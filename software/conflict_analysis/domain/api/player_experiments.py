"""Session/CSRF transport for Foundation-owned G8 assessment operations."""
from __future__ import annotations

import hashlib
import json
from functools import wraps

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError, IntegrityError
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils.cache import patch_vary_headers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied

from domain.services.foundation_packages import RawJSONError, validate_json_content_type
from domain.services.xlsx_adapter import MAX_XLSX_BYTES
from domain.services.player_experiments import (
    PlayerExperimentError, admit_assessment_scope, comparison, create_experiment,
    create_manual_value, import_xlsx, list_experiments, list_expert_profiles,
    list_values, mutate_experiment, open_experiment, preview_xlsx, recover_import,
)
from domain.services.player_workspaces import (
    PlayerError, admit_player_scope, canonical_receipt_bytes, list_player_experiments,
)

_MAX_BODY_BYTES = 1024 * 1024
_MAX_MULTIPART_BYTES = MAX_XLSX_BYTES + 1024 * 1024
_SPOOF_HEADERS = frozenset({
    "HTTP_AUTHORIZATION", "HTTP_X_ACTOR", "HTTP_X_ACTOR_IDENTIFIER",
    "HTTP_X_ACTOR_TYPE", "HTTP_X_ROLE", "HTTP_X_PLAYER_ROLE",
    "HTTP_X_PLAYER_PERMISSIONS", "HTTP_X_STUDIO_ROLE",
    "HTTP_X_STUDIO_CAPABILITY", "HTTP_X_STUDIO_CAPABILITIES",
    "HTTP_X_PROJECT_ID", "HTTP_X_WORKSPACE_ID", "HTTP_X_CAPABILITIES",
    "HTTP_X_AUDIT_CONTEXT", "HTTP_X_SERVICE_CONTEXT", "HTTP_X_SERVICE_PURPOSE",
    "HTTP_X_EXPECTED_MANIFEST_HASH", "HTTP_X_HTTP_METHOD_OVERRIDE",
})
_MESSAGES = {
    "PLAYER_AUTHENTICATION_REQUIRED": "Требуется действующая сессия пользователя.",
    "PLAYER_PERMISSION_DENIED": "Действие запрещено текущими правами доступа.",
    "PLAYER_NOT_FOUND": "Объект недоступен или не найден.",
    "PLAYER_REQUEST_INVALID": "Запрос не соответствует точному контракту Player.",
    "PLAYER_METHOD_NOT_ALLOWED": "Этот метод запроса недоступен.",
    "PLAYER_CSRF_FAILED": "Проверка защиты запроса не пройдена.",
    "PLAYER_STALE": "Контрольная сумма не совпадает с закреплённой версией.",
    "PLAYER_OPERATION_KEY_REUSE": "Идентификатор операции уже связан с другим запросом.",
    "PLAYER_OPERATION_RESULT_DRIFT": "Сохранённый результат операции повреждён.",
    "PLAYER_IDENTITY_CONFLICT": "Запрошенная идентичность уже занята.",
    "ASSESSMENT_PROJECTION_NOT_PROVEN": "Проекция рабочего пространства не подтверждена.",
    "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT": "Целостность проекции не подтверждена.",
    "G8_EXPERIMENT_NOT_DRAFT": "Операция доступна только для DRAFT-эксперимента.",
    "G8_EXPERIMENT_TRANSITION_FORBIDDEN": "Переход жизненного цикла запрещён.",
    "G8_IMPORT_NONEMPTY_EXPERIMENT": "Импорт разрешён только в пустой DRAFT-эксперимент.",
    "G8_IMPORT_PRECONDITION_FAILED": "Повторная проверка импорта не совпала с preview.",
    "G8_IMPORT_ACK_REQUIRED": "Требуется подтверждение сохранённого ticket и 42 исключений.",
    "G8_TARGET_MAPPING_MISMATCH": "Целевая manifest-проекция не совпала с профилем.",
    "G8_PROFILE_HASH_MISMATCH": "Контрольная сумма профиля не совпала.",
    "G8_PROFILE_INVALID": "Пакетированный профиль повреждён.",
    "G8_XLSX_MAPPING_INVALID": "Лист или колонка не соответствуют профилю.",
    "G8_XLSX_REJECTED": "XLSX отклонён безопасным парсером.",
    "G8_XLSX_VALUE_INVALID": "XLSX содержит недопустимое значение.",
    "G8_XLSX_VALUE_OUT_OF_RANGE": "XLSX содержит значение вне шкалы.",
    "PLAYER_OPERATION_FAILED": "Операция не завершена; автоматическое повторение запрещено.",
}


