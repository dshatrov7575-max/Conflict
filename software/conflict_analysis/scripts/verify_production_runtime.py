#!/usr/bin/env python3
"""Static fail-closed contract for the production runtime profile."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DOCKERFILE_FRONTEND_DIGEST = "sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e"
PYTHON_DIGEST = "sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d"
POSTGRES_DIGEST = "sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve(strict=True)

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    dev_compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (root / "docker-compose.prod.yml").read_text(encoding="utf-8")
    settings = (root / "conflict_analysis/production_settings.py").read_text(encoding="utf-8")
    urls = (root / "conflict_analysis/production_urls.py").read_text(encoding="utf-8")
    probe = (root / "conflict_analysis/production_probe.py").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    wheel_builder = (root / "scripts/build_reproducible_wheel.py").read_text(encoding="utf-8")
    build_lock_lines = (root / "requirements/build-lock.txt").read_text(encoding="utf-8").splitlines()
    lock_lines = (root / "requirements/production-lock.txt").read_text(encoding="utf-8").splitlines()

    require(
        dockerfile.startswith(f"# syntax=docker/dockerfile:1.7@{DOCKERFILE_FRONTEND_DIGEST}\n"),
        "Dockerfile frontend is not digest-pinned",
    )
    require(f"python:3.12-slim@{PYTHON_DIGEST}" in dockerfile, "Python image is not digest-pinned")
    require("python -m pip install --upgrade pip" not in dockerfile, "mutable pip upgrade is forbidden")
    require('requires = ["setuptools==84.0.0"]' in pyproject, "build backend must be exact")
    require("requirements/build-lock.txt" in dockerfile, "hashed build-tool lock is not used")
    require("scripts/build_reproducible_wheel.py" in dockerfile, "production image bypasses the canonical wheel builder")
    require("conflict-application-wheel.json /app/conflict-application-wheel.json" in dockerfile, "production image omits application wheel identity")
    require("python -m pip wheel" not in dockerfile, "direct production wheel build is forbidden")
    require("CANONICAL_SOURCE_DATE_EPOCH = 315_532_800" in wheel_builder, "canonical wheel epoch is missing")
    require('environment["SOURCE_DATE_EPOCH"] = canonical_epoch' in wheel_builder, "wheel builder does not seal SOURCE_DATE_EPOCH")
    require("output directory must be outside the project source tree" in wheel_builder, "wheel builder permits output inside source tree")
    require(dockerfile.count("RUN --network=none") >= 2, "wheel build and final installation must be offline")
    require("FROM base AS development" in dockerfile, "development target is missing")
    require("FROM base AS production" in dockerfile, "production target is missing")
    require("--require-hashes" in dockerfile and "requirements/production-lock.txt" in dockerfile, "builder must verify the production lock")
    production = dockerfile.split("FROM base AS production", 1)[1]
    require(".[dev]" not in production, "production image must not install test extras")
    require("COPY . ." not in production, "production image must not copy the source tree")
    for token in ("--no-index", "collectstatic --noinput --clear", "USER app", "conflict_analysis.production_settings"):
        require(token in production, f"production image contract is missing: {token}")

    require("target: development" in dev_compose, "development compose must select the development image target")
    require(f"postgres:18-alpine@{POSTGRES_DIGEST}" in dev_compose, "development PostgreSQL image is not pinned")
    require(f"postgres:18-alpine@{POSTGRES_DIGEST}" in prod_compose, "production PostgreSQL image is not pinned")
    for token in (
        "target: production",
        "conflict_analysis.production_settings",
        "gunicorn",
        "init: true",
        "read_only: true",
        "cap_drop:",
        "no-new-privileges:true",
        "127.0.0.1:${APP_PORT:-8000}:8000",
        "service_completed_successfully",
    ):
        require(token in prod_compose, f"production compose contract is missing: {token}")
    require(prod_compose.count("platform: linux/amd64") == 2, "production lock requires explicit linux/amd64 services")
    require("runserver" not in prod_compose, "runserver is forbidden in production compose")
    require(".:/app" not in prod_compose, "source bind mounts are forbidden in production compose")
    for name in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        require(f"${{{name}:?" in prod_compose, f"production compose must require {name}")

    for token in (
        'DEBUG = False',
        'SQLite is forbidden in production',
        'DJANGO_ALLOWED_HOSTS must contain explicit host names without schemes or wildcards',
        'SESSION_COOKIE_SECURE = True',
        'CSRF_COOKIE_SECURE = True',
        'SECURE_SSL_REDIRECT = True',
        'SECURE_HSTS_SECONDS = 31_536_000',
        'whitenoise.middleware.WhiteNoiseMiddleware',
        'CompressedManifestStaticFilesStorage',
        'ROOT_URLCONF = "conflict_analysis.production_urls"',
        'replace-with-at-least-50-random-characters-before-starting',
        'replace-with-a-strong-database-password',
        'USE_X_FORWARDED_HOST = False',
    ):
        require(token in settings, f"production settings contract is missing: {token}")
    require("django.contrib.admin" not in urls and 'path("admin/' not in urls, "production URL graph exposes admin")
    workflow = (root.parent.parent / ".github/workflows/conflict-analysis-required.yml").read_text(encoding="utf-8")
    require("python -m conflict_analysis.production_probe" in workflow, "production image job does not execute the installed runtime probe")
    require("admin_exposed" in probe and "source_tree_present" in probe, "production runtime probe is incomplete")
    require("application_wheel_sha256" in probe and "wheel_identity_present" in probe, "production wheel identity probe is incomplete")
    require('"whitenoise>=6.12,<7"' in pyproject, "WhiteNoise runtime dependency is not declared")

    build_entries = [line.strip() for line in build_lock_lines if line.strip() and not line.lstrip().startswith("#") and not line.startswith("--")]
    require("--only-binary=:all:" in build_lock_lines, "build lock must require binary wheels")
    require(len(build_entries) == 3, f"unexpected build lock size: {len(build_entries)}")
    require(
        all(re.fullmatch(r"[A-Za-z0-9_.-]+==[^=\s]+ --hash=sha256:[0-9a-f]{64}", line) for line in build_entries),
        "build lock entries must be exact and SHA-256 pinned",
    )

    lock_entries = [line.strip() for line in lock_lines if line.strip() and not line.lstrip().startswith("#") and not line.startswith("--")]
    require("--only-binary=:all:" in lock_lines, "production lock must require binary wheels")
    require(len(lock_entries) == 16, f"unexpected production lock size: {len(lock_entries)}")
    require(
        all(re.fullmatch(r"[A-Za-z0-9_.-]+==[^=\s]+ --hash=sha256:[0-9a-f]{64}", line) for line in lock_entries),
        "production lock entries must be exact and SHA-256 pinned",
    )
    require(any(line.startswith("psycopg-binary==3.3.6 ") for line in lock_entries), "Linux psycopg wheel is not locked")

    print(json.dumps({
        "status": "PASS",
        "dockerfile_frontend_digest": DOCKERFILE_FRONTEND_DIGEST,
        "python_image_digest": PYTHON_DIGEST,
        "postgres_image_digest": POSTGRES_DIGEST,
        "build_lock_entries": len(build_entries),
        "production_lock_entries": len(lock_entries),
        "admin_exposed": False,
        "source_bind_mount": False,
        "development_target_retained": True,
        "reproducible_wheel_epoch": 315_532_800,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
