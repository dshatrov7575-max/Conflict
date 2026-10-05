"""Machine-readable probe for the installed production runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

import django


def snapshot() -> dict[str, object]:
    django.setup()
    import conflict_analysis
    from django.conf import settings
    from django.urls import Resolver404, resolve

    try:
        resolve("/admin/")
    except Resolver404:
        admin_exposed = False
    else:
        admin_exposed = True

    getuid = getattr(os, "getuid", None)
    return {
        "admin_exposed": admin_exposed,
        "admin_installed": "django.contrib.admin" in settings.INSTALLED_APPS,
        "debug": settings.DEBUG,
        "engine": settings.DATABASES["default"]["ENGINE"],
        "package_path": str(Path(conflict_analysis.__file__).resolve()),
        "source_tree_present": Path("/app/manage.py").exists(),
        "static_root_present": Path(settings.STATIC_ROOT).is_dir(),
        "uid": getuid() if getuid is not None else None,
    }


def main() -> None:
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
