from __future__ import annotations

from unittest.mock import patch

from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase, TestCase

from conflict_analysis.production_health import ready
from conflict_analysis.production_health_probe import _host


class ProductionReadinessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_ready_is_exact_no_store_and_database_backed(self):
        response = ready(self.factory.get("/health/ready/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"READY\n")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")

    def test_database_failure_is_generic_503_without_exception_disclosure(self):
        with patch(
            "conflict_analysis.production_health.connection.cursor",
            side_effect=DatabaseError("secret database detail"),
        ):
            response = ready(self.factory.get("/health/ready/"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b"NOT_READY\n")
        self.assertNotIn(b"secret", response.content)

    def test_non_get_is_rejected_before_readiness_logic(self):
        response = ready(self.factory.post("/health/ready/"))
        self.assertEqual(response.status_code, 405)


class ProductionHealthProbeTests(SimpleTestCase):
    def test_probe_uses_first_explicit_allowed_host(self):
        with patch.dict(
            "os.environ",
            {"DJANGO_ALLOWED_HOSTS": "conflict.example.org,other.example.org"},
            clear=False,
        ):
            self.assertEqual(_host(), "conflict.example.org")

    def test_probe_rejects_missing_allowed_host(self):
        with patch.dict("os.environ", {"DJANGO_ALLOWED_HOSTS": " , "}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "no readiness host"):
                _host()
