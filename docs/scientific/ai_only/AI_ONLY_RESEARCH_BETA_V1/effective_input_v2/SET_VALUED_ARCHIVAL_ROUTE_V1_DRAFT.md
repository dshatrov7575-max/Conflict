# SET-VALUED ARCHIVAL ROUTE V1 — design note

Status: DRAFT / NOT A NEW POINT ESTIMATE / NO CORE INPUTS CREATED

## Purpose
The strict v1 rubric is retained unchanged. When a historical item cannot receive a licensed point anchor, this route may preserve a **set of anchors not ruled out by admitted evidence** rather than forcing UNKNOWN to zero or inventing a midpoint.

This is an uncertainty/sensitivity layer, not a replacement factor definition. It must never be serialized as one historical POS/KVS value and must not be described as HUMAN validation.

## Candidate representation
For each actor×PTN×time item:
- POS_allowed ⊆ {-10,-5,0,5,10}
- KVS_allowed ⊆ {0,2,5,8,10}
- exclusion_rationale per removed anchor
- admitted evidence references
- unresolved gates
- status = FULL_SET / REDUCED_SET / DISPUTED_SET

A set is reduced only by a direct logical exclusion supported by admitted evidence and the frozen rubric. Missing evidence never removes an anchor. Partial-reference evidence does not remove anchors for the whole reference unless the logical implication is explicit.

## Calculation boundary
The current Calculation Core accepts one numeric value, not sets. Therefore set-valued records are **not** passed to ParameterValue or CalculationSnapshot as if they were observed values.

A separate scenario enumerator may evaluate permissible combinations under explicit exogenous RGU/KVPTN baselines and report only an envelope/range and the assumptions used. It is a robustness exercise, not historical UNO. If the full admissible set produces 0..100 or similarly uninformative bounds, that result is reported rather than narrowed by judgment.

## Why this route is useful
It preserves UNKNOWN != 0, avoids changing the frozen point rubric, and can show whether any conclusion is robust to unresolved archival coding. It does not solve missing group mandate, missing cutoff proof, or missing factor predicates.

Activation requires a separate frozen enumerator protocol and dual AI audit of each anchor exclusion before any envelope is published.
