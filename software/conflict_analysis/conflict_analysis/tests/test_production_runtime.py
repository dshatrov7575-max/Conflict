from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = PROJECT_ROOT / "scripts" / "verify_production_runtime.py"


def _production_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "conflict_analysis.production_settings",
            "DJANGO_SECRET_KEY": "test-production-secret-" + "x" * 60,
            "DJANGO_ALLOWED_HOSTS": "conflict.example.org",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://conflict.example.org",
            "POSTGRES_DB": "conflict_analysis",
            "POSTGRES_USER": "conflict_analysis",
            "POSTGRES_PASSWORD": "test-production-database-password",
            "FD08_PROJECTION_CAPABILITY_TOKEN": "test-fd08-projection-capability-" + "y" * 40,
            "POSTGRES_HOST": "db.example.org",
            "POSTGRES_PORT": "5432",
            "POSTGRES_CONN_MAX_AGE": "60",
            "USE_SQLITE": "false",
            "DJANGO_DEBUG": "false",
            "DJANGO_STATIC_ROOT": str(PROJECT_ROOT / ".test-static-production"),
        }
    )
    env.update(overrides)
    return env


def _settings_probe(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    code = """
import json
import django
django.setup()
from django.conf import settings
from django.urls import Resolver404, resolve
try:
    resolve('/admin/')
except Resolver404:
    admin_exposed = False
else:
    admin_exposed = True
print(json.dumps({
    'debug': settings.DEBUG,
    'engine': settings.DATABASES['default']['ENGINE'],
    'admin_exposed': admin_exposed,
    'ssl_redirect': settings.SECURE_SSL_REDIRECT,
    'session_secure': settings.SESSION_COOKIE_SECURE,
    'csrf_secure': settings.CSRF_COOKIE_SECURE,
    'hsts': settings.SECURE_HSTS_SECONDS,
    'root_urlconf': settings.ROOT_URLCONF,
    'whitenoise': 'whitenoise.middleware.WhiteNoiseMiddleware' in settings.MIDDLEWARE,
    'admin_installed': 'django.contrib.admin' in settings.INSTALLED_APPS,
    'forwarded_host': settings.USE_X_FORWARDED_HOST,
    'static_backend': settings.STORAGES['staticfiles']['BACKEND'],
}, sort_keys=True))
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


class ProductionRuntimeContractTests(SimpleTestCase):
    def test_static_production_runtime_contract_is_fail_closed(self):
        completed = subprocess.run(
            [sys.executable, str(VERIFIER), "--project-root", str(PROJECT_ROOT)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertFalse(payload["admin_exposed"])
        self.assertFalse(payload["source_bind_mount"])

    def test_production_settings_are_secure_and_admin_free(self):
        completed = _settings_probe(_production_env())
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["engine"], "django.db.backends.postgresql")
        self.assertFalse(payload["debug"])
        self.assertFalse(payload["admin_exposed"])
        self.assertTrue(payload["ssl_redirect"])
        self.assertTrue(payload["session_secure"])
        self.assertTrue(payload["csrf_secure"])
        self.assertEqual(payload["hsts"], 31_536_000)
        self.assertEqual(payload["root_urlconf"], "conflict_analysis.production_urls")
        self.assertTrue(payload["whitenoise"])
        self.assertFalse(payload["admin_installed"])
        self.assertFalse(payload["forwarded_host"])
        self.assertEqual(
            payload["static_backend"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_production_probe_is_machine_readable(self):
        completed = subprocess.run(
            [sys.executable, "-m", "conflict_analysis.production_probe"],
            cwd=PROJECT_ROOT,
            env=_production_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["admin_exposed"])
        self.assertFalse(payload["admin_installed"])
        self.assertIsNone(payload["application_wheel_sha256"])
        self.assertFalse(payload["wheel_identity_present"])
        self.assertFalse(payload["debug"])
        self.assertEqual(payload["engine"], "django.db.backends.postgresql")
        self.assertIsInstance(payload["static_root_present"], bool)

    def test_production_settings_reject_missing_or_unsafe_secrets(self):
        for overrides in (
            {"DJANGO_SECRET_KEY": ""},
            {"DJANGO_SECRET_KEY": "too-short"},
            {"DJANGO_SECRET_KEY": "replace-with-at-least-50-random-characters-before-starting"},
            {"POSTGRES_PASSWORD": ""},
            {"POSTGRES_PASSWORD": "local-development-only"},
            {"POSTGRES_PASSWORD": "replace-with-a-strong-database-password"},
            {"POSTGRES_PASSWORD": "too-short"},
            {"POSTGRES_PASSWORD": "conflict_analysis"},
        ):
            with self.subTest(overrides=overrides):
                completed = _settings_probe(_production_env(**overrides))
                self.assertNotEqual(completed.returncode, 0, completed.stdout)

    def test_django_deploy_check_is_warning_free(self):
        completed = subprocess.run(
            [sys.executable, "-m", "django", "check", "--deploy", "--fail-level", "WARNING"],
            cwd=PROJECT_ROOT,
            env=_production_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_production_settings_reject_debug_sqlite_and_wildcard_hosts(self):
        for overrides in (
            {"DJANGO_DEBUG": "true"},
            {"USE_SQLITE": "true"},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_ALLOWED_HOSTS": "https://conflict.example.org"},
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://conflict.example.org"},
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "https://*.example.org"},
            {"POSTGRES_PORT": "not-a-port"},
            {"POSTGRES_CONN_MAX_AGE": "-1"},
            {"DJANGO_STATIC_ROOT": "relative/static"},
        ):
            with self.subTest(overrides=overrides):
                completed = _settings_probe(_production_env(**overrides))
                self.assertNotEqual(completed.returncode, 0, completed.stdout)
