# MVP7 OMG Episode E1 — Sensitivity Decision Rules V1

**Status:** `FROZEN_BEFORE_EPISODE_PRIMARY_RESPONSES`

## 1. Computability states

- `NOT_COMPUTABLE`: any of the four required POS/KVS entries is not verified
  numeric, or all effective actor weights are zero.
- `COMPUTED_RESEARCH_SCENARIOS`: all four factor entries are verified numeric
  and the fixed scenario family has been executed.
- No scenario result becomes a historical December snapshot.

## 2. Main envelope

Only the seven strictly positive RGU scenarios belong to the main envelope.
Report:

- `Pol_min`, `Pol_max`;
- baseline Pol;
- baseline P/N/A/B;
- B sign and magnitude per scenario;
- every scenario, including extremes.

No probability distribution is attached to scenarios. The grid is a design
space, not a distribution of real social power.

## 3. q checks

Positive q rescaling is expected to leave one-PTN results unchanged. A failure
of this invariance is an implementation defect. Passing it is not evidence of
construct validity.

`q=0` is a coverage-exclusion stress and must not enter the positive envelope.

## 4. Zero-weight stresses

Zero-weight stresses are reported separately. A zero Pol caused by excluding
one actor is labelled `COVERAGE_STRESS_ZERO`, not absence of tension.

Both actor weights zero yields `NOT_COMPUTABLE`.

## 5. Permitted descriptive claims

Permitted, if supported by output:

- “Under the fixed positive RGU grid, Pol ranged from X to Y.”
- “The equal-positive baseline produced Pol = X.”
- “Positive q rescaling was algebraically invariant in the one-PTN topology.”
- “Zero-weight exclusion changed coverage and produced [result].”

Forbidden:

- “The true polarization was X.”
- “The result is robust” without a separately justified criterion.
- “RGU represents power” or “KVPTN represents objective importance.”
- “UNO predicts conflict/risk/probability.”
- “AI agreement validates the model.”

## 6. Relationship to Core

The runner mirrors the frozen formula and eight-decimal ties-to-even rounding.
Before any external release, the final factor record and baseline scenario must
also replay through the exact pinned Core blobs. A mismatch blocks release.
