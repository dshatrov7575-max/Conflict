# OMG Company Decision V1.0.2 — post-run release gate

**Status:** `FROZEN_BEFORE_PRIMARY_RESPONSES`  
**Route:** `AI_ONLY_DYAD_OMG_E1_V102`  
**Evidence input SHA-256:** `34a70bb18664a8ccf5fb5713dd90bbebe32a1a60d17303603e4cb7d84d961f42`

## Required primary outputs

- `OMG_COMPANY_E1_V102_AI1`: exactly two company entries, `POS_AO2` and `KVS_AO2`;
- `OMG_COMPANY_E1_V102_AI2`: the same two entries from an independent run;
- identical route, contract, rubric and evidence-input identities;
- clean attestations; external search and prior outputs prohibited;
- primary `calculation_release=false` in every entry.

## Deterministic comparison

For each factor:

- same `NUMERIC` value and identical C1–C8 → `CONSENSUS_NUMERIC`;
- same `UNKNOWN` and identical C1–C8 → `SHARED_UNKNOWN`;
- same `DISPUTED` and identical C1–C8 → `SHARED_DISPUTED`;
- every other pairing → `HOLD_DISAGREEMENT`.

Coordinator substitution, averaging, majority vote, rerun-until-number and targeted content review are forbidden.

## Calculation gate

A read-only dyad scenario replay is permitted only when **both** company entries are `CONSENSUS_NUMERIC`. The inherited worker values are fixed at `POS=-5`, `KVS=5` from V1.0.1 and are not recoded.

Any company `UNKNOWN`, `DISPUTED`, status/value mismatch or C1–C8 mismatch produces:

`HOLD_FACTOR_INCOMPLETE`

No RGU/KVPTN choice may repair a missing company factor. `UNKNOWN != 0`.

## Output boundary

An eligible calculation remains a non-simultaneous demand→formal-response dyad scenario. It is not a same-date snapshot, a 15.12.2011 state, historical area UNO, HUMAN validation, probability, prediction or risk estimate.
