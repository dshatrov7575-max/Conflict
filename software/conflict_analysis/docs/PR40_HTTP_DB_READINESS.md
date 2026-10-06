# PR-40 — production HTTP+DB readiness

## Purpose

Replace the production web container's TCP-only healthcheck with an application
readiness contract that proves both:

1. the installed Django/Gunicorn runtime can answer HTTP through the production
   URL graph; and
2. the runtime database connection is usable.

## Endpoint

Production exposes exactly:

`GET /health/ready/`

Responses are intentionally minimal and non-sensitive:

- `200 READY\n` when a live `SELECT 1` succeeds;
- `503 NOT_READY\n` on database failure or an unexpected database result;
- non-GET methods are rejected by Django's method gate.

The response is `text/plain`, `Cache-Control: no-store`, and does not disclose
database exception text, identity, credentials, schema state or scientific data.

## Container healthcheck

The production Compose web healthcheck executes:

`python -m conflict_analysis.production_health_probe`

from the installed application wheel. The probe issues an HTTP request to the
loopback Gunicorn socket with the configured explicit Host and trusted
`X-Forwarded-Proto: https` boundary and requires exact `200 / READY\n`.

The old TCP-only `socket.create_connection` healthcheck is forbidden by the
static production verifier.

## Scope boundary

This is a readiness improvement only. It does not claim:

- liveness semantics for every downstream dependency;
- external reverse-proxy / DNS / TLS / identity-provider availability;
- monitoring, paging or SLOs;
- rollback orchestration;
- backup retention, RPO or RTO;
- scientific validity or predictive validity.

Calculation Core, formulas, HUMAN/AI isolation, scientific admission and
historical outputs are unchanged.
