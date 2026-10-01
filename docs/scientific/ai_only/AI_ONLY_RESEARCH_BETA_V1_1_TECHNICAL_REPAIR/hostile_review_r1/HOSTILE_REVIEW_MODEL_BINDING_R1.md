# AI_ONLY_RESEARCH_BETA_V1.1 — hostile review model binding R1

**Status:** `FROZEN_BEFORE_REVIEW_OUTPUTS`  
**Date:** 2026-10-01  
**Selection basis:** executor availability and cross-provider diversity only; no primary values, expected verdict or preferred result may affect selection.

## Reviewer A

- role: `V1_1_HOSTILE_REVIEWER_A`
- provider slot: `ANTHROPIC_CLAUDE_STANDARD_CHAT`
- destination: a new separate Claude chat, not Cowork and not a prior project chat
- model selection rule: use the highest-reasoning Claude chat model available in the owner's account at dispatch time
- actual model identity: must be copied by the reviewer into `actual_model_label` and its source into `model_label_source`
- package: `V1_1_HOSTILE_REVIEWER_A_PACKAGE_R1.zip`
- package SHA-256: `b30284242da68d64d221aeda7a2ce80109580dd97a542e1c5d0c445c0dad1201`
- attempts: exactly one

## Reviewer B

- role: `V1_1_HOSTILE_REVIEWER_B`
- provider slot: `OPENAI_CHATGPT_TEMPORARY_CHAT`
- destination: a new ChatGPT Temporary Chat outside the project `Конфликтология`
- requested model: `GPT-5.6 Sol Pro`
- actual model identity: must be copied by the reviewer into `actual_model_label` and its source into `model_label_source`
- package: `V1_1_HOSTILE_REVIEWER_B_PACKAGE_R1.zip`
- package SHA-256: `a252c84bae0539f48af11de9fae4d603ca9326bced153670cb99d1d6705d8f40`
- attempts: exactly one

## No-switch rule

After a reviewer begins generating an answer, model/provider switching, corrections and repeated attempts are forbidden. A technical failure before any substantive output may be documented and replaced only by a new prospective amendment frozen before the replacement output.

## Isolation

Reviewer A must not receive Reviewer B's package/output. Reviewer B must not receive Reviewer A's package/output. Neither receives coordinator commentary, previous audits, known conflict outcome, external search results or post-freeze target changes.

## Intake

Each raw JSON is preserved byte-for-byte under its declared filename. Validation and cross-review comparison begin only after both raw outputs have been received.
