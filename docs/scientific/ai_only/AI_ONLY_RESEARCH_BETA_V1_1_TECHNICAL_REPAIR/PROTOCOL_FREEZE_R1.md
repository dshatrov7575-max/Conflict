# AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR — prospective protocol freeze R1

**Status:** `FROZEN_BEFORE_NEW_V1_1_RESPONSES`  
**Frozen:** 2026-10-01, before any V1.1 primary response  
**Branch:** `review/ai-only-research-beta-v1-1-fast-repair`

## 1. Purpose

This is a separately named prospective technical-repair route after the immutable closure of `AI_ONLY_RESEARCH_BETA_V1`.

R1 remains `CLOSED_HOLD`. Its two OMG primary outputs are not repaired, edited, completed by the coordinator, relaxed by a new comparator, or counted as valid. The only R1 defect selected for new execution is objective protocol invalidity: both OMG outputs omitted the non-empty `run_id` required by the frozen comparator.

The selection rule is technical, not substantive. The already observed OMG values do not determine whether this route proceeds or what result is accepted.

## 2. Fast-track design

The route uses a hybrid carry-forward cohort:

- six R1 primary outputs that already passed their frozen validators are imported immutably by exact Git blob identity;
- only the two invalid OMG roles are executed again;
- the new OMG package is version-bumped and must explicitly require `run_id`, `completed_at_utc`, model identity, attestation and exactly four actor×factor entries;
- source evidence, actor scope, PTN, reference statement, anchors, C1–C8 rules, no-search rule and `UNKNOWN != 0` remain unchanged;
- no old OMG output is shown to either new primary chat.

This route is not described as a full fresh eight-role replication. It is reported as a **prospective technical-repair release route with six immutable carry-forwards and two fresh blind primaries**.

## 3. Frozen model binding

- AI1 service/model: `ChatGPT / GPT-5.6 Sol Pro`;
- AI2 service/model: `Claude / Claude Opus 5.5 High`;
- one fresh empty chat per role;
- one primary attempt per role;
- Auto mode, fallback, substitution and model shopping are forbidden;
- the UI-selected Claude `High` mode is recorded in the execution receipt even if the raw model self-label reports only `Claude Opus 5.5`.

## 4. Stopping and acceptance rules

1. Exact AI1 and AI2 standalone files and their Git blobs must be frozen before either prompt is dispatched.
2. Both raw answers are preserved unchanged.
3. No repair request, missing-field follow-up, targeted adjudication, coordinator substitution or rerun-until-number is allowed.
4. Any malformed answer, contaminated attestation, disagreement, `UNKNOWN` or `DISPUTED` is retained and may keep the route on HOLD.
5. Old invalid OMG values are never used as evidence, tie-breakers or acceptance targets.
6. All valid R1 carry-forward blobs remain byte-identical; no re-coding of KBM E02, KBM E05 or D25 E02 is permitted in this fast route.
7. Core `POLARIZATION_V1_BETA / 1.0.0`, factor rubrics, denominators and exogenous-weight grid remain unchanged.

## 5. Release and demo separation

A product/research-workflow demo does not wait for final publication status. The demo may show the already completed R1 evidence chain, two eligible read-only Core replays, D25 fail-closed incompleteness and the R1 release-gate HOLD.

V1.1 publication status is evaluated separately after the two fresh OMG responses, frozen comparison, updated cohort aggregation and any eligible read-only Core replay.

## 6. Claim boundary

- HUMAN validation/reliability: `NOT_PERFORMED`;
- historical snapshot: `NOT_ESTABLISHED`;
- historical area UNO: `NOT_COMPUTED / BLOCKED`;
- prediction/probability/risk validation: `NOT_CLAIMED`;
- old OMG `company KVS=5 / Pol=50`: superseded and not restored;
- no auto-merge.
