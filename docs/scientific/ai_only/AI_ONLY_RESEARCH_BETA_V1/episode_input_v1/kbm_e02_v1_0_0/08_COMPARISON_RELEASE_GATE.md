# KBM E02 V1.0.0 — comparison and release gate

**Status:** `FROZEN_BEFORE_PRIMARY_RESPONSES`  
**Input SHA-256:** `d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42`

## Required primary outputs

- `KBM_COMPANY_E02_V100_AI1`: exactly two company entries.
- `KBM_COMPANY_E02_V100_AI2`: exactly two company entries.
- Identical route, contract, rubric and input SHA.
- Different non-empty run IDs.
- Clean attestations: other output, prior episode outputs, outcome and external sources all unseen/unused.
- Each primary entry must keep `calculation_release=false`.

## Deterministic comparison

For each factor:
- same `NUMERIC` value + identical C1-C8 -> `CONSENSUS_NUMERIC`;
- same `UNKNOWN/null` + identical C1-C8 -> `SHARED_UNKNOWN`;
- same `DISPUTED/null` + identical C1-C8 -> `SHARED_DISPUTED`;
- every other pairing -> `HOLD_DISAGREEMENT`.

Coordinator substitution, targeted content review, averaging, voting, rerun-until-number and replacement-model shopping are forbidden.

## Dyad gate

Worker record is internally inherited from R2 `AO2S-C1-03` only after company comparison:
- worker POS = `-5`;
- worker KVS = `5`;
- source-report date = `2011-05-17`;
- no carry-forward.

A read-only dyad scenario replay is eligible **only if both company factors are CONSENSUS_NUMERIC**. Any company UNKNOWN/DISPUTED/mismatch/invalid attestation keeps the result non-computable.

The result, even if computable, remains a non-simultaneous demand→formal-response dyad scenario. It is not a 15.12.2011 snapshot, historical area UNO, HUMAN validation, probability, prediction or risk validation.

`UNKNOWN != 0`; exogenous RGU/KVPTN may not repair missing POS/KVS.
