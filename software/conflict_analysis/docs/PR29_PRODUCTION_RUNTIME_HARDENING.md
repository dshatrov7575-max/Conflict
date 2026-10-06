# PR-29 — production runtime hardening

## Purpose

This slice creates a separate fail-closed production profile. It does not turn the scientific beta into a validated scientific system and does not alter Calculation Core, formulas, domain models, migrations, admissions or scientific results.

## Runtime boundary

Development remains available through `docker-compose.yml` and the `development` Docker target. Production uses:

- `docker-compose.prod.yml`;
- Docker target `production`;
- `conflict_analysis.production_settings`;
- `conflict_analysis.production_urls` without Django Admin;
- Gunicorn and WhiteNoise;
- PostgreSQL 18 pinned by OCI digest;
- Dockerfile frontend and Python 3.12 slim pinned by OCI digests;
- exact SHA-256 locks for build tools and production dependencies;
- a read-only application filesystem, dropped Linux capabilities and no source bind mount.

## Fail-closed settings

Production startup rejects:

- an absent or short Django secret;
- `DJANGO_DEBUG=true`;
- `USE_SQLITE=true`;
- wildcard or absent allowed hosts;
- an absent PostgreSQL password;
- the development PostgreSQL password.

Secure cookies, HTTPS redirect, HSTS, `X-Forwarded-Proto` handling, `DENY` framing and content-type/referrer protections are mandatory. The container port is loopback-bound by Compose and requires an HTTPS reverse proxy that strips any client-supplied forwarding header before setting `X-Forwarded-Proto: https`.

Authentication remains an explicit host integration boundary: this slice does not add a login or credential-collection route. Studio and Player require a Django session issued by a trusted host or upstream SSO. Therefore the profile is not claimed as a turnkey public deployment.

## Delivery

The builder creates an application wheel and all dependency wheels. The final production stage installs only from that local wheelhouse, contains no test extras and does not copy the source tree. Static assets are collected during the image build and served through WhiteNoise.

The migration service runs once after PostgreSQL becomes healthy. The web service starts only after successful migration.

## Verification contract

`scripts/verify_production_runtime.py` rejects regressions in image digests, production Docker stages, required environment values, security settings, Admin removal, source mounts and exact dependency constraints. `conflict_analysis/tests/test_production_runtime.py` executes positive and negative startup probes.

A technically green production profile establishes a hardened deployment path only. HUMAN validation, historical admission, historical area UNO and predictive validity remain unchanged and unclaimed.

## Required CI

The stable `Required product gate` now installs build and test dependencies from exact SHA-256 locks and includes a third independent job. It validates the production contract and Compose graph, builds both test wheels and the pinned production image without build isolation, runs Django's deploy checks inside a read-only non-root container, verifies that Admin and the source tree are absent, and uploads machine-readable evidence. The aggregate gate fails unless SQLite/wheel, PostgreSQL/Chromium and production-image jobs all pass.
