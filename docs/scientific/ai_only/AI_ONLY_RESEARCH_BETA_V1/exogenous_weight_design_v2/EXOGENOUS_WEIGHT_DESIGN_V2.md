# AI_ONLY_RESEARCH_BETA_V1 — Common Exogenous Weight Design V2

**Status:** `FROZEN_BEFORE_NEW_PRIMARY_RESULTS`  
**Frozen date:** 2026-09-30  
**Scope:** all currently frozen two-actor / one-PTN AI-only pair/dyad lanes listed in `LANE_BINDINGS.json`.

## Purpose

Freeze the analytic RGU/KVPTN sensitivity family before any new primary result from the three reproducible lanes is observed.

This design reuses the already-preregistered OMG Episode E1 V1 family unchanged in substance. It is **not** fitted to any new factor value, model output, conflict outcome, actor power, source count, group size, office, resources, capability, confidence or model agreement.

POS/KVS remain measured content variables. RGU/KVPTN remain exogenous analytic design weights.

## Release gate

A lane may enter this weight layer only if its frozen deterministic comparator returns the lane-specific all-numeric replay-eligibility state.

Any UNKNOWN, DISPUTED, invalid primary or disagreement keeps that lane outside the calculation layer. Missing values are never replaced by zero, baseline, average, sibling values or values from another date/lane.

## Equal-positive baseline

For each eligible two-actor lane:

- actor A RGU = 1
- actor B RGU = 1
- sole PTN KVPTN = 1

These are normalization/design values, not empirical assessments of equal real-world power or equal real-world importance.

## Positive RGU family

The fixed positive family is:

| Scenario | Actor A RGU | Actor B RGU | B/A ratio |
|---|---:|---:|---:|
| A_DOMINANT_10_1 | 10 | 1 | 0.1 |
| A_DOMINANT_4_1 | 4 | 1 | 0.25 |
| A_DOMINANT_2_1 | 2 | 1 | 0.5 |
| EQUAL_1_1 | 1 | 1 | 1 |
| B_DOMINANT_1_2 | 1 | 2 | 2 |
| B_DOMINANT_1_4 | 1 | 4 | 4 |
| B_DOMINANT_1_10 | 1 | 10 | 10 |

All positive scenarios must be reported; none may be removed after seeing output.

## One-PTN KVPTN limitation

Each current lane has exactly one PTN. Therefore positive q rescaling is expected to be algebraically invariant in the normalized one-PTN aggregate.

Implementation checks:
- q = 0.1
- q = 1
- q = 10

This is an invariance test, not substantive KVPTN sensitivity.

q=0 is a separate coverage-exclusion stress and must not enter the positive envelope.

## Zero-weight coverage stresses

Report separately:
- actor A RGU = 0, actor B = 1, q=1;
- actor A = 1, actor B RGU = 0, q=1;
- both actor RGUs = 0, q=1;
- actor A = 1, actor B = 1, q=0.

A zero Pol created by actor exclusion is a coverage stress, not evidence of absence of tension. Both actor weights zero is NOT_COMPUTABLE.

## Reporting

For every eligible lane report:
- baseline P/N/A/B/Pol;
- all seven positive RGU scenarios;
- positive-grid Pol_min and Pol_max;
- q-rescaling invariance;
- all zero-weight stress outcomes;
- exact factor record and comparator receipt;
- exact weight-design version and lane binding;
- exact pinned Core replay identity.

No scenario is selected as "true" or "best".

## Claim boundary

Even after successful replay, results remain AI-only bounded pair/dyad scenarios. They are not:
- historical same-date snapshots unless separately established;
- 15.12.2011 state estimates;
- historical area-level UNO;
- HUMAN validation/reliability;
- probability, prediction or risk validation.

When a one-PTN Core field named UNO is numerically produced, it must be labeled a **single-PTN scenario field**, not historical area UNO.

## Prohibitions

- no fitting weights to known outcome;
- no RGU from actor power, office, resources, headcount or mobilization;
- no KVPTN from severity, duration, source count, coverage or KVS;
- no changing grid after primary results;
- no dropping inconvenient scenarios;
- no using RGU/KVPTN to repair missing POS/KVS;
- no automatic robustness label.
