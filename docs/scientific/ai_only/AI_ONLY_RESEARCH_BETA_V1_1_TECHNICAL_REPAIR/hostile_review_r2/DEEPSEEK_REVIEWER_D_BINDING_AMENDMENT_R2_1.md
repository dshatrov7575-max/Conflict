# AI_ONLY_RESEARCH_BETA_V1.1 — DeepSeek Reviewer D binding amendment R2.1

**Status:** `FROZEN_BEFORE_REVIEWER_D_OUTPUT`  
**Frozen:** 2026-10-01, before any Reviewer D substantive generation  
**Reason:** the DeepSeek Web UI supplied by the owner exposes the provider name `DeepSeek` and the mode `Глубокое мышление`, but does not expose an exact backend model name.

## Frozen Reviewer D binding

- role: `V1_1_HOSTILE_REVIEWER_D_R2`
- service: `DeepSeek Web`
- exact UI-visible provider identity: `DeepSeek`
- exact UI-visible reasoning mode: `Глубокое мышление`
- exact backend model identity: `NOT_UI_DISCLOSED`
- search mode: `Умный поиск` MUST remain OFF
- destination: new separate DeepSeek Web chat
- prompt: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r2/REVIEWER_D_DEEPSEEK_STANDALONE_RU.md`
- target manifest: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r2/EXPANDED_REVIEW_TARGET_MANIFEST_R2.json`
- target manifest blob: `4b27f7eb0a393de53dde4ff737e9f2a606b16611`
- substantive attempt limit: 1

## Reporting rule

Reviewer D must report the model identity without inventing a backend model version:
- `actual_model_label`: use the exact identity that the DeepSeek session itself exposes; if no backend model is exposed, use `DeepSeek Web — Глубокое мышление (backend model not UI-disclosed)`.
- `model_label_source`: state that the provider/mode are UI-visible and that the backend model version is not exposed by the UI.

A self-asserted hidden backend version that is not visibly exposed by the service is not treated as independently authenticated model identity.

## Isolation and no-switch rule

Reviewer D must not see:
- Reviewer C output;
- any R1 hostile-review output;
- coordinator commentary;
- external search results or known conflict outcome.

After substantive generation starts, model/mode switching, corrective follow-up, rerun-until-favorable and coordinator adjudication are forbidden.

This amendment changes only executor identity reporting. The R2 evidence target, scientific outputs, primary outputs, comparison, cohort, Core replay, release gate and claim boundaries are unchanged.
