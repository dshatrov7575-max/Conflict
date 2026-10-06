# AI_ONLY_EPISODE_INPUT_V1

**Status:** FROZEN BEFORE EPISODE CODING / AI-ONLY / NO HUMAN VALIDATION

## Purpose

This layer groups only dated `SOURCE_STATEMENT` observations from R2 into prospectively bounded historical episodes. It does not carry a statement forward to `2011-12-15T23:59:59Z` and does not create a latest-known actor state without a separately frozen persistence rule.

## Unit

`actor_id × ptn_id × episode_id`.

Before any episode value is admitted, the following must be fixed:

- start and end date;
- source-inclusion rule;
- actor universe;
- carry-forward rule;
- admitted source identities;
- provenance of each POS/KVS value.

## Frozen temporal policy

- `carry_forward_policy = NONE`;
- each R2 record remains attached to its own source-report date;
- dates cannot be pooled merely because they belong to the same conflict;
- the December 2011 historical snapshot remains `NOT_ESTABLISHED`;
- any future episode window must be fixed before recoding, not retrofitted to obtain computability.

## Calculation boundary

A real `CalculationSnapshot` is allowed only when the episode actor universe is complete and every included actor has both POS and KVS. Missing actors or values are not zero. Exogenous RGU/KVPTN scenarios cannot repair missing POS/KVS or temporal mismatch.

`PARTIAL` in Calculation Core is not evidence of absent tension. SOURCE_STATEMENT values are not HUMAN validation, probabilities, forecasts, or a December snapshot.

## Sensitivity

Read-only sensitivity is permitted only with all assumptions stated. It cannot overwrite UNKNOWN, cannot become a historical factor value, and cannot be presented as historical UNO.
