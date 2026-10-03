# Zhanaozen 2011 — inherited archive-witness replay

**AI preparation only. Provenance replay; no new retrieval or substantive source review.**

Base: `7bb97104a0f70c9b2d331b955eba440e1bee35ee`. Replay ID: `ZHANAOZEN_2011_INHERITED_WITNESS_REPLAY_V1`.
This package binds 18 already preserved archive witnesses to 18 distinct PR-15 fragment-route query slots across 11 DocumentVersion blockers.
The binding is deterministic and chronological within each DocumentVersion. It does not consume live PR-15 query budget.

## What is preserved

- exact witness IDs, archive replay URLs, final URLs, capture timestamps, CDX/archive SHA-1 equality, payload SHA-256 and byte counts;
- retrieval timestamps, witness roles, proof-scope wording, literal matched fragments, and fragment SHA-256;
- all inherited `PROVEN_FRAGMENT_PRE_CUTOFF` statuses for 17 unique fragments;
- full-edition `NOT_PROVEN`, Mapping admission, target-time UNKNOWN, DISPUTED, BLOCKED, and NOT_REVIEWED states unchanged.

## Conservative replay semantics

Each record has `attempt_class=INHERITED_PRE_PROTOCOL_WITNESS_REPLAY`, `result_state=NOT_ADMISSIBLE`, and `admissibility_contract_satisfied=false` because PR-16 did not execute the frozen query or re-adjudicate the source.
`query_budget_effect=NONE_LEGACY_REPLAY`: the live PR-15 query slot remains available for a future protocol-compliant execution.
The inherited witness may remain valid fragment proof under the earlier frozen recovery, but this replay creates no new evidence claim or admission decision.
Missing inherited `content_type` and `requested_at_utc` are retained as null rather than invented.

## Hard boundaries

Network search by PR-16: NOT_EXECUTED. Substantive review by PR-16: NOT_EXECUTED. HUMAN validation: NOT_PERFORMED.
No factor values, numeric anchors, weights, HistoricalAssessment, ValidationRecord, historical UNO, outcome use, prediction, probability, risk, country rating, publication, release, or deployment.
Fragment proof remains fragment-only and never authenticates the complete historical edition or late CP3 edition identity.
Superseded company scoring values are not restored.

## Files and validation

`EXECUTED_ATTEMPT_LEDGER.json` stores the append-only replay records; `WITNESS_QUERY_BINDING.json` stores exact source/plan pointers and deterministic binding hashes.
`validate_witness_replay.py` replays PR-15 in an isolated detached worktree, checks all 18 witness digests and 17 fragment hashes, verifies exact 11-DocumentVersion coverage, rejects query reuse and edition promotion, and enforces the six-file diff boundary.

Run from the repository root:

```powershell
python -B docs/scientific/pilots/ZHANAOZEN_2011_INHERITED_WITNESS_REPLAY_V1/validate_witness_replay.py
```
