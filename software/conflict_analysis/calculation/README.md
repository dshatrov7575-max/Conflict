# Calculation Beta V1

Task `CA-I1-CALCULATION-BETA-V1-IMPLEMENTATION`, parent #19.
Executable identity: `POLARIZATION_V1_BETA / 1.0.0`.

This module provides immutable `CalculationSnapshot` and `CalculationRun` value
objects, a pure strategy interface and exact-version executable dispatch, and
a read-only Foundation/G8 snapshot adapter. It introduces no domain tables,
migrations, HTTP endpoints, UI integration or automatic calculation jobs.
`CalculationStrategyDefinition` remains Foundation's registry metadata authority;
the code dispatch table only selects implementations and does not write metadata.

Snapshot/run records are returned to the caller, not saved in a database. Keep
`snapshot.to_json()` and `run.to_json()` to retain a calculation. An exported
snapshot can be replayed offline after source corrections, freeze or archival.
Persistent append-only database run history is outside this slice; results are
never stored in ParameterValue, Experiment, ImportRun or AuditEvent.

## Frozen numerical contract

The eligibility and area missingness rules implement the owner-approved
[P0-1/P0-2/P0-3 packet](https://github.com/dshatrov7575-max/Conflict/issues/6#issuecomment-5601645025),
confirmed by [OD-0032](https://github.com/dshatrov7575-max/Conflict/issues/6#issuecomment-5601776533).
The current task authorizes this core slice independently of the historical
import-snapshot proposal in #19.

For actor `i` and PTN `j`, attitude `x` is on `[-10,10]`, salience `c=KVS`,
actor weight `r=RGU` and PTN importance `q=KVPTN` are on `[0,10]`.
These are beta compatibility inputs, never V4 Power.

An actor row is eligible only when **all three** x/c/r values are numeric:

```text
w_i = r_i * c_i
W_j = sum(w_i for eligible actors in PTN j)
P_j = 10 * sum(w_i * max(x_i, 0)) / W_j
N_j = 10 * sum(w_i * max(-x_i, 0)) / W_j
A_j = P_j + N_j
B_j = P_j - N_j
Pol_j = 2 * min(P_j, N_j)
UNO = sum(q_j * Pol_j) / sum(q_j)
```

P/N/A/Pol/UNO use 0..100; B uses -100..100. `CalculationRun.P`, `.N`, `.A`,
`.B`, and `.Pol` are immutable mappings keyed by PTN identity; `.ptns` and
`.trace` retain all PTN components, actor contributions and UNO contributions.
UNO is the weighted PTN polarization, never polarization of pooled area P/N.
It is a beta tension/polarization index with no prediction, probability, risk
or validated general-intensity interpretation.

Rules fixed by strategy version 1.0.0:

- UNKNOWN, INSUFFICIENT_DATA, NOT_APPLICABLE and OPEN_METHOD require null
  values. They are never converted to zero. A wholly absent input is UNKNOWN
  with source identity `ABSENT`.
- PROVISIONAL, CONFIRMED, DISPUTED and RETROSPECTIVE_KNOWLEDGE require one
  finite numeric value. Their original status/source identity stays in trace;
  numeric eligibility does not validate the assessment.
- An ineligible actor row contributes to neither numerator nor denominator.
  Completeness records expected and eligible rows, including known zero rows.
  Even a known zero weight does not make a missing attitude eligible.
- x=0 is neutral; c=0 and r=0 are known zero weights. W=0 makes all five PTN
  metrics null and the PTN status `NOT_COMPUTABLE`.
- Missing q anywhere makes UNO null, with `MISSING_PTN_WEIGHT`. No q=0/q=1
  substitution and no partial area renormalization occurs.
- Known q=0 excludes that PTN from the area sum. An unavailable PTN with
  positive q blocks UNO. Sum(q)=0 makes UNO null, never zero.
- The run is `NOT_COMPUTABLE` when UNO is unavailable, `PARTIAL` when UNO is
  available with incomplete rows/PTNs, otherwise `COMPLETE`. PTN results remain
  visible when the area is unavailable. There are no completeness thresholds.
- Arithmetic uses exact rational numbers. Each published metric/contribution
  is rounded once to eight decimal places, ties to even. Trace weights, W and
  raw numerators remain exact finite decimals. UNO uses unrounded
  PTN polarization. A/B/Pol are also computed before rounding; summing rounded
  contributions may differ by a final decimal unit. JSON stores decimals as
  canonical decimal strings; no ambient Decimal context or binary-float math
  controls the result.
- Warnings always retain the beta interpretation and the unresolved dependence
  between the KVS and KVPTN coding layers. No hidden correction is applied.

Changing these rules requires a new strategy version. Unsupported strategy
identities/versions raise `CalculationInputError`; there is no latest fallback.

## Foundation/G8 adapter

`capture_snapshot()` reads one explicit Experiment and TimeSlice. It verifies
the exact workspace/definition pin and accepted assessment projection, requires
the existing G8 POS/SAL scales and shared applicability topology, and reads
terminal ParameterValue revisions across the complete assessment-header history.
It preserves the ActorElementAssessment identity and each value's own revision.
No other experiment or TimeSlice can supply missing values.

In this beta adapter POS supplies the attitude input and SAL supplies KVS.
PTN/GU identities use their existing projected AnalyticalElement/Actor identities
and ActorElementRole topology. It does not infer a new domain classification,
create a Cartesian product, or select topology by labels.

G8 has no canonical RGU/KVPTN numeric lane. The caller can provide `BetaWeights`
with explicit experiment/time scope and source identities. Missing entries stay
UNKNOWN. The adapter does not read the legacy 330-row receipt, import a matrix,
derive weights from PowerProfile, or write beta weights to ParameterValue.

```python
from calculation import CalculationSnapshot, InputValue, calculate
from calculation.foundation import BetaWeights, capture_snapshot

# IDs below are the existing projected Actor/AnalyticalElement primary keys.
weights = BetaWeights(
    experiment_id=str(experiment.pk),
    time_slice_id=str(time_slice.pk),
    rgu=((str(actor.pk), InputValue("PROVISIONAL", "3", "beta-rgu-source", "1")),),
    kvptn=((str(element.pk), InputValue("PROVISIONAL", "2", "beta-q-source", "1")),),
)
snapshot = capture_snapshot(
    experiment_id=experiment.pk, time_slice_id=time_slice.pk, beta_weights=weights,
)
run = calculate(snapshot)
replayed = calculate(CalculationSnapshot.from_json(snapshot.to_json()))
assert run.to_json() == replayed.to_json()
```

The API is an internal service. Its caller must enforce the existing Foundation
access policy before reading a lane; no new public authorization endpoint is
created. Snapshot capture takes the shared Project transaction lock used by G8
writes. PostgreSQL is the supported concurrent runtime; SQLite checks exercise
portable behavior, not PostgreSQL row-lock concurrency.

The SHA-256 input identity covers project/workspace/experiment/assessment set,
definition ID/hash, TimeSlice ID/version/cutoff, strategy identity, complete
topology and every source ID/version/status/value. Canonical ordering makes the
identity independent of database/list order. `from_json()` verifies the digest.
`result_digest` hashes the complete deterministic run, including warnings/trace.
The hashes establish byte identity, not authenticity or empirical validity.

## Executable examples and tests

From `software/conflict_analysis`, use the project's Python environment:

```text
python -m calculation.examples
python -m pytest calculation/tests
```

Set `USE_SQLITE=1` for portable tests. No production database is used by them.

| Vector | x | r (c=1) | P | N | A | B | Pol / UNO | Status |
|---|---|---|---:|---:|---:|---:|---:|---|
| DV-01 Neutral | 0, 0 | 1, 1 | 0 | 0 | 0 | 0 | 0 | COMPLETE |
| DV-02 Maximum opposition | 10, -10 | 1, 1 | 50 | 50 | 100 | 0 | 100 | COMPLETE |
| DV-03 Partial UNKNOWN | 10, -10, UNKNOWN | 1, 1, 1 | 50 | 50 | 100 | 0 | 100 | PARTIAL, 2/3 rows |
| DV-04 Zero weight | 10, -10 | 0, 0 | null | null | null | null | null | NOT_COMPUTABLE |
| DV-05 Unequal opposition | 10, -10 | 3, 1 | 75 | 25 | 100 | 50 | 50 | COMPLETE |

All examples are synthetic, with one PTN and q=1. Additional tests cover every
absent status/component, q missing/zero, unequal PTN weights, one important PTN
against five weak PTNs, exact replay/rounding, input validation, G8 corrections,
HUMAN/AI isolation, no-write capture, and frozen/archived experiment replay.

Implementation base: `ea507812090651a460d753c472082437abe92db3`;
base tree: `f407e609adb2a8b94770b521a1302feb79281822`.
