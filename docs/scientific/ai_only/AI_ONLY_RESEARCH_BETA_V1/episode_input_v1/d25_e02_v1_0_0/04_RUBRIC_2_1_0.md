# POS/KVS AO2 rubric 2.1.0 — D25 E02 V1.0.0

Status: FROZEN_BEFORE_PRIMARY_RESPONSES.

## POS_AO2
- -10: explicit rejection/change of the whole reference across all essential components.
- -5: explicit demand to change at least one essential component.
- 0: explicit absence of directional preference.
- +5: explicit defence/preservation of at least one status-quo component.
- +10: explicit defence of the whole reference and rejection of substantial change across all essential components.

## KVS_AO2
- 0: issue explicitly irrelevant/not a decision criterion.
- 2: issue explicitly secondary to a named higher-priority issue and concession accepted.
- 5: issue explicitly included in the actor's own formal demand set or declared action/decision/settlement set.
- 8: consequential action/refusal/settlement/participation/continuation explicitly conditioned on resolution of this specific issue.
- 10: issue explicitly non-negotiable and relevant settlement/option refused without it.

## Prospective D25 interpretation rules

1. Worker phrase `review of salaries` does not automatically equal `pay rise`. POS=-5 requires the admitted wording/context itself to support a demand to change the current pay arrangement. If the source supports only a neutral review procedure, C5 fails and POS is UNKNOWN.

2. Company history of six salary raises since 2008 does not automatically satisfy KVS=5. KVS=5 requires the admitted source to link pay to the company's own declared action/decision/settlement/policy criterion in the relevant source object, not merely provide historical justification.

3. The sentence characterizing KMG EP as `uncompromising over the key demand` is journalist voice unless explicitly attributed to the company. It cannot by itself establish company KVS or non-negotiability.

4. Continued protest, tent-camp duration, headcount and consequences do not establish worker KVS above the explicit anchor.

## C1-C8
C1 exact actor/PTN/source identity.
C2 traceable frozen text/context.
C3 pre-cutoff historical content authentication.
C4 decisive predicate attributable to the narrow actor.
C5 exactly one licensed anchor predicate fully satisfied.
C6 provenance/dependency/voice boundary reviewed.
C7 fixed same-report mapping respected; no carry-forward.
C8 independent frozen-run protocol respected.

NUMERIC requires all C1-C8 true.
If no one anchor is fully supported, return UNKNOWN/null with at least one failed gate.
Incompatible admitted evidence for the same actor-factor returns DISPUTED/null.

UNKNOWN is never zero.
