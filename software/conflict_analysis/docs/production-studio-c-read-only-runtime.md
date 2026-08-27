# Production Studio C0 read-only runtime

This runbook applies only to `C0_AUTHENTICATED_READ_ONLY`. It does not authorize
C1, C2, C3, a Foundation dependency task, a release or a write-capable Studio.

## Hosted authority

The supported hosted role is Linux with CPython 3.12, Django 5.2, Gunicorn 23
and PostgreSQL 18. PostgreSQL 18 is the sole hosted and integration database
authority. Start the WSGI process from `software/conflict_analysis` only after
applying the accepted migrations:

```bash
python manage.py migrate --noinput
python manage.py check
gunicorn --bind 127.0.0.1:8000 conflict_analysis.wsgi:application
```

Terminate public HTTPS at a trusted reverse proxy. The proxy must replace,
rather than append to, forwarding headers; set the canonical Host; forward
`X-Forwarded-Proto: https`; reject untrusted direct public access to Gunicorn;
and apply bounded request/header timeouts. Configure Django's trusted hosts,
secure session and CSRF cookies, HTTPS redirect/HSTS and proxy SSL header for
that deployment. Static assets are collected and served by the proxy or a
trusted static-file service:

```bash
python manage.py collectstatic --noinput
```

Never expose the development server as the hosted role. Secrets, database
credentials and trusted proxy values belong in the deployment secret/config
system, not source control.

## Authentication hand-off

Studio C0 does not collect credentials and has no login, logout or session
issuance endpoint. Before a measured flow, the hosting authentication system
must issue the user's Django session out of band. The browser then opens:

```text
GET /studio/
GET /studio/definitions/<exact UUID>/
```

Starting entry or definition navigation with a session-less browser is expected
to produce the fixed 401 state. The public claim-contract GET neither inspects
nor changes session state. Do not make a Studio shell view create, rotate or
refresh a session. The measured flow must leave `django_session`,
`auth_user.last_login`, every `domain_*` row and every AuditEvent unchanged.

## Read-only network boundary

The client reads the exact definition through
`GET /api/foundation/definitions/<UUID>/`. It may also download
`GET /api/foundation/definitions/<UUID>/package/2.1/`. It requests Help only
when the manifest carries a complete exact STUDIO binding:

```text
GET /api/foundation/help/<ui_key>/?application=STUDIO&locale=<locale>&version=<topic_version>
```

Missing or mismatched Help remains visibly unavailable; there is no local
authoritative fallback. `Документ` evidence is unavailable in C0. The client
must not issue a Foundation `POST`, `PUT`, `PATCH`, `DELETE` or `HEAD`, and must
not call a Studio mutation alias. All application fetches use same-origin
credentials and no-store caching.

The export download is accepted only as Foundation's exact representation:
bytes and terminal newline, `Content-Disposition` filename, quoted ETag and
`X-Foundation-Semantic-Payload-SHA256` remain distinct verified identities.

## Browser storage and visible limitations

The only application localStorage entry is
`conflict-analysis-studio:read-only-layout:v1`, with schema
`{version:"STUDIO_READ_ONLY_LAYOUT_V1", left, right, activeRightTab}`. Defaults
are `272 / 360 / document`; left is bounded to 220–420, right to 300–500, the
tab is `document|chat|help`, and serialized UTF-8 is at most 256 bytes. Invalid
state resets. No domain/project/evidence identity, manifest, Help, claim copy or
session material may be persisted in browser storage.

The permanent banner, limitations panel, disabled Chat/scientific controls,
noscript text and downloadable checksum-bound claim contract are part of the
operational boundary. Do not remove or hide them. C0 does not claim substantive
correctness or scientific validation and offers no aggregation/ranking,
formula, scalar Power, prediction, probability, risk or recommendation.

## Platform roles and verification

The supported Windows partner role for C0 is a current Chromium browser only,
connecting over HTTPS to the hosted Linux service. Windows is not a supported
Gunicorn or PostgreSQL server authority for this slice. Browser acceptance uses
real current Chromium against a pre-issued session and checks GET-only traffic,
bounded DOM/storage, exact downloads, permanent claims and a byte-identical
database snapshot.

SQLite is an explicit local/test convenience only. Its accepted C0 run preserves
169 Foundation passes and exactly six named PostgreSQL-only skips, but SQLite
does not prove row-locking, transaction interleaving or any other PostgreSQL
concurrency semantics. Delivery still requires the clean PostgreSQL 18 gate:
the 175-test Foundation baseline with no unexpected skips plus all C0 tests.

Before delivery, verify the pinned base/allowlist and unchanged `domain/` tree,
compile all packages, run Django checks and migration drift detection, execute
both database suites, validate the claim contract hash, run the Chromium smoke,
and inspect the wheel for every runtime template/static/contract asset. A failed
gate is not permission to widen C0.
