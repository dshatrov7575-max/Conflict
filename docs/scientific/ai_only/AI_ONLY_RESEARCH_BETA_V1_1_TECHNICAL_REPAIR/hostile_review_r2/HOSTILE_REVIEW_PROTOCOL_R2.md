# AI_ONLY_RESEARCH_BETA_V1.1 — independent hostile review protocol R2

## 1. Purpose

Run two new independent hostile reviews of the expanded evidence target after R1 packaging findings. The reviewers must decide whether the status

`AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS`

is supported by the R2 target, while preserving all explicit limitations.

This is not a re-coding of historical facts. It is an audit of workflow integrity, prospective repair, provenance, deterministic tooling, release-gate auditability, demo accuracy and claim boundaries.

## 2. Frozen target

- path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r2/EXPANDED_REVIEW_TARGET_MANIFEST_R2.json`
- Git blob: `4b27f7eb0a393de53dde4ff737e9f2a606b16611`
- source evaluation run: `36885038106`
- demo preflight run: `36888617846`

The R2 target includes source files that were absent from the R1 review package. R1 hostile-review outputs are deliberately excluded to prevent anchoring.

## 3. Independence

Each reviewer must:
- work in a fresh separate chat;
- not see the other R2 reviewer output;
- not see R1 hostile-review outputs;
- not use external search or known conflict outcome;
- use only the supplied R2 evidence package;
- not modify or adjudicate primary coding;
- use `NOT_PROVEN` when the supplied evidence does not establish a claim.

## 4. Required domains

1. D01_PROSPECTIVE_TECHNICAL_REPAIR
2. D02_IMMUTABLE_CARRY_FORWARD
3. D03_FRESH_PRIMARY_INDEPENDENCE
4. D04_MODEL_B_SUBSTITUTION
5. D05_COMPARATOR_FAIL_CLOSED
6. D06_COHORT_AGGREGATION
7. D07_ELIGIBLE_ONLY_CORE_REPLAY
8. D08_RELEASE_GATE_LOGIC
9. D09_PROVENANCE_AND_RECEIPTS
10. D10_DEMO_ACCURACY
11. D11_OLD_OMG_SUPERSESSION
12. D12_CLAIM_BOUNDARIES
13. D13_FAILED_WORKFLOW_ATTEMPTS
14. D14_SELECTIVE_RERUN_AND_BIAS_RISK

## 5. Required skeptical checks

The reviewer must distinguish:
- repository/Git timestamp evidence from service-level proof;
- preserved project attempts from the impossible stronger claim that no hidden external attempt could exist;
- a self-reported model label from an independently authenticated provider receipt;
- denominator coverage from numeric completion, historical truth, HUMAN validation or predictive validity.

The target explicitly labels some of these stronger claims `NOT_PROVEN`. Do not convert those limitations to PASS.

## 6. Severity and verdict

- P0: invalidates RC integrity or makes even the limited demo materially misleading -> `HOLD_P0`.
- P1: significant auditability/evidence/claim-boundary defect; limited demo may remain possible -> `PASS_WITH_P1` if evidence is otherwise sufficient.
- P2: clarity/packaging improvement without material RC effect.
- `NOT_PROVEN`: evidence package still insufficient for a justified verdict.

Allowed verdicts: `PASS`, `PASS_WITH_P1`, `HOLD_P0`, `NOT_PROVEN`.

Assess `rc_state_supported` and `demo_allowed` separately.

## 7. Output

Return exactly one JSON conforming to `HOSTILE_REVIEW_RESPONSE_SCHEMA_R2.json`, without Markdown or prose outside JSON. One substantive attempt only.
