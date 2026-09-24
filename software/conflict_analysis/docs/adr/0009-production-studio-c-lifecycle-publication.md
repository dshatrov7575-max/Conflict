# ADR 0009: Production Studio C2A composes Foundation lifecycle publication

- Status: accepted for `CA-SUITE-I1-PRODUCTION-STUDIO-C2A-LIFECYCLE-PUBLICATION-001`
- Start: `710b88f0db9ec2f0e2fae65c7e0c77025115771a`
- Start tree: `0a15bd4d6993f87199329d0907be372aec9e69ca`
- Scope: lifecycle presentation, sealed HUMAN attempts and recovery UX

## Decision

Production Studio C2A adds a GET-only server-rendered shell:

| Method and path | Purpose |
| --- | --- |
| `GET /studio/lifecycle/definitions/<definition_id>/` | Compose one exact Foundation definition lifecycle screen |
| `GET /studio/claim-boundaries/lifecycle-publication/v1/` | Serve the immutable checksum-bound Russian C2A claims |

The view verifies the committed claim bytes before rendering, requires only a
pre-issued Django session, and ensures CSRF only for an authenticated shell
whose trusted principal has an exact mutation capability. Viewer, Player and
incoherent permission sets receive no Product-shell CSRF cookie. The view
passes exact UUID and literal Foundation route facts to the browser. Any
server-rendered capability hints come only from the trusted
`studio_principal_from_user(request.user)` derivation, fail closed for an
incoherent permission set, and remain presentation facts. The view imports no
Product model, reads no lifecycle object, performs no lifecycle inference, and
creates no `/api/studio` authority. The trusted policy symbols needed for that
derivation are its sole `domain` import; it imports no model, query, service or
Foundation DTO implementation.

The public claim route neither authenticates nor touches session state. It
returns the exact committed UTF-8 bytes, exact `Content-Length`, quoted SHA-256
ETag, `public, max-age=31536000, immutable, no-transform`, and
`X-Content-Type-Options: nosniff`. Missing, changed or malformed contract or
sidecar bytes fail closed before either lifecycle shell or public payload is
served.

## Foundation-only composition

The lifecycle browser calls only these accepted same-origin Foundation routes:

| Method and path | C2A use |
| --- | --- |
| `GET /api/foundation/definitions/<UUID>/` | Fresh persisted lifecycle and strong manifest ETag |
| `GET /api/foundation/definitions/<UUID>/publication-readiness/` | Fresh no-store advisory topology snapshot |
| `POST /api/foundation/definitions/<UUID>/validation-preview/` | Optional non-mutating preview for an initial DRAFT |
| `POST /api/foundation/definitions/<UUID>/validate/` | Exact successor validation or byte-identical reconciliation |
| `POST /api/foundation/definitions/<UUID>/publish-initial/` | Atomic validation and first publication directly from DRAFT |
| `POST /api/foundation/definitions/<UUID>/publish-successor/` | Publication of an exact validated successor |
| `GET /api/foundation/projects/<project_id>/publication-operations/<operation_id>/` | Publication response-loss recovery only |

`FOUNDATION_PUBLICATION_READINESS_V1` is advice, not authorization or a
reservation. Its `candidate_kind`, `required_next_action` and
`readiness_sha256` never become an `If-Match`. C2A obtains a fresh definition
and readiness snapshot before enabling an action and again immediately before
attempt preparation. Identity, topology or hash drift discards an unsent
preparation, renders fresh truth and performs no POST.

The exact lifecycle composition is:

```text
INITIAL
  fresh exact DRAFT + fresh INITIAL readiness
  -> optional non-mutating preview
  -> atomic initial publication directly from DRAFT

SUCCESSOR
  fresh exact DRAFT + fresh VALIDATE readiness
  -> validation or exact reconciliation
  -> fresh exact VALIDATED + fresh SUCCESSOR_PUBLISH readiness
  -> successor publication

VALIDATED with supersedes_id = null
  -> no publication action

PUBLISHED current/non-current, RETIRED and unknown states
  -> truthful immutable display; no inferred mutation action
```

The optional FD01 preview capability belongs to an exact Studio Editor through
`DRAFT_SAVE`; initial publication belongs to an exact Studio Publisher through
`DEFINITION_VALIDATE + DEFINITION_PUBLISH`. Those permission sets are not
combined. After an Editor preview, the Publisher uses its separately pre-issued
session and performs fresh FD03 and FD07 reads before preparing the atomic FD06
initial publication. Presentation facts never upgrade either role.

## Sealed attempts and HUMAN recovery

Successor validation uses exact UTF-8 `{}` bytes, one canonical UUIDv4
`Idempotency-Key` and the fresh strong manifest `If-Match`. Initial publication
uses exactly `{locale,workspace}`, where the HUMAN reviews visible `id`, `code`,
`version`, `name`, `is_default=true` and exact JSON `metadata`. Successor
publication uses exactly `{locale}`. Publication also carries one canonical
UUIDv4 operation key and the fresh strong manifest `If-Match`.

Each request is prepared as one immutable in-memory attempt. Before POST, C2A
creates a canonical `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` from that same
attempt and requires a HUMAN download or exact-copy acknowledgement. The ticket
binds operation kind, project and definition IDs, method, exact route,
operation ID, `If-Match`, body SHA-256 and body byte length. It contains no
cookie, CSRF token, credential, role, capability, actor override or receipt and
grants no authority.

Request-affecting controls freeze after preparation. Cancelling an unsent
attempt invalidates it visibly; any replacement uses a new UUID and ticket.
Headers and body are emitted only from the sealed attempt, with no late reads,
hidden defaults, alternate whitespace, regenerated UUID, automatic save,
retry, redirect or replacement key.

An unknown validation outcome permits only explicit replay of the same exact
FD05 request. After tab or process loss, importing the HUMAN-retained ticket
requires fresh definition, readiness and server-authority checks before that
same-request reconciliation is offered. A persisted `VALIDATED` state is not
proof that the missing HUMAN operation produced it.

An unknown publication outcome disables POST and permits only the accepted
project-scoped operation-recovery GET. Recovery `404` means only that the exact
operation result is not visible in the checked scope; it never proves that no
commit occurred.

## Browser and navigation boundary

C2A stores lifecycle state, manifests, hashes, roles, capabilities, operation
IDs, tickets, receipts and workspace fields only in memory. Browser persistence
remains layout/preferences only; those values never enter `localStorage`,
`sessionStorage`, IndexedDB, Cache Storage or a service worker.

C1-to-C2A navigation is disabled while an authoring request is busy or
unresolved. Dirty navigation requires explicit save or explicit discard.
`beforeunload` is advisory for dirty, busy, unresolved-write or unknown-
transport state and never performs an automatic mutation.

The checksum-bound claim contract permanently states Foundation authority,
advisory readiness, exact recovery semantics, persisted-fact limits and the
absence of scientific validity. C2B package controls, Document, Chat, formulas,
scalar Power, prediction, probability, risk, ranking and recommendations remain
unavailable.

## Consequences

C2A makes initial and successor publication demonstrable without introducing a
second lifecycle or write authority. The 13 portable contract nodes run on
PostgreSQL and SQLite; two additional lifecycle scenarios run in real Chromium
against PostgreSQL. PostgreSQL 18 remains the hosted and concurrency authority.

This decision does not authorize C2B, Windows packaging, Player, Evidence,
Experiments, model or migration changes, a release, or any Foundation contract
change.
