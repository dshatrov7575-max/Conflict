# MANUAL_DUAL_MODEL_R1 — pre-output executor plan

Status: PREOUTPUT_DRAFT
Date: 2026-10-01
Scope: executor-only supersession candidate for AI_ONLY_REPLICATION_COHORT_R1_20260930

## Reason

Copilot CLI path is operational, but the frozen model pins `gpt-6-astra` and `claude-opus-5.5` are unavailable under the current Copilot Free account. Run 36781002777 produced zero-byte outputs for all eight roles and therefore no scientific primary result.

The owner has authorized a manual multi-chat route instead of purchasing a paid Copilot plan.

## Scientific invariants preserved

Unchanged:
- cohort membership: 4 lanes / 8 primary roles / 12 actor×factor decisions;
- every frozen standalone prompt and its exact Git blob identity;
- factor rubric and evidence input;
- UNKNOWN != 0;
- no coordinator substitution;
- no targeted content review;
- no rerun-until-number;
- no post-result cohort expansion;
- no post-result weight tuning;
- no cross-lane factor repair;
- no cross-lane historical aggregation;
- frozen denominators / weight grid / release gate;
- old OMG company KVS=5 / Pol=50 remain superseded;
- PR remains Draft; no auto-merge.

## Manual executor design

Eight fresh chats:
- four independent MODEL_A chats, one per AI1 standalone;
- four independent MODEL_B chats, one per AI2 standalone.

Each chat must:
1. be newly created before receiving its standalone;
2. receive exactly one frozen standalone prompt and no sibling output;
3. have no prior episode/R2/coordinator result in context;
4. not use external search unless the frozen standalone explicitly permits it;
5. return the raw requested JSON only;
6. not be corrected, retried, repaired, or shown another coder's result;
7. preserve the exact visible model identity and service in the execution receipt.

The coordinator chat is not eligible to act as a blind primary.

## Model-binding gate

Manual execution is FORBIDDEN until both exact UI-visible model identities are prospectively frozen here.

Required fields before first primary output:
- MODEL_A service + exact model name: TO_BE_FROZEN
- MODEL_B service + exact model name: TO_BE_FROZEN

No primary prompt may be issued before these fields are replaced by exact model identities and the status becomes `FROZEN_BEFORE_RESPONSES`.

## Acceptance

A manual primary output is admissible only if its chat/model identity matches the frozen binding, the correct frozen standalone was used once, and the raw returned JSON is captured unchanged.
