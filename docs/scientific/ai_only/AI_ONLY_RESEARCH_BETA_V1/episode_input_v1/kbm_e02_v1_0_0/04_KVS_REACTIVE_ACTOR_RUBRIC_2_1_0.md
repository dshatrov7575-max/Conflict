# POS/KVS AO2 rubric 2.1.0 — KBM E02 V1.0.0

**Status:** `FROZEN_BEFORE_PRIMARY_RESPONSES`

## POS_AO2
- `-10`: explicit rejection/change of the whole reference across all essential components.
- `-5`: explicit demand to change at least one essential component.
- `0`: explicit absence of directional preference.
- `+5`: explicit defence/preservation of at least one status-quo component.
- `+10`: explicit defence of the whole reference and rejection of substantial change across all essential components.

## KVS_AO2
- `0`: actor explicitly says the issue is irrelevant or not a decision criterion.
- `2`: actor explicitly treats it as secondary to a named higher-priority issue and accepts concession.
- `5`: the issue is explicitly included in the actor's own formal demand set or in the actor's own declared action/decision/settlement set.
- `8`: a consequential action, refusal, settlement, participation or continuation is explicitly conditioned on resolution of this specific issue.
- `10`: the actor explicitly makes the issue non-negotiable and refuses the relevant settlement/option without it.

## Reactive-actor rule
A reactive actor's mention, rebuttal, rejection, or assertion that the opponent's demand is unfounded does **not by itself** satisfy `KVS=5`.

`KVS=5` requires an additional explicit link to that actor's own action, decision, settlement, resource allocation or policy criterion concerning the issue.

A condition concerning the labour dispute as a whole does not automatically establish component-specific `KVS=8`.

Do not infer KVS from strike duration, headcount, production loss, sanctions, source repetition, media prominence or emotional intensity.

## C1-C8 admission checks
- `C1`: exact narrow actor / PTN / reference / temporal object identity is satisfied.
- `C2`: coder-visible text/summary is traceable to the frozen evidence input.
- `C3`: pre-cutoff historical content authentication is satisfied.
- `C4`: the decisive predicate is attributable to the narrow company actor.
- `C5`: exactly one licensed anchor predicate is fully satisfied for the factor.
- `C6`: provenance, dependency, and source limitations have been considered.
- `C7`: fixed PTN/reference and non-simultaneous temporal mapping are respected; no carry-forward.
- `C8`: independent frozen-run protocol is respected; no external search, outcome, prior outputs, or other coder output used.

NUMERIC requires all C1-C8 true. If no single licensed anchor predicate is fully satisfied, return `UNKNOWN/null` and expose the failed gate(s). Incompatible admitted evidence for the same factor yields `DISPUTED/null`.

`UNKNOWN` is never zero.
