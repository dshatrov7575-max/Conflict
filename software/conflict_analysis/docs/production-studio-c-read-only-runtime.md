# Production Studio C0, C1 and C2A runtime

This runbook applies to the accepted `C0_AUTHENTICATED_READ_ONLY` boundary and
the separately authorized `C1_AUTHENTICATED_DRAFT` composition and the bounded
`C2A_LIFECYCLE_PUBLICATION` composition. It does not authorize C2B, C3, a
release or any Studio-local persistence, validation,
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

C2A uses that same hand-off. Its server view is also GET-only and may ensure a
CSRF cookie only for an authenticated lifecycle shell whose trusted exact
Editor or Publisher principal has a mutation capability. Viewer, Player and
incoherent permission sets receive no Product-shell CSRF cookie:

```text
GET /studio/lifecycle/definitions/<exact UUID>/
GET /studio/claim-boundaries/lifecycle-publication/v1/
```

The claim route is public, immutable and session-free. The lifecycle view does
not read a definition or infer a lifecycle state. It passes literal Foundation
route facts and presentation-only capability hints derived only through
`studio_principal_from_user`, `StudioCapability` and the fail-closed
`StudioAuthorizationDenied` policy seam. Foundation repeats authentication,
exact object scope, capability, stale-state and transaction checks for every
operation.

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

## C2A lifecycle and publication boundary

Before enabling a lifecycle action and again before preparing it, the browser
must fetch both the exact Foundation definition and its fresh no-store
`publication-readiness` snapshot. Readiness is advisory: its action, topology
and hash neither grant capability nor reserve a write and are never sent as
`If-Match`. Drift discards an unsent attempt and causes no mutation.

Initial publication is possible only for a fresh exact INITIAL DRAFT selected
by readiness. The HUMAN may run a non-mutating Foundation preview, then the
initial Foundation route validates and publishes that DRAFT atomically. C2A
must not validate an initial DRAFT first. A successor DRAFT uses exact FD05
validation, fresh definition/readiness rereads, and only then exact FD06
successor publication. A standalone DRAFT in a published Project, a VALIDATED
definition without a predecessor, current/non-current PUBLISHED, RETIRED and
unknown lifecycle values expose no inferred publication action.

FD01 preview is optional and available only to the exact Editor capability
`DRAFT_SAVE`. Atomic initial publication is available only to the exact
Publisher capabilities `DEFINITION_VALIDATE + DEFINITION_PUBLISH`. Studio does
not combine or upgrade those roles: after an Editor preview, a separately
pre-issued Publisher session performs fresh FD03 and FD07 reads before attempt
preparation.

Validation uses exact UTF-8 `{}` bytes. Initial publication sends exactly
`{locale,workspace}` with visible HUMAN-reviewed `id`, `code`, `version`,
`name`, `is_default=true` and JSON `metadata`; successor publication sends
exactly `{locale}`. Every semantic write attempt uses one visible canonical
UUIDv4 operation key, an exact action-specific route and the fresh strong
Foundation manifest ETag.

Validation and publication use different non-authoritative tickets:

```text
VALIDATION
contract = FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1
operation_kind = VALIDATE_DEFINITION
unknown outcome = explicit byte-identical FD05 POST reconciliation only
process-loss recovery = ticket import -> fresh FD03 + FD07 + server authority -> exact same-request replay

PUBLICATION
contract = FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1
operation_kind = INITIAL | SUCCESSOR
unknown outcome = exact project/operation Foundation GET only
publication POST reconstruction or replay = forbidden
```

A ticket binds its exact operation kind, project and definition UUIDs, method,
route, operation UUID, `If-Match`, body SHA-256 and byte length. It contains no
cookie, CSRF token, credential, role, capability, actor override or receipt and
grants no authority. A validation ticket cannot expose publication recovery; a
publication ticket cannot expose FD05 replay.

Starting a file download is only an export action and never proves retention.
POST remains disabled until the HUMAN either pastes an exact byte-for-byte copy
of the canonical ticket or re-imports and verifies the exact downloaded file.
Cancelling an unsent attempt invalidates it; any replacement uses a new UUID and
ticket.

