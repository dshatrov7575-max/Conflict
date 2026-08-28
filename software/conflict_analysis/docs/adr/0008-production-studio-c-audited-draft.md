# ADR 0008: Production Studio C1 composes audited Foundation DRAFT authoring

- Status: accepted for `CA-SUITE-I1-PRODUCTION-STUDIO-C1-AUTHENTICATED-DRAFT-001`
- Start: `bd6e88c2a5f6552e057ea5b49fc63a1eb77ef4c6`
- Start tree: `e1124839da8571408c258517c8afdf24622f1655`
- Scope: authenticated C1 composition, presentation and browser proposal state

## Decision

Production Studio C1 adds a same-origin Russian three-panel DRAFT editor while
retaining Foundation as the sole persistence, authorization, object-scope,
lifecycle, validation, audit, Help and package authority. Studio remains a
model-free composition application: it adds no ORM model, migration, permission
system, session issuer, package builder, validator or `/api/studio` mutation
alias.

The C1 Studio server surface is GET-only:

| Method and path | Purpose |
| --- | --- |
| `GET /studio/drafts/` | Pre-issued-session bootstrap or exact-UUID entry shell |
| `GET /studio/drafts/definitions/<definition_id>/` | Exact DRAFT authoring shell |
| `GET /studio/claim-boundaries/audited-draft/v1/` | Immutable public Russian claim contract |

Anonymous shell requests receive a fixed 401 state with no credential form or
redirect. Authenticated shell views may ensure the CSRF cookie required by the
canonical Foundation gateway, but never create or rotate the Django session.
The public claim route does not inspect session state and serves exact committed
bytes with immutable cache headers, a quoted SHA-256 ETag and no cookie.

## Foundation-only writes

The entry shell calls only
`POST /api/foundation/projects/bootstrap-first-draft/` with the exact
`{project, definition}` envelope, preselected UUID identities and a canonical
UUIDv4 `Idempotency-Key`. Foundation atomically creates the Project, DRAFT,
object-scope membership and immutable audit receipt. An exact-ID open uses
`GET /api/foundation/definitions/<UUID>/` and accepts the returned manifest hash
and quoted ETag as the sole persisted DRAFT identity.

The definition shell keeps a proposal in browser memory. Canonical preview uses
`POST /api/foundation/definitions/<UUID>/validation-preview/` with exactly
`{manifest}`, real CSRF and no operation key or `If-Match`; it cannot write the
definition or AuditEvent. Save uses
`PUT /api/foundation/definitions/<UUID>/draft/` with exactly `{manifest}`, real
CSRF, one strong quoted Foundation ETag and one canonical UUIDv4
`Idempotency-Key`. The successful Foundation payload and immutable
`write_receipt` replace the in-memory proposal identity.

Typed 409 outcomes are not collapsed into generic errors. In particular,
`DRAFT_STALE` requires reload or explicit user resolution; Studio never sends a
force overwrite. There is no automatic write retry. A manual reconciliation
control is enabled only after an ambiguous outcome and repeats the exact raw
body, operation key and `If-Match`; Foundation decides whether that identity is
an exact replay or a typed key-reuse conflict.

## Bounded editor and truthful features

Project name and description are labelled as the proposal's Project snapshot.
Actors and analytical elements retain exact UUID identity and order and support
add, delete, rename and reorder. Each collection renders a maximum active window
of 100 rows even above 500 records. No actor-by-element cross-product, rank,
total/average row, heatmap, scalar Power or risk badge is allocated.

Exact Foundation Help is requested only from a complete manifest binding tuple.
Missing or mismatched Help remains unavailable; Studio has no authoritative
fallback. Document, Chat, scientific formula, prediction and recommendation
controls are disabled. Validation reports schema conformance and diagnostics,
not substantive correctness, scientific validity or a recommendation.

## State and claims

The only browser persistence is the bounded layout object:

```text
localStorage["conflict-analysis-studio:audited-draft-layout:v1"] =
{
  version: "STUDIO_AUDITED_DRAFT_LAYOUT_V1",
  left: 220..420,
  right: 300..500,
  activeRightTab: "help"
}
```

Its exact-key UTF-8 JSON is at most 256 bytes. Manifest, Project/definition
identity, ETag, operation key, receipt, conflict and Help content remain absent
from all browser persistence. Malformed, oversized, extra-key and out-of-range
layout values are removed.

The versioned Russian claim contract
`STUDIO_AUDITED_DRAFT_CLAIM_BOUNDARIES_V1` is checksum-bound and visible in
both shells. It permanently states Foundation authority, proposal-only browser
memory, attribution limits, exact reconciliation, validation limits, disabled
features and separation from the partner-visible Showcase baseline.

## Consequences

C1 can be exercised end to end with a real current Chromium browser: open more
than 500 actors and analytical elements without DOM exhaustion, edit and
preview without server mutation, observe a typed stale conflict without retry,
save with a Foundation receipt, and reload the persisted DRAFT. PostgreSQL 18
remains the concurrency and integration authority; SQLite is only a portable
contract convenience.

This decision does not authorize publication, Document evidence authoring,
Chat, formulas, prediction, risk, ranking, recommendation, launcher or release
work. A requirement for new model, migration, schema or Foundation service
semantics returns to MAIN rather than being implemented inside Studio.
