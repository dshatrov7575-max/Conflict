"""Fail-closed bridge from a trusted upstream SSO/reverse proxy to Django."""

from __future__ import annotations

import hmac

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.backends import RemoteUserBackend
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse


UPSTREAM_USER_META = "HTTP_X_CONFLICT_AUTH_USER"
UPSTREAM_SECRET_META = "HTTP_X_CONFLICT_AUTH_SECRET"


class ProvisionedRemoteUserBackend(RemoteUserBackend):
    """Authenticate only users provisioned explicitly in the local database."""

    create_unknown_user = False


def _logout(request: HttpRequest) -> None:
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        auth.logout(request)


def _valid_username(value: str) -> bool:
    if not value or value != value.strip() or len(value) > 150:
        return False
    if "," in value:
        # WSGI/proxy stacks may comma-join duplicate headers. Reject ambiguity.
        return False
    return not any(ord(character) < 32 or ord(character) == 127 for character in value)


class TrustedUpstreamAuthMiddleware:
    """
    Authenticate a pre-provisioned local user from headers injected by a trusted proxy.

    The proxy contract is strict: it must strip any client-supplied
    X-Conflict-Auth-User / X-Conflict-Auth-Secret headers and inject both values
    only after upstream authentication succeeds.
    """

    sync_capable = True
    async_capable = False

    def __init__(self, get_response):
        if get_response is None:
            raise ValueError("get_response must be provided")
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        response = self.process_request(request)
        if response is not None:
            return response
        return self.get_response(request)

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        if not hasattr(request, "user"):
            raise ImproperlyConfigured(
                "TrustedUpstreamAuthMiddleware requires AuthenticationMiddleware first."
            )

        username = request.META.pop(UPSTREAM_USER_META, None)
        presented_secret = request.META.pop(UPSTREAM_SECRET_META, None)

        if username is None and presented_secret is None:
            _logout(request)
            return None

        if not isinstance(username, str) or not isinstance(presented_secret, str):
            _logout(request)
            return HttpResponse("UPSTREAM_AUTH_HEADERS_REQUIRED\n", status=403)

        if not _valid_username(username):
            _logout(request)
            return HttpResponse("UPSTREAM_AUTH_USER_INVALID\n", status=400)

        expected_secret = settings.UPSTREAM_AUTH_SHARED_SECRET
        if not hmac.compare_digest(presented_secret, expected_secret):
            _logout(request)
            return HttpResponse("UPSTREAM_AUTH_SECRET_INVALID\n", status=403)

        if request.user.is_authenticated:
            if request.user.get_username() == username:
                return None
            _logout(request)

        user = auth.authenticate(request, remote_user=username)
        if user is None:
            return HttpResponse("UPSTREAM_AUTH_USER_NOT_PROVISIONED\n", status=403)

        request.user = user
        auth.login(request, user)
        return None
