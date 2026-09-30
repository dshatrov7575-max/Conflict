# MANUAL_DUAL_MODEL_R1 — frozen manual executor plan

Status: FROZEN_BEFORE_RESPONSES
Date: 2026-10-01
Scope: executor-only supersession for AI_ONLY_REPLICATION_COHORT_R1_20260930

## Reason

Copilot CLI path is operational, but the previously pinned Copilot CLI models `gpt-6-astra` and `claude-opus-5.5` are unavailable under the current Copilot Free account. Run `36781002777` produced zero-byte outputs for all eight roles and therefore no scientific primary result.

The owner authorized a manual multi-chat route instead of purchasing a paid Copilot plan.

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

## Frozen manual model binding

Frozen prospectively before any manual primary response:

- MODEL_A service: ChatGPT
- MODEL_A exact UI-visible model identity: `GPT-5.6 Sol Pro`
- MODEL_A role allocation: all four AI1 standalones

- MODEL_B service: Claude
- MODEL_B exact UI-visible model identity: `Claude Opus 5.5 High`
- MODEL_B role allocation: all four AI2 standalones

Substitution is forbidden. A different model label, fallback, Auto mode, or silent model replacement makes that primary output inadmissible.

## Manual executor design

Eight fresh chats:
- four independent ChatGPT / GPT-5.6 Sol Pro chats, one per AI1 standalone;
- four independent Claude / Claude Opus 5.5 High chats, one per AI2 standalone.

Each chat must:
1. be newly created before receiving its standalone;
2. receive exactly one frozen standalone prompt and no sibling output;
3. have no prior episode/R2/coordinator result in context;
4. not use external search unless the frozen standalone explicitly permits it;
5. return the raw requested JSON only;
6. not be corrected, retried, repaired, or shown another coder's result;
7. preserve the exact visible model identity and service in the execution receipt.

The coordinator chat is not eligible to act as a blind primary.

## Acceptance

A manual primary output is admissible only if:
- its chat/service/model identity exactly matches the frozen binding above;
- the correct frozen standalone was used once;
- the chat was fresh before the standalone was pasted;
- the raw returned JSON is captured unchanged;
- no retry, repair, sibling exposure, coordinator substitution, external outcome lookup, or post-result prompt modification occurred.
