# Foundation package 2.0.0

The Foundation import boundary is transport-independent:

```text
external JSON/XLS
  -> canonical versioned DTO
  -> JSON Schema and semantic validation
  -> non-mutating preview
  -> atomic commit
  -> append-only ImportRun receipt
```

The canonical format preserves stable IDs and exact workspace/definition,
dataset, ontology, method, schema and template versions. Re-import cannot
silently overwrite a non-empty target. HUMAN and AI input is selected for one
explicit Experiment/AssessmentSet; there is no fill-across or automatic
consensus.

Every successful JSON preview and immutable receipt also keeps transport
provenance separate from the canonical semantic package checksum:
`PATH_BYTES`, `BYTES`, and `TEXT` hash the exact supplied bytes, while
`CANONICAL_MAPPING` hashes deterministic canonical JSON and explicitly makes no
claim about unavailable original transport bytes. Commit uses the previewed
snapshot and never re-reads a mutable input path.

Evidence follows one canonical path:

```text
ParameterValue / ActorElementAssessment
  -> Fact
  -> TextFragment
  -> immutable DocumentVersion
  -> Document
  -> Source
```

An unresolved legacy `EvidenceSource`/`EvidenceLink` is represented by an
explicit compatibility receipt until a complete exact chain is available. A
URL or fragment checksum is never promoted to a full DocumentVersion checksum.
Anchor mismatch fails atomically and never triggers silent re-anchoring.

Power components `FA`, `ER`, `OC`, `CC`, `AL`, `IC`, `NI`, and `EB` are stored
as separate records with their own status and provenance. The package does not
define total/scalar Power, automatic means or weights, prediction, risk, or a
calculation formula.

## Legacy 1.0.0 compatibility boundary

The legacy `project-package-1.0.0` schema is retained unchanged. Its
`evidence_sources` and `evidence_links` sections are
`LEGACY_COMPATIBILITY_ONLY`: they are never a second authoritative evidence
chain. Import preserves those rows for historical round trips and emits an
explicit `UNRESOLVED` compatibility receipt/data gap until the exact canonical
chain exists:

```text
Source
  -> Document
  -> immutable DocumentVersion (with captured DocumentContent)
  -> TextFragment
  -> Fact
  -> Assessment/ParameterValue
```

The v1 importer never fabricates any node or link in that canonical chain from
a URL, legacy source, or legacy link. Foundation 2.0.0 export exposes only the
canonical sections plus explicit compatibility receipts; it does not export
the v1 evidence sections.

The v1 `scenarios` and `scenario_overrides` sections are historical
compatibility residue only. Their retention does not authorize product
scenarios, a modelling engine, calculations, prediction, ranking, or
recommendations. The explicit upgrade path creates a deterministic default
workspace and compatibility receipts; a 1.0.0 payload is never silently
treated as 2.0.0.

## Bound external contracts

The canonical DTO is adapter-independent. The first pilot adapter is bound to
`ZHANAOZEN_V4_EVIDENCE_PACKAGE_SPEC_V1` (Google Doc
`1eaRA29j41kv_O5BeruHkUy9KlHbjDhMNHgFxL7avmeA`, JSON Schema SHA-256
`df125668d2664abbd59e4bc619f09263e339032f0414cf4378da2986c5d561d5`).
The XLS profile is `V4_EXPERT_XLS_IMPORT_CONTRACT_PRE_FREEZE_V1` (Google Doc
`1vnWF2dXe7SimOj8Jvh5gXbRG_9HWKU7PvJLFZi7mRpw`, specification SHA-256
`f9d0c193c9d6b36e8f035ec24c1a265b06ef9120cc91399b93f40ac87e0067b9`,
field-contract SHA-256
`b0d12d36dd011d88cabd593e980e94090e828bba66427aa06cae6adb90eae474`).
These hashes identify adapter contracts; neither external file layout defines
the ORM schema.

External non-UUID identifiers are preserved byte-for-byte as canonical stable
`code` values. Internal UUID primary keys are a separate deterministic identity
layer, and the import receipt records the exact code-to-UUID mapping. Display
labels, including Russian labels, never select an import identity.

## Commands

Preview is the default and does not mutate the database:

```text
python manage.py import_foundation_package PACKAGE --workspace WORKSPACE_UUID --adapter json
python manage.py import_foundation_package WORKBOOK.xlsx --workspace WORKSPACE_UUID --adapter xlsx
```

An explicit attributable commit reuses the exact immutable preview policy and
creates an append-only receipt:

```text
python manage.py import_foundation_package PACKAGE --workspace WORKSPACE_UUID --adapter json --commit --actor ACTOR_ID
python manage.py export_foundation_package WORKSPACE_UUID OUTPUT.json
```
