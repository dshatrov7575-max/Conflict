"""Isolated settings entry point for the presentation-only Studio showcase."""

from conflict_analysis.settings import *  # noqa: F403


INSTALLED_APPS = [  # noqa: F405
    *INSTALLED_APPS,  # noqa: F405
    "shared_ui.apps.SharedUiConfig",
    "studio_showcase.apps.StudioShowcaseConfig",
]

ROOT_URLCONF = "conflict_analysis.studio_showcase_urls"

# The showcase never persists domain data.  An in-memory database remains
# configured solely so Django's system checks have a complete backend config.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