class _SessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if user is None or not user.is_active:
            return None
        return user, None


def _response(payload=None, *, status=200, body=None):
    raw = canonical_receipt_bytes(payload) if body is None else body
    response = HttpResponse(raw, status=status, content_type="application/json; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["ETag"] = f'"{hashlib.sha256(raw).hexdigest()}"'
    response["Content-Length"] = str(len(raw))
    patch_vary_headers(response, ("Cookie",))
    return response


def _error(error):
    code = getattr(error, "code", "PLAYER_OPERATION_FAILED")
    status = getattr(error, "status", 503)
    detail = getattr(error, "detail", None) or _MESSAGES.get(code, _MESSAGES["PLAYER_OPERATION_FAILED"])
    return _response({"code": code, "errors": [detail]}, status=status)


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _body(request):
    length = request.META.get("CONTENT_LENGTH", "")
    if length and (not str(length).isascii() or not str(length).isdigit()
                   or len(str(length)) > 10 or int(length) > _MAX_BODY_BYTES):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    raw = request.body
    if not raw or len(raw) > _MAX_BODY_BYTES:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
    if type(payload) is not dict:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    return payload


def _xlsx_body(request):
    length = request.META.get("CONTENT_LENGTH", "")
    if (
        not str(length).isascii() or not str(length).isdigit()
        or len(str(length)) > 10 or int(length) > _MAX_MULTIPART_BYTES
        or set(request.POST) != {"metadata"} or set(request.FILES) != {"file"}
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    upload = request.FILES["file"]
    if upload.size <= 0 or upload.size > MAX_XLSX_BYTES:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    try:
        metadata = json.loads(
            request.POST["metadata"], object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
    if type(metadata) is not dict:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    raw = upload.read(MAX_XLSX_BYTES + 1)
    if type(raw) is not bytes or len(raw) != upload.size or len(raw) > MAX_XLSX_BYTES:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    return {**metadata, "raw_file": raw}


def _endpoint(*, methods, scope, identity_key, preview=False, query=False,
              xlsx=False, legacy_experiments_get=False):
    def decorate(handler):
        @api_view(methods)
        @authentication_classes((_SessionAuthentication,))
        @permission_classes(())
        def admitted(request, **kwargs):
            try:
                raw = request._request
                if legacy_experiments_get and raw.method == "GET":
                    try:
                        admit_player_scope(user=request.user, kind=scope, identity=kwargs[identity_key])
                    except PlayerError:
                        admit_assessment_scope(user=request.user, kind=scope, identity=kwargs[identity_key])
                elif legacy_experiments_get and raw.method == "POST":
                    try:
                        admit_assessment_scope(
                            user=request.user, kind=scope, identity=kwargs[identity_key]
                        )
                    except PlayerExperimentError as assessment_error:
                        try:
                            admit_player_scope(
                                user=request.user, kind=scope, identity=kwargs[identity_key]
                            )
                        except PlayerError:
                            raise assessment_error
                        raise PlayerExperimentError("PLAYER_METHOD_NOT_ALLOWED", 405)
                else:
                    admit_assessment_scope(user=request.user, kind=scope, identity=kwargs[identity_key])
                if any(key in raw.META for key in _SPOOF_HEADERS):
                    raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
                if not query and raw.GET:
                    raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
                if raw.method in {"POST", "PUT"}:
                    try:
                        SessionAuthentication().enforce_csrf(raw)
                    except PermissionDenied as exc:
                        raise PlayerExperimentError("PLAYER_CSRF_FAILED", 403) from exc
                    body = _xlsx_body(raw) if xlsx else _body(raw)
                    result = handler(request, body=body, **kwargs)
                    if preview:
                        return _response(result)
                    return _response(body=result.body, status=200 if result.replayed else 201)
                if raw.body or "HTTP_IDEMPOTENCY_KEY" in raw.META or "HTTP_IF_MATCH" in raw.META:
                    raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
                payload = handler(request, **kwargs)
                get_token(raw)
                return _response(payload)
            except (PlayerExperimentError, PlayerError) as exc:
                return _error(exc)
            except RequestDataTooBig:
                return _error(PlayerExperimentError("PLAYER_REQUEST_INVALID", 400))
            except (DatabaseError, ValidationError, IntegrityError):
                return _error(PlayerExperimentError("PLAYER_OPERATION_FAILED", 503))

        @wraps(handler)
        def transport(request, **kwargs):
            if request.method not in methods:
                response = _error(PlayerExperimentError("PLAYER_METHOD_NOT_ALLOWED", 405))
                response["Allow"] = ", ".join(methods)
                return response
            if request.method in {"POST", "PUT"}:
                content_type = str(request.META.get("CONTENT_TYPE", ""))
                if xlsx:
                    if not content_type.lower().startswith("multipart/form-data; boundary="):
                        return _error(PlayerExperimentError("PLAYER_REQUEST_INVALID", 400))
                else:
                    try:
                        validate_json_content_type(content_type)
                    except RawJSONError:
                        return _error(PlayerExperimentError("PLAYER_REQUEST_INVALID", 400))
            return admitted(request, **kwargs)
        transport.csrf_exempt = admitted.csrf_exempt
        return transport
    return decorate


def _headers(request):
    return {"operation_id": request.META.get("HTTP_IDEMPOTENCY_KEY"),
            "if_match": request.META.get("HTTP_IF_MATCH")}


@_endpoint(methods=["GET"], scope="workspace", identity_key="workspace_id")
def expert_profiles(request, workspace_id):
    return list_expert_profiles(user=request.user, workspace_id=workspace_id)


@_endpoint(methods=["GET", "POST"], scope="workspace", identity_key="workspace_id", query=True,
           legacy_experiments_get=True)
def experiments(request, workspace_id, body=None):
    if request.method == "POST":
        if request._request.GET:
            raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
        return create_experiment(user=request.user, workspace_id=workspace_id, body=body,
                                 **_headers(request))
    values = request._request.GET.getlist("include_archived")
    if set(request._request.GET) - {"include_archived"} or len(values) > 1:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    try:
        return list_experiments(user=request.user, workspace_id=workspace_id,
                                include_archived=values == ["true"])
    except PlayerExperimentError as exc:
        if exc.code != "PLAYER_PERMISSION_DENIED" or values:
            raise
        return list_player_experiments(user=request.user, workspace_id=workspace_id)


@_endpoint(methods=["GET", "PUT"], scope="experiment", identity_key="experiment_id")
def experiment(request, experiment_id, body=None):
    if request.method == "PUT":
        return mutate_experiment(user=request.user, experiment_id=experiment_id,
                                 body=body, action="update", **_headers(request))
    return open_experiment(user=request.user, experiment_id=experiment_id)


@_endpoint(methods=["POST"], scope="experiment", identity_key="experiment_id")
def freeze(request, experiment_id, body=None):
    return mutate_experiment(user=request.user, experiment_id=experiment_id,
                             body=body, action="freeze", **_headers(request))


@_endpoint(methods=["POST"], scope="experiment", identity_key="experiment_id")
def archive(request, experiment_id, body=None):
    return mutate_experiment(user=request.user, experiment_id=experiment_id,
                             body=body, action="archive", **_headers(request))


@_endpoint(methods=["GET", "POST"], scope="experiment", identity_key="experiment_id")
def values(request, experiment_id, body=None):
    if request.method == "POST":
        return create_manual_value(user=request.user, experiment_id=experiment_id,
                                   body=body, **_headers(request))
    return list_values(user=request.user, experiment_id=experiment_id)


@_endpoint(methods=["POST"], scope="experiment", identity_key="experiment_id", preview=True, xlsx=True)
def xlsx_preview(request, experiment_id, body=None):
    return preview_xlsx(user=request.user, experiment_id=experiment_id, body=body)


@_endpoint(methods=["POST"], scope="experiment", identity_key="experiment_id", xlsx=True)
def xlsx_import(request, experiment_id, body=None):
    return import_xlsx(user=request.user, experiment_id=experiment_id,
                       body=body, **_headers(request))


@_endpoint(methods=["GET"], scope="experiment", identity_key="experiment_id")
def import_recovery(request, experiment_id, operation_id):
    return recover_import(user=request.user, experiment_id=experiment_id,
                          operation_id=operation_id)


@_endpoint(methods=["GET"], scope="workspace", identity_key="workspace_id")
def experiment_comparison(request, workspace_id):
    return comparison(user=request.user, workspace_id=workspace_id)
