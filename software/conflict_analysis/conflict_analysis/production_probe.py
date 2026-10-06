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

    wheel_identity_path = Path("/app/conflict-application-wheel.json")
    wheel_identity_present = wheel_identity_path.is_file()
    application_wheel_sha256 = None
    if wheel_identity_present:
        wheel_identity = json.loads(wheel_identity_path.read_text(encoding="utf-8"))
        if not isinstance(wheel_identity, dict):
            raise RuntimeError("Installed application wheel identity is invalid")
        candidate = wheel_identity.get("sha256")
        if (
            wheel_identity.get("status") != "PASS"
            or not isinstance(candidate, str)
            or len(candidate) != 64
            or any(character not in "0123456789abcdef" for character in candidate)
        ):
            raise RuntimeError("Installed application wheel identity is invalid")
        application_wheel_sha256 = candidate

    getuid = getattr(os, "getuid", None)
    rest_framework = getattr(settings, "REST_FRAMEWORK", {})
    return {
        "admin_exposed": admin_exposed,
        "admin_installed": "django.contrib.admin" in settings.INSTALLED_APPS,
        "application_wheel_sha256": application_wheel_sha256,
        "debug": settings.DEBUG,
        "engine": settings.DATABASES["default"]["ENGINE"],
        "package_path": str(Path(conflict_analysis.__file__).resolve()),
        "source_tree_present": Path("/app/manage.py").exists(),
        "static_root_present": Path(settings.STATIC_ROOT).is_dir(),
        "upstream_auth_middleware": (
            "conflict_analysis.upstream_auth.TrustedUpstreamAuthMiddleware"
            in settings.MIDDLEWARE
        ),
        "authentication_backends": list(settings.AUTHENTICATION_BACKENDS),
        "drf_authentication_classes": list(
            rest_framework.get("DEFAULT_AUTHENTICATION_CLASSES", [])
        ),
        "uid": getuid() if getuid is not None else None,
        "wheel_identity_present": wheel_identity_present,
    }


def main() -> None:
    print(json.dumps(snapshot(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
