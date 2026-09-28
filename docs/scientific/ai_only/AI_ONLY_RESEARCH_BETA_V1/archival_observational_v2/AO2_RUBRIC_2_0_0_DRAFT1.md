# AI_ARCHIVAL_OBSERVATIONAL_V2 — RUBRIC 2.0.0-draft1

Status: FROZEN_BEFORE_PRIMARY_RESPONSES. Separate from strict-v1 POS/KVS. Strict-v1 UNKNOWN records are not overwritten.

## General
Unit = narrow evidence-supported actor × projected PTN identity × exact reference statement × admitted historical episode. Only the frozen evidence set may be used. Do not use known outcome, external search, prior AI answers, broad GU assumptions, source frequency, emotional tone, or analyst intuition. UNKNOWN != 0. No interpolation.

## POS-AO2 anchors
- -10: admitted actor evidence explicitly rejects the reference as a whole, or explicitly demands reversal/change across all essential components covered by the reference.
- -5: admitted actor evidence explicitly demands change to at least one essential component of the reference, while whole-reference rejection is not established.
- 0: actor explicitly states no directional preference toward the reference.
- +5: admitted actor evidence explicitly defends/preserves at least one essential status-quo component of the reference or explicitly rejects the corresponding change, while whole-reference acceptance is not established.
- +10: actor explicitly defends the reference as a whole and rejects substantial change across its essential components.

A demand for a pay rise is directional negative evidence for the pay component but does not by itself justify -10. A company claim that employees are fairly compensated is directional positive evidence for the pay component but does not by itself justify +10.

## KVS-AO2 anchors
This is archival decision salience, not absolute psychological importance.
- 0: actor explicitly says the issue is irrelevant/not a decision criterion.
- 2: actor explicitly calls the issue secondary to a named higher-priority issue and accepts concession on it.
- 5: the issue is explicitly included in a collective/formal demand or decision set attributable to the actor, but leading rank/settlement conditionality is not established.
- 8: actor explicitly conditions continuation, refusal, settlement, participation, or another consequential decision on resolution of this specific issue.
- 10: actor explicitly makes the specific issue non-negotiable and refuses the relevant settlement/option without it.

Do not infer KVS from strike duration, headcount, production loss, punishment severity, repeated media coverage, or persistence alone. A multi-issue decision condition cannot automatically be assigned as KVS=8 to each component unless the source makes the specific component condition explicit.

## Admission gates
A1 exact narrow actor/PTN/reference/episode identity; A2 traceable text/context; A3 pre-cutoff content proof; A4 attribution to narrow actor; A5 exactly one AO2 anchor predicate; A6 provenance/dependency reviewed; A7 fixed mapping; A8 fixed independent AI-run protocol. NUMERIC requires all A1-A8 true. Otherwise UNKNOWN/null. Incompatible admitted evidence for the same unit => DISPUTED/null.

## Output semantics
These are PROVISIONAL AI-coded archival measurements. They are not HUMAN validation, strict-v1 validation, probability, prediction, or historical truth. RGU/KVPTN remain exogenous analytic weights.
