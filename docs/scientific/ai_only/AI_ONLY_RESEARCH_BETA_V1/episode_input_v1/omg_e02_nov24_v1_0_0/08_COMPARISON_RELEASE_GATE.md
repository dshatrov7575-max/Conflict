# OMG E02 Nov23–24 V1.0.0 — deterministic comparison and release gate

**Status:** `FROZEN_BEFORE_PRIMARY_RESPONSES`  
**Input SHA-256:** `72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4`

## Valid primary identity

Required roles:
- `OMG_NOV24_V100_AI1`
- `OMG_NOV24_V100_AI2`

Each output must contain exactly four unique actor×factor entries:
- `OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR × POS_AO2`
- `OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR × KVS_AO2`
- `RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR × POS_AO2`
- `RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR × KVS_AO2`

Both outputs must have:
- route `AI_ONLY_DYAD_OMG_NOV24_V100`;
- contract `1.0.0`;
- rubric `2.1.0`;
- identical frozen input SHA;
- different non-empty run IDs;
- clean attestations;
- `calculation_release=false` for every primary entry.

## Per-entry validation

Allowed POS numeric anchors: `-10,-5,0,5,10`.  
Allowed KVS numeric anchors: `0,2,5,8,10`.

`NUMERIC` requires a licensed anchor and all C1–C8 true.

`UNKNOWN` requires `value=null` and at least one failed admission gate.

`DISPUTED` requires `value=null`.

Duplicate or missing actor×factor entries, invalid identity, invalid attestation, unlicensed number, or inconsistent status/value makes that whole primary run invalid.

## Pair comparison

For each of four actor×factor entries:

- same `NUMERIC` status, same numeric value, identical C1–C8 → `CONSENSUS_NUMERIC`;
- same `UNKNOWN/null`, identical C1–C8 → `SHARED_UNKNOWN`;
- same `DISPUTED/null`, identical C1–C8 → `SHARED_DISPUTED`;
- otherwise → `HOLD_DISAGREEMENT`.

Rationale wording and qualitative confidence need not be text-identical; they remain visible for audit but do not override status/value/C1–C8 comparison.

## Release state

If either primary run is invalid:
`REJECT_INVALID_PRIMARY_RUN`.

Else if any entry is `HOLD_DISAGREEMENT`:
`HOLD_DISAGREEMENT`.

Else if any entry is `SHARED_UNKNOWN` or `SHARED_DISPUTED`:
`HOLD_FACTOR_INCOMPLETE`.

Only if all four entries are `CONSENSUS_NUMERIC`:
`ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY`.

Eligibility is not a calculation result. A later replay requires separately stated exogenous RGU/KVPTN assumptions and the existing unchanged Calculation Core.

## Forbidden repairs

- coordinator substitution;
- targeted content review;
- averaging;
- majority vote;
- rerun-until-number;
- replacement-model shopping;
- UNKNOWN→0;
- using RGU/KVPTN to repair missing POS/KVS;
- using the known historical outcome;
- treating source editorial hostility as evidence.

## Claim boundary

Even an all-numeric consensus is only an `AI_ONLY_SAME_EVENT_MEDIATED_SOURCE_STATEMENT_DYAD`.

It is not:
- a same-time historical snapshot;
- a 15.12.2011 state;
- historical area UNO;
- HUMAN validation/reliability;
- probability, prediction, or risk validation.
