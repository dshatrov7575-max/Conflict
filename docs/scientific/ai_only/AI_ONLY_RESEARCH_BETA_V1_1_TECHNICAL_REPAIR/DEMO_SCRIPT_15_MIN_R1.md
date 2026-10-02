# Conflict Analysis — 15-minute fast demo script

**Demo status:** research-workflow demonstration, not a HUMAN-validated scientific release.  
**Can be shown even if V1.1 remains HOLD.**

## 00:00–01:00 — What is being demonstrated

- source evidence is frozen and provenance-visible;
- two independent AI coders assign factor values under explicit anchors;
- comparator and release decisions are deterministic;
- `UNKNOWN` is never converted to zero;
- Core/formula are unchanged and replayable.

Required banner:

`AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`

## 01:00–03:00 — Frozen historical input

Show one compact lane packet:
- actor identity;
- PTN/reference statement;
- archived source receipt/hash;
- permitted evidence fragments;
- POS/KVS anchors and C1–C8 admission checks.

Explain that no external search or known outcome is available to the primary coders.

## 03:00–05:00 — Two independent primary outputs

Show KBM E02 or KBM E05 AI1 and AI2 side by side:
- distinct model/service and run IDs;
- clean attestations;
- matching factor values;
- all C1–C8 true;
- raw JSON preserved unchanged.

Do not present AI agreement as truth or source authentication.

## 05:00–07:00 — Frozen comparator

Show deterministic comparison:
- identical status/value/C1–C8 → `CONSENSUS_NUMERIC`;
- disagreement → HOLD;
- shared UNKNOWN → `HOLD_FACTOR_INCOMPLETE`;
- no coordinator adjudication.

## 07:00–09:30 — Sensitivity and Calculation Core parity

Use KBM E02 and KBM E05:
- 15 frozen scenarios per eligible route;
- exogenous RGU/KVPTN grid fixed before results;
- every scenario replayed through pinned `POLARIZATION_V1_BETA / 1.0.0`;
- result digests and JSON replay stable;
- this is a single-PTN research scenario, not historical area UNO.

## 09:30–11:30 — Honest incompleteness

Show D25 E02:
- worker POS = shared `UNKNOWN`;
- company KVS = shared `UNKNOWN`;
- lane state = `HOLD_FACTOR_INCOMPLETE`;
- no substitution with zero and no forced calculation.

This is a positive safety result, not a system failure.

## 11:30–13:00 — Fail-closed malformed output

Show R1 OMG:
- both models produced substantively matching values;
- both omitted required `run_id`;
- frozen comparator rejected both;
- coordinator did not append IDs or relax schema;
- G2/G4 failed exactly for this reason.

## 13:00–14:30 — Release gate

Show frozen gate output:
- G1/G3/G5/G6/G7/G8 PASS;
- G2/G4 FAIL;
- overall state `AI_ONLY_RESEARCH_BETA_RC_HOLD`;
- exact blockers and immutable evidence trail.

## 14:30–15:00 — Close

Key message:

> Conflict Analysis is not a black-box score generator. It is a provenance-visible, fail-closed research workflow that can compute when evidence is admitted and explicitly refuses when inputs or protocol are incomplete.

Then state the V1.1 fast-repair route:
- six valid R1 primary outputs carried forward by exact blob;
- only two invalid OMG roles rerun prospectively;
- demo date no longer depends on publication status.
