"""Read-only HTTP boundary for exact multilingual Fact evidence."""

from __future__ import annotations

from functools import wraps
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.http import Http404, HttpResponseNotAllowed
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK

from domain.services.evidence_drilldown import build_evidence_drilldown
from domain.services.project_definitions import project_access_group_name


VISIBILITY_WORKSPACE_SHARED = "WORKSPACE_SHARED"
VISIBILITY_OWNER_ONLY = "OWNER_ONLY"
VISIBILITY_EXPERIMENT_PRIVATE = "EXPERIMENT_PRIVATE"


class _ReadOnlyBasicAuthentication(BasicAuthentication):
    """Basic authentication which can never invoke Django's hash-upgrade setter."""

    _failure = "Invalid username/password."

    def authenticate_credentials(self, userid, password, request=None):
        user_model = get_user_model()
        try:
            user = user_model._default_manager.get_by_natural_key(userid)
        except user_model.DoesNotExist:
            # Match the current hasher's work factor without writing a row or
            # leaking the difference between an absent and present username.
            dummy = user_model()
            dummy.set_password(password)
            raise AuthenticationFailed(self._failure)
        if not check_password(password, user.password, setter=None):
            raise AuthenticationFailed(self._failure)
        if not user.is_active:
            raise AuthenticationFailed(self._failure)
        return user, None


class _ReadOnlySessionAuthentication(SessionAuthentication):
    """Permit existing session credentials without CSRF/session creation on GET."""

    def authenticate(self, request: Request):
        # SessionAuthentication performs no CSRF validation for safe methods;
        # this override documents that fact and keeps this route's auth list
        # distinct from the write endpoints.
        return super().authenticate(request)


_READ_ONLY_AUTHENTICATION = (
    _ReadOnlyBasicAuthentication,
    _ReadOnlySessionAuthentication,
)


def _get_only_boundary(view):
    """Reject non-GET methods before DRF can authenticate or inspect a body."""

    @wraps(view)
    def boundary(request, *args, **kwargs):
        if request.method != "GET":
            response = HttpResponseNotAllowed(["GET"])
            response["Content-Length"] = "0"
            return response
        return view(request, *args, **kwargs)

    return boundary


def _clear_read_only_cookie_mutation(request, response=None) -> None:
    """Prevent Session/CSRF response-phase writes while retaining auth reads."""

    request.META["CSRF_COOKIE_NEEDS_UPDATE"] = False
    session = getattr(request, "session", None)
    if session is not None:
        session.accessed = False
        session.modified = False
    if response is not None:
        response.cookies.clear()
        if response.has_header("Set-Cookie"):
            del response["Set-Cookie"]


def _read_only_http_boundary(view):
    """Apply the complete zero-write, no-cookie cache privacy boundary."""

    @wraps(view)
    def boundary(request, *args, **kwargs):
        response = None
        try:
            response = view(request, *args, **kwargs)
            return response
        finally:
            if response is not None:
                response["Cache-Control"] = "no-store"
                response["Vary"] = "Cookie, Authorization"
            _clear_read_only_cookie_mutation(request, response)

    return boundary


def _domain_models() -> Any:
    from domain import models as domain_models

    return domain_models


def _has_project_access(user: Any, project: Any) -> bool:
    """Use only server-derived superuser/group facts for Project scope."""

    if not bool(getattr(user, "is_authenticated", False)):
        return False
    if bool(getattr(user, "is_superuser", False)):
        return True
    groups = getattr(user, "groups", None)
    return bool(
        groups is not None
        and groups.filter(name=project_access_group_name(project.pk)).exists()
    )


def _private_fact_access(user: Any, fact: Any) -> bool:
    """Private Fact access is exact identity equality, never a client header."""

    if bool(getattr(user, "is_superuser", False)):
        return True
    if not bool(getattr(user, "is_authenticated", False)):
        return False
    user_id = getattr(user, "pk", None)
    if user_id is None:
        return False
    return fact.coder_identifier == f"django-user:{user_id}"


def _fact_visible_or_404(user: Any, fact: Any) -> None:
    if fact.visibility == VISIBILITY_WORKSPACE_SHARED:
        return
    if fact.visibility in (VISIBILITY_OWNER_ONLY, VISIBILITY_EXPERIMENT_PRIVATE):
        if _private_fact_access(user, fact):
            return
    # This same bare error is used for absent Project/Workspace/Fact and each
    # denial.  Nothing about which stage failed reaches the client.
    raise Http404()


def _project_or_404(user: Any, project_id: object) -> Any:
    models = _domain_models()
    try:
        project = models.Project.objects.get(pk=project_id)
    except (models.Project.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc
    if not _has_project_access(user, project):
        raise Http404()
    return project


def _workspace_or_404(project: Any, workspace_id: object) -> Any:
    models = _domain_models()
    try:
        return models.ProjectWorkspace.objects.get(pk=workspace_id, project=project)
    except (models.ProjectWorkspace.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc


def _fact_or_404(workspace: Any, fact_id: object) -> Any:
    models = _domain_models()
    try:
        return models.Fact.objects.get(pk=fact_id, workspace=workspace)
    except (models.Fact.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc


@_read_only_http_boundary
@_get_only_boundary
@api_view(["GET"])
@authentication_classes(_READ_ONLY_AUTHENTICATION)
@permission_classes([AllowAny])
def fact_evidence_drilldown(
    request: Request,
    project_id: object,
    workspace_id: object,
    fact_id: object,
) -> Response:
    """Expose evidence only after the frozen authorization admission sequence."""

    # Do not merge these lookups: their observable sequencing is the privacy
    # contract.  In particular, no Fact/evidence query happens before Project
    # scope, Workspace scope and Fact visibility have passed.
    project = _project_or_404(request.user, project_id)
    workspace = _workspace_or_404(project, workspace_id)
    fact = _fact_or_404(workspace, fact_id)
    _fact_visible_or_404(request.user, fact)
    return Response(build_evidence_drilldown(fact).as_dict(), status=HTTP_200_OK)
