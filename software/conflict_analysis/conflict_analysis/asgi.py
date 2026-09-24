"""ASGI config for Conflict Analysis."""

import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conflict_analysis.settings")

application = get_asgi_application()
