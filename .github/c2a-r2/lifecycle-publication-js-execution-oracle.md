# C2A R2 path 9/12 execution oracle — lifecycle_publication.js

Base: `22f0f173a941de88d6920b6e19821168e9b30cc8`
Target path: `software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js`
PR #94 target branch must remain immutable until the candidate is independently validated.

## R1 defects that MUST be corrected

1. `prepareAttempt()` reads `csrfToken()` during preparation and freezes `X-CSRFToken` inside `attempt.headers`; `performSealedAttempt()` later sends those frozen headers. This violates the binding split between immutable semantic request identity and fresh transport admission.
2. `importValidationTicket()` again reads and freezes CSRF in restored `attempt.headers`; imported validation replay must instead obtain current transport admission only at the actual allowed send boundary.
3. `downloadTicket()` currently calls `retainTicket("download")` immediately after `link.click()`. Download initiation is not durable retention proof and MUST NOT set `ticketRetained=true` or unlock POST.
4. R1 uses `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` for validation and publication and only imports validation tickets. Final R2 requires strict dual contracts: validation ticket permits only explicit byte-identical FD05 replay; publication ticket permits only exact FD06 operation GET recovery and can never reconstruct or enable a publication POST.

## Binding final behavior

### Validation ticket
- contract: `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1`
- operation kind: `VALIDATE_DEFINITION`
- immutable semantic request: method, route, operation UUID, project/definition identity, quoted `If-Match`, content type, exact body bytes/hash/length
- no cookie, CSRF, role, capability, credential or browser-persistent authority
- process-loss import: verify canonical ticket bytes/identity; re-read current FD03 + FD07 + current server presentation authority; only then permit explicit same-request FD05 reconciliation
- no replacement operation UUID and no automatic retry

### Publication ticket
- contract: `FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1`
- contract_version: `1.0.0`
- exact fields: `project_id`, `definition_id`, `operation_id`, `operation_kind` (`INITIAL|SUCCESSOR`), `expected_manifest_hash`, `request_body_sha256`, plus deterministic canonical representation/SHA proof required by existing authority
- process-loss import: exact identity verification followed only by `GET /api/foundation/projects/{project_id}/publication-operations/{operation_id}/`
- publication POST reconstruction/replay from a publication ticket is impossible
- validation ticket can never expose publication recovery; publication ticket can never expose FD05 replay

### Human retention proof
- `link.click()` is export initiation only and never retention proof
- POST may unlock only after either:
  1. exact-copy paste equals the canonical ticket bytes, or
  2. the HUMAN re-selects the saved ticket file and the browser verifies byte-for-byte equality to the canonical ticket
- the corrected template already exposes `ticket-file-proof` and `acknowledge-ticket-file`; bind them instead of treating download initiation as proof

### Fresh transport admission
Immediately before each allowed FD05/FD06 POST or FD05 reconciliation send:
- fresh-read current server-rendered presentation authority and exact route facts
- require the action-specific current capability
- read the current same-origin CSRF token
- build ephemeral transport headers from current CSRF + sealed semantic `Content-Type`/`If-Match`/`Idempotency-Key`
- route, UUID, `If-Match`, body bytes/hash/length remain unchanged
- missing/changed session, authority, capability or CSRF fails closed with zero mutation, no replacement UUID/ticket, no retry
- no CSRF token may be stored in sealedAttempt or either recovery ticket

## Required preservation
- no new Foundation route/model/migration/permission/package authority
- no browser persistence beyond accepted layout/preferences
- no automatic save/retry/redirect/replacement operation
- FD07 remains advice, never authority
- publication unknown outcome remains GET-only recovery
- existing exact receipt/hash/identity checks remain or become stricter; no assertion weakening
- no change to test cardinality: 13 portable + 2 Chromium

## Candidate acceptance before counting 9/12
- exact one-path `M` candidate against immutable R1
- `node --check production_studio/static/production_studio/lifecycle_publication.js` PASS
- static proof: no frozen `X-CSRFToken` inside sealed semantic attempt; no `retainTicket("download")` path; exact-copy + file re-import are the only retention unlocks; both ticket contracts are present and fail closed across kinds
- prepare one unattached Git blob/tree and report blob SHA/tree SHA
- do not update PR #94, do not commit/push target branch, no merge/rebase/cherry-pick/amend/squash/force-push/release/G10
