# MVP7 OMG Episode E1 — Exogenous Weight Design V1

**Status:** `FROZEN_BEFORE_EPISODE_PRIMARY_RESPONSES`  
**Scope:** `OMG_INITIAL_WAGE_DISPUTE_2011_05_26_2011_06_28`  
**PTN:** `E02_PAY`  
**Actors:** `OMG_WORKERS_INITIAL_STRIKE`, `KMG_EP_MANAGEMENT_FORMAL_RESPONSE`

## 1. Purpose and scientific boundary

This document fixes the exogenous RGU/KVPTN design before the episode factor
answers are compared. It implements the owner-approved semantics:

- POS and KVS are measured content variables.
- RGU and KVPTN are exogenous analytic design weights.
- No Evidence, source frequency, group size, office, influence, resources,
  capability, outcome, confidence, or model agreement is converted into RGU or
  KVPTN.
- The design does not assert equal real-world power or equal real-world
  importance.
- No historical December snapshot and no historical area-level UNO are created.

The episode has one PTN and two evidence-supported actor identities. The weight
design is therefore a scenario/sensitivity layer for the episode only. It does
not modify `POLARIZATION_V1_BETA / 1.0.0`.

## 2. Release gate before any calculation

A scenario run is permitted only if all four episode factor entries are
`VERIFIED_NUMERIC` after:

1. two independent primary AI outputs;
2. deterministic comparison;
3. no more than one targeted review round;
4. coordinator evidence/rubric verification;
5. preservation of original primary outputs.

Required entries:

- worker POS;
- worker KVS;
- company POS;
- company KVS.

If any entry is UNKNOWN or DISPUTED, the episode result is
`NOT_COMPUTABLE`. No missing value is replaced by zero, a baseline, an average,
the other actor's value, or a value from a different date.

## 3. Equal-positive baseline

The baseline is an analytic normalization:

- `RGU_worker = 1`
- `RGU_company = 1`
- `KVPTN_E02 = 1`

These values are not empirical assessments. Choosing 1 rather than another
common positive constant is only a normalization convention: common positive
rescaling of all actor weights or the sole PTN weight cancels in the relevant
normalization.

The baseline is not automatically the main scientific result. It is the center
of the preregistered sensitivity family.

## 4. Main positive-weight RGU family

The main family keeps both actors in scope and varies only their relative RGU:

| Scenario | Worker RGU | Company RGU | Relative company/worker |
|---|---:|---:|---:|
| `WORKER_DOMINANT_10_1` | 10 | 1 | 0.1 |
| `WORKER_DOMINANT_4_1` | 4 | 1 | 0.25 |
| `WORKER_DOMINANT_2_1` | 2 | 1 | 0.5 |
| `EQUAL_1_1` | 1 | 1 | 1 |
| `COMPANY_DOMINANT_1_2` | 1 | 2 | 2 |
| `COMPANY_DOMINANT_1_4` | 1 | 4 | 4 |
| `COMPANY_DOMINANT_1_10` | 1 | 10 | 10 |

All weights remain positive. The actor universe, POS/KVS values, PTN identity,
episode boundary, source material, and Calculation Core remain fixed.

## 5. KVPTN topology limitation

There is only one PTN. For any positive `q`, the Core's normalized one-PTN
aggregate is algebraically invariant to the absolute q scale. Therefore:

- positive q values `0.1`, `1`, and `10` are checked as an implementation
  invariance test;
- this is not substantive KVPTN sensitivity;
- there is no nontrivial relative q design in a one-PTN topology;
- no claim of area-level robustness is allowed.

`q = 0` is a separate coverage-exclusion stress case. It changes the estimand
and makes the area aggregate unavailable; it is not part of the main positive
sensitivity envelope.

## 6. Zero-weight coverage stresses

The following are reported separately and are never used as a preferred result:

- worker RGU = 0;
- company RGU = 0;
- both RGU = 0;
- sole PTN q = 0.

These stresses show how exclusion or a zero denominator can hide one side or
make the result unavailable. They do not represent unknown as zero.

## 7. Output and claims

The report must show:

- baseline P/N/A/B/Pol;
- every positive-weight RGU scenario;
- minimum and maximum Pol over the fixed positive grid;
- q-scale invariance check;
- all zero-weight stress outcomes;
- completeness and any missing inputs;
- exact factor-input provenance and weight-design version.

No automatic label `robust` is assigned. The protocol reports the envelope and
lets the reader see the design dependence.

When q is positive in a one-PTN topology, the Core field named UNO is
numerically equal to that PTN's Pol. It must be described as a **single-PTN
scenario field**, not as a historical area-level UNO.

## 8. Prohibitions

- no fitting weights to the known conflict outcome;
- no RGU from actor power, office, resources, headcount, or mobilization;
- no KVPTN from severity, duration, coverage, source count, or KVS;
- no changing topology or factor values inside weight sensitivity;
- no removal of noncomputable scenarios;
- no selection of the most convenient scenario as true;
- no HUMAN validation or HUMAN reliability claim.
