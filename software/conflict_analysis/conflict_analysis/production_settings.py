"""Fail-closed production settings for Conflict Analysis."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


_FORBIDDEN_DJANGO_SECRETS = {
    "unsafe-development-key-replace-before-deployment",
    "local-compose-development-only",
    "replace-with-at-least-50-random-characters-before-starting",
}
_FORBIDDEN_DATABASE_PASSWORDS = {
    "local-development-only",
    "replace-with-a-strong-database-password",
}
_FORBIDDEN_UPSTREAM_AUTH_SECRETS = {
    "replace-with-a-strong-upstream-auth-secret",
    "development-only-upstream-auth-secret",
}


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required in production")
    return value


def _csv(name: str, *, required: bool = False) -> list[str]:
    raw = _required(name) if required else os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: str, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ImproperlyConfigured(f"{name} must be between {minimum} and {maximum}")
    return value


if _enabled("DJANGO_DEBUG"):
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in production")
if _enabled("USE_SQLITE"):
    raise ImproperlyConfigured("SQLite is forbidden in production")

DEBUG = False
SECRET_KEY = _required("DJANGO_SECRET_KEY")
FD08_PROJECTION_LEASE_SECRET = _required("FD08_PROJECTION_LEASE_SECRET")
UPSTREAM_AUTH_SHARED_SECRET = _required("UPSTREAM_AUTH_SHARED_SECRET")
if (
    len(FD08_PROJECTION_LEASE_SECRET) < 32
    or FD08_PROJECTION_LEASE_SECRET
    == "development-only-fd08-projection-capability-0123456789abcdef"
):
    raise ImproperlyConfigured(
        "FD08_PROJECTION_LEASE_SECRET must be a non-placeholder value of at least 32 characters"
    )
if len(SECRET_KEY) < 50 or SECRET_KEY in _FORBIDDEN_DJANGO_SECRETS:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a non-placeholder value of at least 50 characters")
if (
    len(UPSTREAM_AUTH_SHARED_SECRET) < 32
    or UPSTREAM_AUTH_SHARED_SECRET in _FORBIDDEN_UPSTREAM_AUTH_SECRETS
):
    raise ImproperlyConfigured(
        "UPSTREAM_AUTH_SHARED_SECRET must be a non-placeholder value of at least 32 characters"
    )

ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS", required=True)
if any(host == "*" or "://" in host or "/" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit host names without schemes or wildcards")
CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS")
if any(not origin.startswith("https://") or "*" in origin for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must contain explicit HTTPS origins")

POSTGRES_USER = _required("POSTGRES_USER")
POSTGRES_PASSWORD = _required("POSTGRES_PASSWORD")
if (
    len(POSTGRES_PASSWORD) < 20
    or POSTGRES_PASSWORD in _FORBIDDEN_DATABASE_PASSWORDS
    or POSTGRES_PASSWORD == POSTGRES_USER
):
    raise ImproperlyConfigured("POSTGRES_PASSWORD must be a non-placeholder value of at least 20 characters")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _required("POSTGRES_DB"),
        "USER": POSTGRES_USER,
        "PASSWORD": POSTGRES_PASSWORD,
        "HOST": _required("POSTGRES_HOST"),
        "PORT": str(_bounded_int("POSTGRES_PORT", "5432", minimum=1, maximum=65_535)),
        "CONN_MAX_AGE": _bounded_int("POSTGRES_CONN_MAX_AGE", "60", minimum=0, maximum=86_400),
        "CONN_HEALTH_CHECKS": True,
    }
}

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django.contrib.admin"]  # noqa: F405
ROOT_URLCONF = "conflict_analysis.production_urls"
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
_authentication_index = MIDDLEWARE.index(
    "django.contrib.auth.middleware.AuthenticationMiddleware"
)
MIDDLEWARE.insert(
    _authentication_index + 1,
    "conflict_analysis.upstream_auth.TrustedUpstreamAuthMiddleware",
)
AUTHENTICATION_BACKENDS = [
    "conflict_analysis.upstream_auth.ProvisionedRemoteUserBackend",
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

STATIC_ROOT = Path(os.getenv("DJANGO_STATIC_ROOT", "/app/staticfiles"))
if not STATIC_ROOT.is_absolute():
    raise ImproperlyConfigured("DJANGO_STATIC_ROOT must be an absolute path")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
