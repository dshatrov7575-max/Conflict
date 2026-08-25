from __future__ import annotations

import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from studio_showcase.session import FIXTURES, fixture, validate_session


@require_GET
@ensure_csrf_cookie
def index(request):
    return render(
        request,
        "studio_showcase/index.html",
        {
            "initial_session": fixture("6x8"),
            "fixture_names": sorted(FIXTURES),
        },
    )


@require_GET
def fixture_api(request, fixture_name: str):
    try:
        payload = fixture(fixture_name)
    except ValueError as error:
        raise Http404(str(error)) from error
    return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


@require_POST
def validate_api(request):
    if len(request.body) > 2 * 1024 * 1024:
        return JsonResponse(
            {
                "valid": False,
                "diagnostics": [
                    {
                        "level": "error",
                        "code": "SESSION_TOO_LARGE",
                        "path": "$",
                        "message": "Файл showcase-сессии превышает безопасный лимит 2 МБ.",
                    }
                ],
            },
            status=413,
            json_dumps_params={"ensure_ascii": False},
        )
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {
                "valid": False,
                "diagnostics": [
                    {
                        "level": "error",
                        "code": "INVALID_JSON",
                        "path": "$",
                        "message": "Не удалось прочитать JSON showcase-сессии.",
                    }
                ],
            },
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
    diagnostics = validate_session(payload)
    return JsonResponse(
        {"valid": not diagnostics, "diagnostics": diagnostics},
        json_dumps_params={"ensure_ascii": False},
    )


@require_GET
def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "application": "ConflictAnalysis Studio — Прототип",
            "persistence": "session-only",
        },
        json_dumps_params={"ensure_ascii": False},
    )
