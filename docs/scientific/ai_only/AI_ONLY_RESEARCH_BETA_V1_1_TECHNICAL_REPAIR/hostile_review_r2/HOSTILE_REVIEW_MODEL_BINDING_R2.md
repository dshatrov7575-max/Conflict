# AI_ONLY_RESEARCH_BETA_V1.1 — hostile review R2 model binding

**Status:** `QWEN_FROZEN_DEEPSEEK_PENDING_EXACT_UI_LABEL`
**Frozen:** 2026-10-01 before any R2 hostile-review output
**Selection basis:** two additional independent providers named by the owner before R2 review outputs; no result-based model shopping.

## Reviewer C
- role: `V1_1_HOSTILE_REVIEWER_C_R2`
- provider: Qwen
- exact UI-visible model: `Qwen 3.8-Max`
- destination: new separate Qwen chat
- attempt limit: 1 substantive attempt
- prompt: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r2/REVIEWER_C_QWEN_STANDALONE_RU.md`
- other R2 reviewer output access: FORBIDDEN
- R1 hostile-review output access: FORBIDDEN

## Reviewer D
- role: `V1_1_HOSTILE_REVIEWER_D_R2`
- provider: DeepSeek
- exact UI-visible model: `PENDING_PRE_DISPATCH_FREEZE`
- destination: new separate DeepSeek chat
- attempt limit: 1 substantive attempt
- prompt: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r2/REVIEWER_D_DEEPSEEK_STANDALONE_RU.md`
- other R2 reviewer output access: FORBIDDEN
- R1 hostile-review output access: FORBIDDEN

Reviewer D MUST NOT be dispatched until the owner provides the exact UI-visible DeepSeek model label and a prospective amendment is committed before generation begins.

## No-switch rule
Once a reviewer begins substantive generation, provider/model switching, corrective follow-up, rerun-until-favorable and coordinator adjudication are forbidden. A pure input-access failure before substantive review may be documented separately and does not become a scientific review output.
