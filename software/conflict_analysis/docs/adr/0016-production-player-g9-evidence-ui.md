# ADR 0016: Production Player G9 evidence UI

- Status: Accepted for the bounded G9 delivery
- Date: 2026-09-10
- Parent: `df537ee138088a1fc691cc89a257259817db4644`
- Parent tree: `67739a84d7bcc9406cbb830d9a58656b05eee06a`

## Decision

G9 adds a read-only evidence path from one exact `ParameterValue` or
`ActorElementAssessment` to its canonical evidence links and accessible Facts.
Foundation admits the exact Project, Workspace and entry lane before reading a
link to a Fact. It filters Fact visibility in the database before projection or
counting. A real zero-link result and a result containing only hidden links have
the same neutral response shape and code.

The two new GET routes return a deterministic minimal Fact list. The existing
Fact drilldown and the new list service share one Project and Fact visibility
authority. Workspace-shared Facts are visible to admitted Project members.
Owner-only Facts require exact persisted author identity. Experiment-private
Facts additionally require the exact entry experiment lane. Missing, foreign
and denied identities use one non-fingerprinting 404 boundary.

Fact type and Fact category stay separate. Category classification status is
read only from an immutable assignment and is never inferred. Entry link roles
remain separate, as do `SUPPORTS`, `REFUTES`, `CONTEXT`, `CONTEXTUALIZES` and
`CHALLENGES` in Fact evidence. A memory-origin expert assertion may have no
document and returns `NO_DOCUMENT_EVIDENCE` without a synthetic source, document
or quotation.

The accepted F1 drilldown remains the only document-evidence projection. It
resolves the exact persisted Fragment, content variant and immutable document
version. G9 renders its supplied `exact_text` directly. It shows an original
excerpt only when the drilldown supplies a complete stored checksum-bound
alignment. Partial or invalid alignment remains `ALIGNMENT_NOT_GUARANTEED` and
the original command stays disabled with the exact stated reason.

Player consumes only Foundation HTTP DTOs. It uses the inert G8
`data-ca-project-id`, `data-ca-workspace-id`, `data-ca-focus-kind` and
`data-ca-focus-id` identities. Selecting a row only records an in-memory target;
the separate RELATED command performs server authorization. History restores
exact IDs and reauthorizes them. An abort token and complete identity tuple stop
late responses after selection, workspace or permission changes.

Evidence text is inserted as text in bidi-isolating elements. External links
are limited to HTTP or HTTPS, require an explicit confirmation, and open with
`noopener,noreferrer`. Evidence and security state are never persisted in Web
Storage, IndexedDB, Cache API or a service worker. The existing G7 layout key is
unchanged.

## Consequences

This delivery adds no model, enum, migration, Product ORM query, Product cache
or parallel evidence store. It does not create or mutate evidence. It contains
no calculation, modeling, G10 or source-ingestion authority. Its complete scope
is the frozen 15 paths and its incremental registry is 8 portable Foundation,
0 PostgreSQL-only Foundation, 6 portable Product and 3 PostgreSQL Chromium
nodes.
