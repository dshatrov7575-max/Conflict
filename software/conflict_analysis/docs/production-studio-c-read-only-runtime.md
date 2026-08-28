# Production Studio C0 read-only and C1 audited-DRAFT runtime

This runbook applies to the accepted `C0_AUTHENTICATED_READ_ONLY` boundary and
the separately authorized `C1_AUTHENTICATED_DRAFT` composition. It does not
authorize C2, C3, a release or any Studio-local persistence, validation,
authorization, lifecycle, audit, Help or package authority.

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

C1 uses the same pre-issued-session hand-off and never renders a credential
form or login/logout route:

```text
GET /studio/drafts/
GET /studio/drafts/definitions/<exact UUID>/
```

Those server views are still GET-only composition. They may ensure a CSRF
cookie for the already authenticated session, but they do not issue, rotate or
refresh the session. The entry shell either accepts an exact DRAFT UUID or asks
Foundation to create the first Project and DRAFT with preselected canonical
UUIDs. The definition shell accepts only an exact UUID and lets Foundation
perform all object-scope and capability decisions.

## C1 Foundation authoring boundary

The C1 browser may use only these same-origin Foundation operations:

| Method and path | Exact purpose |
| --- | --- |
| `POST /api/foundation/projects/bootstrap-first-draft/` | Create the first Project, DRAFT, scope membership, audit and receipt atomically |
| `GET /api/foundation/definitions/<UUID>/` | Open the exact accessible definition and obtain its strong manifest ETag |
| `POST /api/foundation/definitions/<UUID>/validation-preview/` | Canonical, bounded, non-mutating preview of the in-memory proposal |
| `PUT /api/foundation/definitions/<UUID>/draft/` | Audited save using one strong `If-Match` and one canonical UUIDv4 `Idempotency-Key` |
| `GET /api/foundation/help/<ui_key>/?application=STUDIO&locale=<locale>&version=<version>` | Resolve one exact Foundation Help binding |

Bootstrap sends the exact `{project, definition}` envelope. Save sends exactly
`{manifest}`. Preview sends exactly `{manifest}` and must not carry
`Idempotency-Key` or `If-Match`. All mutations require real session CSRF, exact
JSON media type and Foundation's bounded raw-ingress parser. Actor, role,
capability, project scope and stale-token authority are never accepted from the
browser body, query or spoofable headers.

The open ETag identifies the persisted manifest. A successful save returns a
new ETag and immutable `write_receipt`. `DRAFT_STALE` and other typed 409
responses are visible conflict states; the UI neither force-overwrites nor
automatically retries. Manual reconciliation is enabled only after an ambiguous
outcome and must repeat the identical raw body, operation key and `If-Match`.
An exact replay may return `WRITE_OPERATION_RECONCILED`; changing any request
identity with a reused key is a typed key-reuse conflict.

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

C1 has a distinct and equally bounded layout key:

```text
localStorage["conflict-analysis-studio:audited-draft-layout:v1"] =
{
  version: "STUDIO_AUDITED_DRAFT_LAYOUT_V1",
  left: 220..420,
  right: 300..500,
  activeRightTab: "help"
}
```

Defaults are `left=272`, `right=360`, `activeRightTab="help"`; the exact keys
and UTF-8 JSON are limited to 256 bytes. Invalid, extra-key or out-of-range
state is removed. The in-memory DRAFT, manifest, Foundation ETag, operation
UUID, receipt, conflict and Help content must never be written to localStorage,
sessionStorage, IndexedDB, Cache Storage or a service worker.

The C1 editor renders at most 100 active actor rows and 100 analytical-element
rows even when each collection exceeds 500 items. It does not allocate an
actor-by-element matrix, aggregate/rank rows or a cross-component magnitude.
Document, Chat, scientific formula, scalar Power, prediction, probability,
risk and recommendation controls remain disabled. Exact Foundation Help is the
only help content promoted to authoritative UI.

The immutable public C1 boundary is
`GET /studio/claim-boundaries/audited-draft/v1/`. Its committed UTF-8 bytes and
SHA-256 sidecar must verify before either C1 shell renders. The boundary states
that the browser holds a proposal only, Foundation remains the sole authority,
validation is not substantive correctness, and reconciliation is not an
automatic retry.

## Platform roles and verification

The supported Windows partner role for C0 is a current Chromium browser only,
connecting over HTTPS to the hosted Linux service. Windows is not a supported
Gunicorn or PostgreSQL server authority for this slice. Browser acceptance uses
real current Chromium against a pre-issued session and checks GET-only traffic,
bounded DOM/storage, exact downloads, permanent claims and a byte-identical
database snapshot.

SQLite is an explicit local/test convenience only. The accepted current run
collects 200 Foundation nodes, with 189 passes and exactly eleven named
PostgreSQL-only skips; SQLite
does not prove row-locking, transaction interleaving or any other PostgreSQL
concurrency semantics. Delivery still requires the clean PostgreSQL 18 gate:
200 Foundation passes with no skips, the unchanged 19-node C0 regression on
both databases, all eight portable C1 contract nodes on both databases, and the
single real-Chromium C1 edit/save/reload node on PostgreSQL.

Before delivery, verify the pinned base/allowlist and unchanged `domain/` tree,
compile all packages, run Django checks and migration drift detection, execute
both database suites, validate the claim contract hash, run the Chromium smoke,
and inspect the wheel for every runtime template/static/contract asset. A failed
gate is not permission to widen C0 or C1.
