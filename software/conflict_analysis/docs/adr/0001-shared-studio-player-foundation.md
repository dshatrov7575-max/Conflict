# ADR 0001: Shared Studio and Player foundation

Status: accepted for `CA-SUITE-I1-FOUNDATION-001`

## Context

Conflict Analysis will expose two later user-facing entry points:

- Studio authors project definitions and publishes immutable versions.
- Player opens a workspace pinned to one exact published definition and stores
  time slices, independent assessments, evidence, help and chat history.

The desktop-like web shell is a presentation concern. Duplicating the domain,
package or persistence layer for the two entry points would make stable IDs,
workspace isolation and evidence provenance impossible to enforce consistently.

## Decision

Both entry points use the single Django `domain` application, one migration
history, one canonical package boundary and one database. A
`ProjectDefinitionVersion` is immutable after publication. A
`ProjectWorkspace` pins the exact definition ID and manifest hash; mutable
Player data belongs to that workspace and cannot change the published
definition.

Definition publication is an attributable `DRAFT -> VALIDATED -> PUBLISHED`
service transition. Validation seals the exact canonical manifest bytes and
records actor, timestamp and result; publication records its actor and creates
an immutable publication/audit record. A failed validation creates no published
snapshot, and later structural changes require a successor definition version.

Studio and Player may receive separate launch modules in later issues. Those
modules will be composition roots over the shared services and models, not
separate codebases. No product UI or launcher is implemented in this slice.

External JSON and XLS formats are replaceable adapters. They must produce the
versioned canonical DTO before validation, non-mutating preview, atomic commit
and append-only receipt. Display labels and workbook positions are never
identities.

## Consequences

- Workspace identity is part of every mutable-data and evidence boundary.
- Cross-workspace links fail closed.
- Published structure is changed only by publishing a successor definition.
- Document versions and their exact fragment anchors remain historical.
- HUMAN and AI experiments share the value model but never a value lane.
- Help and provider-neutral chat schemas can serve both future entry points.
- Formulae, scalar Power, UI, OCR, live LLM/RAG and response logic remain out
  of this foundation.
