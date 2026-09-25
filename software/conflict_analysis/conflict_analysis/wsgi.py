"""WSGI config for Conflict Analysis."""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conflict_analysis.settings")

application = get_wsgi_application()
