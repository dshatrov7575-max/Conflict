# AI_ONLY_REPLICATION_COHORT_R1 — Analysis Plan

**Status:** `FROZEN_BEFORE_ANY_COHORT_PRIMARY_RESULT`
**Date:** 2026-09-30

## Cohort

Four frozen lanes, eight independent primary roles, twelve actor×factor decisions total:

- KBM E02: 2 company decisions;
- OMG Nov23–24: 4 decisions;
- KBM E05: 2 company decisions;
- D25 E02: 4 decisions.

Decision totals:
- POS_AO2: 6;
- KVS_AO2: 6.

## Primary reproducibility endpoint

For each of 12 decisions, the two primaries are compared using the lane's frozen comparator.

Exact agreement requires identical:
- status;
- numeric value or null;
- all C1–C8 admission checks.

Comparator triage categories:
- `CONSENSUS_NUMERIC`
- `SHARED_UNKNOWN`
- `SHARED_DISPUTED`
- `HOLD_DISAGREEMENT`

No rationale-text matching and no confidence-label matching are required for the primary endpoint.

## Descriptive cohort outputs

Report exactly:

1. total decisions expected = 12;
2. total decisions observed from valid paired comparator outputs;
3. exact agreement count and fraction;
4. numeric-consensus count and fraction;
5. shared-UNKNOWN count and fraction;
6. shared-DISPUTED count and fraction;
7. disagreement count and fraction;
8. same statistics separately for POS and KVS;
9. lane-state counts:
   - `ELIGIBLE_FOR_READ_ONLY_*_SCENARIO_REPLAY`;
   - `HOLD_FACTOR_INCOMPLETE`;
   - `HOLD_DISAGREEMENT`;
   - `REJECT_INVALID_PRIMARY_RUN`;
10. number of lanes eligible for sensitivity replay.

Fractions are descriptive proportions of this purposeful cohort, not population estimates.

## Invalid/missing runs

An invalid primary pair is not replaced. Its lane is reported as invalid/unresolved according to the frozen lane gate.

A missing external run is reported missing. It is not imputed and does not trigger a replacement-model search.

## No inferential overclaim

Because this is a small purposeful provenance-feasible cohort:
- no claim of representative reliability;
- no population confidence interval;
- no p-value;
- no calibrated probability;
- no HUMAN reliability/validation;
- no automatic Cohen kappa headline.

A future larger preregistered sample may define inferential reliability separately.

## Scenario layer

Sensitivity results are downstream exploratory outputs only for lanes already classified eligible by their frozen comparator.

Scenario outputs do not change:
- primary agreement metrics;
- cohort membership;
- lane status;
- source coding.

## Forbidden post-result changes

- changing denominators to exclude disagreements;
- counting only numeric decisions as the agreement denominator;
- dropping UNKNOWN/DISPUTED decisions;
- adding new lanes after observing results;
- replacing an invalid/unfavorable primary with another model;
- changing C1-C8 agreement semantics;
- using scenario results to adjudicate coding.
