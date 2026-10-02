# OMG Company Decision V1.0.2 — prospective company-only replication

**Status:** `FROZEN_BEFORE_NEW_PRIMARY_RESPONSES`  
**Route:** `AI_ONLY_DYAD_OMG_E1_V102`  
**Rubric:** `2.1.0`  
**Evidence input SHA-256:** `34a70bb18664a8ccf5fb5713dd90bbebe32a1a60d17303603e4cb7d84d961f42`

## Purpose

V1.0.1 independently replicated the worker source-statement values and independently retained company KVS as `UNKNOWN`. Re-running models on the same company evidence is prohibited. V1.0.2 introduces a newly authenticated KMG press-service response dated 12.08.2011 that explicitly describes company wage actions, concessions and settlement decisions.

## Scope

Only two entries are coded:

- company `POS_AO2`;
- company `KVS_AO2`.

The worker values `POS=-5`, `KVS=5` are inherited from V1.0.1 and are not shown as answers to the new coders. The company actor is narrow: `RD_KMG_MANAGEMENT_FORMAL_RESPONSE_20110812`.

## Independence

Two primary coders receive separate standalone packets with the same frozen evidence input. They may not see prior episode/AO2 outputs, coordinator reviews, the other output, external search or the known outcome.

## Reactive-actor KVS rule

A mention, rebuttal, rejection or assertion that the opponent's demand is unfounded does not by itself satisfy KVS=5. KVS=5 requires an additional explicit link to the company's own action, decision, settlement, resource allocation or policy criterion concerning pay.

## Comparator and release gate

- same NUMERIC value and identical C1-C8: `CONSENSUS_NUMERIC`;
- same UNKNOWN and failed-gate structure: `SHARED_UNKNOWN`;
- any other result: `HOLD_DISAGREEMENT`;
- coordinator substitution is forbidden;
- targeted content review rounds: `0`.

A read-only dyad scenario replay is allowed only if both company entries obtain two independent numeric consensus decisions. Any UNKNOWN or disagreement yields `HOLD_FACTOR_INCOMPLETE`.

## Scientific boundary

This is a non-simultaneous demand→formal-response dyad: worker statement 26.05.2011 and company response 12.08.2011. There is no carry-forward and no claim of a same-date snapshot, a 15.12.2011 state, area-level UNO, HUMAN validation or predictive validation.
