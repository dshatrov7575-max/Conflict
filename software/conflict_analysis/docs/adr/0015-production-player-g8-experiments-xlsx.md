# ADR 0015: Production Player G8 assessment experiments and XLSX import

- Status: Accepted for the bounded G8 delivery
- Date: 2026-09-09
- Parent: `f2255b6d76cf8efa46b5bea5756e09af4273b46a`
- Parent tree: `249b5e826511072c6fbcb0ea3cb7441d83c25faf`

## Decision

Foundation owns independent HUMAN and AI assessment experiments. An experiment
is an existing `Experiment` linked to one existing `AssessmentSet` and one
existing `ExpertProfile`. Its G8 lifecycle is DRAFT, FROZEN and ARCHIVED. A
profile becomes immutable after first use. FROZEN and ARCHIVED experiments
reject semantic writes. Corrections create immutable successor
`ParameterValue` rows; they never rewrite historical values.

`ParameterValue` is the sole numeric lane. Per-parameter categorical confidence
and role/source lineage live in the existing assessment provenance structure.
This delivery changes model behavior only: it adds no field, enum, table or
migration. Raw comparison returns each persisted value and its experiment
identity without aggregation, fill, ranking or winner selection.

The existing named workspace route
`player/workspaces/<workspace_id>/experiments/` is the only collection route.
Its accepted G7 GET behavior remains available, and its G8 handler adds the
authorized GET and POST behavior. All writes require an authenticated session,
the exact assessment permission family, project scope, real CSRF validation,
strong preconditions and a caller supplied UUID operation key. Same-key replay
is resolved before mutable-state rejection and remains bound to the request,
principal, project, workspace and experiment.

XLSX preview and import use the single `domain.services.xlsx_adapter` parser.
The adapter bounds archive size, entry counts, decompression, XML depth and text
size, rejects active content and external XML constructs, and rejects every
formula cell even when a cached value exists. Preview performs zero database
writes. Import reparses the same bytes inside the operation, validates the
checksum-bound preview and ticket, then atomically persists the import graph or
nothing.

The Zhаnaozen profile enumerates exactly 330 source identities. The pinned
bridge maps `АК-01..АК-08` to `GU-01..GU-08`, `КВК-01..КВК-06` to
`PTN-01..PTN-06`, and the three cutoffs to their exact `TimeSlice` codes. Role
identity comes only from the unique published manifest role record for the
actor/element pair. `POS` and `SAL` are canonical value targets. The 18 ESW
rows remain `METHOD_BLOCKED`; the 24 POW rows remain `RECODING_REQUIRED`.

`POLARIZATION_V1_IMPORT_SNAPSHOT_V1` is an immutable receipt snapshot only when
the uploaded file contains the complete 330-row identity set. Its checksum and
byte length describe the actual uploaded XLSX. The fixed A5 workbook checksum
remains separate source-classification lineage. Partial files never claim the
complete snapshot contract. Snapshot rows do not form a second value store.

## Consequences

The bounded G8 delivery creates no Fact, Document or Fragment data, exposes no
evidence API, writes no Product ORM state and provides no calculation or
modeling implementation. G9 identifiers occur only as inert focus identifiers
inside the authorized Product contract nodes. The accepted R2 commit is the
immediate runtime parent while the repository `G7_ACCEPTED_HEAD` and
`G7_ACCEPTED_TREE` variables preserve the accepted G7 lineage proof.
