"""Hardened, standalone settings for the session-only Studio showcase."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent

_secret_key = os.getenv("DJANGO_SECRET_KEY", "")
if len(_secret_key) < 32:
    raise ImproperlyConfigured(
        "Studio showcase requires a cryptographically generated per-run "
        "DJANGO_SECRET_KEY. Start it with scripts/run_studio_showcase.ps1."
    )
SECRET_KEY = _secret_key

# Presentation assets are served by runserver --insecure on a loopback socket;
# Django diagnostics and debug exception pages remain disabled.
DEBUG = False

_allowed_loopback_hosts = {"127.0.0.1", "localhost", "[::1]"}
_configured_hosts = {
    item.strip()
    for item in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,[::1]",
    ).split(",")
    if item.strip()
}
if not _configured_hosts or not _configured_hosts <= _allowed_loopback_hosts:
    unsafe_hosts = sorted(_configured_hosts - _allowed_loopback_hosts)
    raise ImproperlyConfigured(
        "Studio showcase accepts loopback hosts only; rejected: "
        f"{unsafe_hosts or sorted(_configured_hosts)}"
    )
ALLOWED_HOSTS = sorted(_configured_hosts)

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "shared_ui.apps.SharedUiConfig",
    "studio_showcase.apps.StudioShowcaseConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "conflict_analysis.studio_showcase_urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

# No relational backend is part of this presentation-only composition root.
# Any accidental ORM access therefore fails instead of reaching Foundation.
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "studio_showcase_staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
