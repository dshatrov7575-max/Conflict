from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from conflict_analysis.upstream_auth import (
    TrustedUpstreamAuthMiddleware,
    UPSTREAM_SECRET_META,
    UPSTREAM_USER_META,
)


AUTH_SECRET = "unit-test-upstream-auth-secret-" + "x" * 32
BACKEND = "conflict_analysis.upstream_auth.ProvisionedRemoteUserBackend"


@override_settings(
    UPSTREAM_AUTH_SHARED_SECRET=AUTH_SECRET,
    AUTHENTICATION_BACKENDS=[BACKEND],
)
class TrustedUpstreamAuthMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(
            username="analyst",
            password=None,
            is_active=True,
        )
        self.middleware = TrustedUpstreamAuthMiddleware(
            lambda request: HttpResponse(
                request.user.get_username()
                if request.user.is_authenticated
                else "anonymous",
                status=200,
            )
        )

    def _request(self, **meta):
        request = self.factory.get("/", **meta)
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        AuthenticationMiddleware(lambda req: None).process_request(request)
        return request

    def test_valid_headers_authenticate_only_preprovisioned_user(self):
        request = self._request(
            HTTP_X_CONFLICT_AUTH_USER="analyst",
            HTTP_X_CONFLICT_AUTH_SECRET=AUTH_SECRET,
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"analyst")
        self.assertTrue(request.user.is_authenticated)
        self.assertEqual(request.user.pk, self.user.pk)
        self.assertNotIn(UPSTREAM_USER_META, request.META)
        self.assertNotIn(UPSTREAM_SECRET_META, request.META)
        self.assertEqual(
            request.session["_auth_user_backend"],
            BACKEND,
        )

    def test_unknown_and_inactive_users_fail_closed_without_creation(self):
        request = self._request(
            HTTP_X_CONFLICT_AUTH_USER="not-provisioned",
            HTTP_X_CONFLICT_AUTH_SECRET=AUTH_SECRET,
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            get_user_model().objects.filter(username="not-provisioned").exists()
        )

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        request = self._request(
            HTTP_X_CONFLICT_AUTH_USER="analyst",
            HTTP_X_CONFLICT_AUTH_SECRET=AUTH_SECRET,
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)

    def test_bad_or_incomplete_proxy_headers_fail_closed(self):
        cases = (
            (
                {"HTTP_X_CONFLICT_AUTH_USER": "analyst"},
                403,
            ),
            (
                {"HTTP_X_CONFLICT_AUTH_SECRET": AUTH_SECRET},
                403,
            ),
            (
                {
                    "HTTP_X_CONFLICT_AUTH_USER": "analyst",
                    "HTTP_X_CONFLICT_AUTH_SECRET": "wrong-secret",
                },
                403,
            ),
            (
                {
                    "HTTP_X_CONFLICT_AUTH_USER": " analyst",
                    "HTTP_X_CONFLICT_AUTH_SECRET": AUTH_SECRET,
                },
                400,
            ),
            (
                {
                    "HTTP_X_CONFLICT_AUTH_USER": "analyst,attacker",
                    "HTTP_X_CONFLICT_AUTH_SECRET": AUTH_SECRET,
                },
                400,
            ),
            (
                {
                    "HTTP_AUTHORIZATION": "Basic YW5hbHlzdDpwYXNzd29yZA==",
                },
                403,
            ),
            (
                {
                    "HTTP_AUTHORIZATION": "Bearer attacker-token",
                    "HTTP_X_CONFLICT_AUTH_USER": "analyst",
                    "HTTP_X_CONFLICT_AUTH_SECRET": AUTH_SECRET,
                },
                403,
            ),
        )
        for meta, expected_status in cases:
            with self.subTest(meta=meta):
                request = self._request(**meta)
                response = self.middleware(request)
                self.assertEqual(response.status_code, expected_status)
                self.assertFalse(request.user.is_authenticated)

    def test_missing_headers_log_out_existing_upstream_session(self):
        first = self._request(
            HTTP_X_CONFLICT_AUTH_USER="analyst",
            HTTP_X_CONFLICT_AUTH_SECRET=AUTH_SECRET,
        )
        response = self.middleware(first)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(first.user.is_authenticated)

        second = self.factory.get("/")
        second.session = first.session
        AuthenticationMiddleware(lambda req: None).process_request(second)
        self.assertTrue(second.user.is_authenticated)

        response = self.middleware(second)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"anonymous")
        self.assertFalse(second.user.is_authenticated)