Immediately before every permitted FD05/FD06 POST or FD05 reconciliation, C2A
fresh-reads the server-rendered presentation facts, rechecks the exact current
capability and route, then reads the current same-origin CSRF token. CSRF is an
ephemeral transport admission fact and is never sealed into the semantic
attempt or ticket. The operation UUID, route, `If-Match`, body bytes, hash and
length remain byte-identical. Missing or rotated session/capability/route facts
fail closed without a replacement UUID or automatic retry.

The only accepted action routes are exact:

```text
VALIDATE_DEFINITION -> /api/foundation/definitions/{definition_id}/validate/
PUBLISH_INITIAL -> /api/foundation/definitions/{definition_id}/publish-initial/
PUBLISH_SUCCESSOR -> /api/foundation/definitions/{definition_id}/publish-successor/
```

DOM, dataset, action, definition or recovery-template tampering must produce a
bounded state and zero Foundation mutation requests. Arbitrary server `code`
values or exception/detail prose are never rendered directly; a finite,
operation/status-compatible map distinguishes capability, session, inaccessible
404, envelope/validation 400, stale/state/key conflicts, unknown transport,
unverified success and ambiguous recovery 404 states.

Publication receipt verification is channel-specific and the channels are not
substitutes:

```text
fresh FD06 POST = 201 + Idempotency-Replayed:false
exact reconciled FD06 result = 200 + Idempotency-Replayed:true
operation-recovery GET = 200 + Idempotency-Replayed:true + recovery-only no-store/scoped-Vary contract
```

All channels retain exact canonical body, receipt, definition, operation,
request hash, ETag and Location verification. A malformed, truncated or
identity-mismatched success remains unknown/unverified and cannot be promoted to
committed. Recovery 404 is not proof that no commit occurred. No write is
automatically saved, retried, redirected or assigned a replacement key.

C1-to-C2A navigation is disabled while busy or unresolved, and dirty
navigation requires explicit save or discard. `beforeunload` guards dirty,
busy, unresolved-write and unknown-transport states only as advisory browser
UX. No unload handler sends a mutation.

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

The immutable public C2A boundary is
`GET /studio/claim-boundaries/lifecycle-publication/v1/`. Its committed UTF-8
bytes and SHA-256 sidecar verify before the lifecycle shell renders. C2A does
not persist definitions, hashes, lifecycle/readiness state, roles,
capabilities, operation IDs, tickets, receipts or workspace fields in
localStorage, sessionStorage, IndexedDB, Cache Storage or service workers.
Package C2B, Document, Chat, formulas, scalar Power, prediction, probability,
risk, ranking and recommendation controls remain unavailable.

## Platform roles and verification

The supported Windows partner role is a Chromium browser connecting over HTTPS
to the hosted Linux service. Windows is not a supported Gunicorn or PostgreSQL
server authority for these slices. CI browser acceptance uses the pinned
Chrome-for-Testing `152.0.7977.64` Linux archive with one exact SHA-256 enforced
before extraction by the workflow and verifier. This is a deterministic
regression browser, not a dynamically current browser. Acceptance checks exact
same-origin traffic, bounded DOM/storage, permanent claims, response-channel
contracts and database effects.

SQLite is an explicit local/test convenience only and does not prove row
locking, transaction interleaving or any PostgreSQL concurrency semantics. The
complete delivery accounting is:

```text
Foundation PostgreSQL 18 = 350/350 PASS
Foundation SQLite = 322 PASS + exact 28 inherited PostgreSQL-only skips
Product PostgreSQL 18 = 68/68 PASS
Product SQLite = 68/68 PASS
PostgreSQL real-Chromium registry = 10/10 PASS, including C2A 2/2
```

Before delivery, verify the exact accepted G9 base, immutable R1, two-commit C2A
R2 topology, exact 12-path all-`M` correction delta, exact 19-path aggregate,
accepted preimages and frozen surfaces. Compile all packages, run Django checks
and migration drift detection, execute both database suites, validate claim
contract hashes, run the pinned Chromium registries, and inspect the wheel for
every runtime template/static/contract asset. A failed gate is not permission
to widen C0, C1 or C2A.