# AI_ONLY_RESEARCH_BETA_V1 — Release Gate R1

**Status:** `FROZEN_BEFORE_ANY_COHORT_PRIMARY_RESULT`  
**Date:** 2026-09-30

## Release object

This gate controls only the **AI-only research beta package**.

It does not authorize:
- HUMAN validation or reliability;
- external substantive historical measurement;
- a 15.12.2011 historical snapshot;
- historical area-level UNO;
- predictive, probability, or risk-validation claims.

Those remain blocked/not performed unless a future separate protocol establishes them.

## Key principle

A research beta may legitimately contain `UNKNOWN`, `DISPUTED`, `HOLD_FACTOR_INCOMPLETE`, or `NOT_COMPUTABLE`.

Therefore a noncomputable lane is **not by itself** a beta-release failure.

The release question is whether the research workflow is complete, frozen, reproducible, provenance-visible, technically valid, and honestly labeled.

## Mandatory gates for AI-only Research Beta RC

### G1 — Fixed cohort and stopping rule
PASS only if:
- `AI_ONLY_REPLICATION_COHORT_R1_20260930` remains unchanged after first cohort result;
- no new lane was added to seek a favorable result;
- all four frozen lanes are reported.

### G2 — Primary execution completeness
PASS only if all eight frozen primary roles produce valid protocol outputs.

Missing, contaminated, substituted, or model-shopped roles block RC until resolved by the originally defined role/executor path. An unfavorable/UNKNOWN result is valid and does not fail G2.

### G3 — Input/provenance integrity
PASS only if:
- each lane uses its frozen input SHA;
- source authentication/receipt remains traceable;
- no post-result evidence rebinding or input rewrite occurred.

### G4 — Deterministic comparison
PASS only if:
- each lane is processed by its frozen comparator;
- no coordinator substitution or targeted content review is used;
- every lane outcome is retained, including disagreement/UNKNOWN/DISPUTED.

A lane may end in `ELIGIBLE_FOR_READ_ONLY_*_SCENARIO_REPLAY`, `HOLD_FACTOR_INCOMPLETE`, or `HOLD_DISAGREEMENT` without failing G4.

### G5 — Cohort analysis reproducibility
PASS only if:
- cohort aggregator exact Git blob matches the tested blob;
- frozen denominator is 12 decisions total / 6 POS / 6 KVS;
- missing/invalid decisions are not removed from denominators;
- aggregate output validates against the frozen schema.

### G6 — Exogenous-weight integrity
PASS only if:
- sensitivity grid remains unchanged after primary results;
- RGU/KVPTN are not inferred from evidence or outcome;
- tested runner V2.1 exact Git blob is used.

This gate applies even if no lane is numerically eligible; in that case no scenario is run.

### G7 — Eligible-lane technical replay
For every lane that reaches all-numeric replay eligibility:
- read-only sensitivity run must use the frozen grid/binding;
- baseline/result must replay through the pinned unchanged Core before numerical scenario output is included in RC;
- any Core mismatch blocks RC until resolved without changing factor inputs or weights.

If zero lanes are eligible, G7 is PASS-NOT-TRIGGERED and the beta may still report all lanes as noncomputable/HOLD.

### G8 — Claim boundary
PASS only if the package prominently states:

`AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`

and preserves:
- historical snapshot = NOT_ESTABLISHED;
- historical area UNO = NOT_COMPUTED/BLOCKED;
- HUMAN validation = NOT_PERFORMED;
- HUMAN reliability = NOT_MEASURED/NOT_PERFORMED;
- predictive/probability/risk validation = NOT_CLAIMED.

## Decision

`AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS`

iff G1–G6 and G8 PASS, and G7 is PASS or PASS-NOT-TRIGGERED.

Otherwise:
`AI_ONLY_RESEARCH_BETA_RC_HOLD`.

Lane-level numerical computability is reported separately and cannot override the research-beta gate.

## Permanently separate release states

For this cohort/protocol:

- External substantive historical measurement: `HOLD`
- Historical area-level UNO: `BLOCKED`
- HUMAN-validated scientific release: `NOT_PERFORMED`
- Predictive/probability/risk validation: `BLOCKED/NOT_CLAIMED`

No beta-RC PASS changes those states.
