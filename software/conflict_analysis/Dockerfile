# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS development
COPY . .
RUN python -m pip install -e ".[dev]" \
    && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS wheel-builder
WORKDIR /build
COPY . .
RUN python -m pip install --require-hashes --only-binary=:all: \
      --requirement requirements/build-lock.txt
RUN --network=none python scripts/build_reproducible_wheel.py \
      --project-root /build \
      --output-dir /wheels \
      --metadata-out /wheels/conflict-application-wheel.json
RUN python -m pip download --require-hashes --only-binary=:all: \
      --dest /wheels \
      --requirement requirements/production-lock.txt

FROM base AS production
ENV DJANGO_SETTINGS_MODULE=conflict_analysis.production_settings \
    DJANGO_STATIC_ROOT=/app/staticfiles
COPY --from=wheel-builder /wheels /wheels
COPY --from=wheel-builder /wheels/conflict-application-wheel.json /app/conflict-application-wheel.json
COPY --from=wheel-builder /build/requirements/production-lock.txt /tmp/production-lock.txt
RUN --network=none python -m pip install --no-index --find-links=/wheels --require-hashes \
      --requirement /tmp/production-lock.txt \
    && python -m pip install --no-index --no-deps \
      /wheels/conflict_analysis-0.1.0-py3-none-any.whl \
    && python -m pip check \
    && DJANGO_SECRET_KEY=build-only-not-secret-build-only-not-secret-build-only-not-secret-1234 \
       DJANGO_ALLOWED_HOSTS=localhost \
       FD08_PROJECTION_LEASE_SECRET=build-only-fd08-projection-capability-not-secret-123456 \
       UPSTREAM_AUTH_SHARED_SECRET=build-only-upstream-auth-secret-not-secret-123456 \
       POSTGRES_DB=build_only \
       POSTGRES_USER=build_only \
       POSTGRES_PASSWORD=build-only-database-password-not-secret \
       POSTGRES_HOST=localhost \
       python -m django check --deploy --fail-level WARNING \
    && DJANGO_SECRET_KEY=build-only-not-secret-build-only-not-secret-build-only-not-secret-1234 \
       DJANGO_ALLOWED_HOSTS=localhost \
       FD08_PROJECTION_LEASE_SECRET=build-only-fd08-projection-capability-not-secret-123456 \
       UPSTREAM_AUTH_SHARED_SECRET=build-only-upstream-auth-secret-not-secret-123456 \
       POSTGRES_DB=build_only \
       POSTGRES_USER=build_only \
       POSTGRES_PASSWORD=build-only-database-password-not-secret \
       POSTGRES_HOST=localhost \
       python -m django collectstatic --noinput --clear \
    && rm -rf /wheels /tmp/production-lock.txt \
    && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "conflict_analysis.wsgi:application", "--bind=0.0.0.0:8000", "--access-logfile=-", "--error-logfile=-"]
