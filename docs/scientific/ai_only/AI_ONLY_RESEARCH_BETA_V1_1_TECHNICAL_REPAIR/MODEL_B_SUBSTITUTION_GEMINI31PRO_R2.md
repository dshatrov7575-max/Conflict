# AI_ONLY_RESEARCH_BETA_V1.1 — executor-only Model B substitution R2

**Status:** `FROZEN_BEFORE_AI2_RESPONSE`
**Frozen:** 2026-10-01, before any V1.1 AI2 response under the replacement binding
**Branch:** `review/ai-only-research-beta-v1-1-fast-repair`

## Reason

The prospectively selected Claude executor is unavailable because the owner's usage limit is exhausted. The previously proposed Grok binding is not executable as frozen: the owner's UI shows Expert mode backed by `Grok 4.6`, not the exact frozen label `Grok 4.7`. Therefore no Grok prompt is dispatched.

The owner also showed Gemini with exact UI-visible model `3.1 Pro` and the separate option `Расширенные способности к размышлению`. This replacement is selected prospectively based on executor availability, before seeing any AI2 response.

The already dispatched AI1 result remains sealed and must not be shown to Model B.

## Frozen replacement binding

- role: `OMG_NOV24_V101_AI2`
- service: `Google Gemini`
- exact UI-visible model identity: `3.1 Pro`
- reasoning option: `Расширенные способности к размышлению`
- prompt: `omg_nov24_v1_0_1/07_AI2_STANDALONE_RU.md`
- frozen prompt Git blob: `9a5f103db14541c7379444886bc83b386224cacf`
- attempt limit: `1`
- Auto/fallback/model shopping: forbidden

The earlier Grok 4.7 amendment is superseded before dispatch and produces no primary output.

## Unchanged

Scientific input, route, contract, rubric, evidence, actor scopes, PTN/reference, anchors, C1–C8, no-search rule, mandatory run_id/timestamp/model identity, comparator, six carry-forwards, Core/formula/weights, UNKNOWN != 0, and no-adjudication/no-repair rules are unchanged.

## Reporting

Final V1.1 pair if executed:
- AI1: ChatGPT / GPT-5.6 Sol Pro
- AI2: Google Gemini / 3.1 Pro / Расширенные способности к размышлению
