# HANDOFF — Главная 24 → Главная 25
**Project:** Конфликтология / Conflict Analysis MVP7 / AI_ONLY_RESEARCH_BETA_V1  
**Date:** 2026-09-30  
**Canonical branch:** `review/ai-only-research-beta-v1`  
**PR:** #123  
**Live HEAD at handoff:** `edcb0ff9f848df8c187b6839530615e1acd18a4e`  
**PR state:** Draft / open / not merged

## 0. ABSOLUTE CANONICAL SCIENTIFIC STATE

Do NOT restart the project.

The latest completed scientific result remains:

- route: `OMG_DYAD_E1_V101`
- state: `HOLD_FACTOR_INCOMPLETE`
- calculation state: `NOT_COMPUTABLE_FACTOR_INCOMPLETE`
- company KVS: `UNKNOWN`

Never restore the old technical-demo assumptions:
- old OMG company `KVS=5`
- old `Pol=50`

Those are superseded and are not scientific results.

OMG V1.0.2 remains separately frozen but its exact frozen ZIP is unavailable. Do not reconstruct it.

## 1. FIXED COHORT — DO NOT EXPAND

Cohort:
`AI_ONLY_REPLICATION_COHORT_R1_20260930`

Exactly 4 executable lanes / 8 primary roles / 12 actor×factor decisions:

1. `AI_ONLY_DYAD_KBM_E02_V100`
2. `AI_ONLY_DYAD_OMG_NOV24_V100`
3. `AI_ONLY_PAIR_KBM_E05_V100`
4. `AI_ONLY_DYAD_D25_E02_V100`

Stop rule is frozen:
- no new lane after cohort freeze;
- no success-based stopping;
- no adding episodes after HOLD to seek a computable case;
- no replacement-model shopping;
- no rerun-until-number.

Coverage ledger:
`docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/R2_TO_EPISODE_COVERAGE_LEDGER_20260930_R1.json`

All 6 R2 units are accounted for. No numeric R2 unit was silently omitted.

## 2. FROZEN LANE IDENTITIES

### KBM E02 V1.0.0
Route: `AI_ONLY_DYAD_KBM_E02_V100`  
Input SHA-256:
`d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42`

AI1 standalone blob:
`4d894bf841912788ec534904c05f53a3076bee3b`

AI2 standalone blob:
`64d02513711034941da014bd40024e506a68b020`

Comparator self-test: 8/8 PASS.

### OMG Nov23–24 V1.0.0
Route: `AI_ONLY_DYAD_OMG_NOV24_V100`  
Input SHA-256:
`72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4`

AI1 blob:
`83473066a90daf00bc2a9413cb0175d25f54b60a`

AI2 blob:
`b8a18c8a553e1e6f1efee2bfbe4d348619795d59`

Comparator self-test: 8/8 PASS.

### KBM E05 V1.0.0
Route: `AI_ONLY_PAIR_KBM_E05_V100`  
Input SHA-256:
`51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95`

AI1 blob:
`bd1d89ac5b0aa046e8d4498cb3b19031dd2c60af`

AI2 blob:
`0a39088aaa78bbf3c1a5e7300e1f3fe23e25438c`

Comparator self-test: 8/8 PASS.

### D25 E02 V1.0.0
Route: `AI_ONLY_DYAD_D25_E02_V100`  
Input SHA-256:
`aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa`

AI1 blob:
`2b0dcd8ee954f68d74b11b8bcbf299dfb9e2da33`

AI2 blob:
`2911bd6975184b9d9f1faf2aa235d6322eae7152`

Comparator exact-code self-test: 8/8 PASS.

D25 is fresh replication; no R2 factor inheritance.

## 3. PRE-RESULT ANALYSIS/WEIGHT/RELEASE FREEZES

Common exogenous weight design:
`docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/exogenous_weight_design_v2/`

Grid:
- RGU 10:1, 4:1, 2:1, 1:1, 1:2, 1:4, 1:10
- q checks 0.1 / 1 / 10
- zero-weight stresses separately

Runner:
`read_only_sensitivity_runner_v2_1.py`
Exact Git blob:
`04ed2c062d35e04cd073a001f81523a0342283ab`
Self-test: 11/11 PASS.

Cohort analysis:
`cohort_analysis_r1/`

Aggregator:
`aggregate_cohort_r1.py`
Git blob:
`47b3fc0fc3828066b8cb68450114d4f7f8b69790`
Self-test: 5/5 PASS.

Denominator frozen:
- 12 total decisions
- 6 POS
- 6 KVS
- missing/invalid remain unresolved in denominator

Release gate:
`release_gate_r1/`

Evaluator:
`evaluate_release_gate_r1.py`
Git blob:
`71bcfd8dd259364df6140be358ad265ce653443d`
Self-test: 6/6 PASS.

Important: lane UNKNOWN/HOLD/NOT_COMPUTABLE does NOT automatically fail the AI-only research beta. Missing/contaminated/substituted runs, provenance/hash failure, technical mismatch, post-result weight/cohort manipulation, or claim-boundary violation do fail the gate.

Cross-lane historical aggregation is forbidden. These lanes are not a historical multi-PTN snapshot and cannot be combined into historical area UNO.

## 4. GOOGLE DRIVE / ПОЧТА

Folder:
`Конфликтология/Почта`

At handoff:
- 8 primary task documents exist;
- 1 V1.0.2 recovery blocker exists;
- completed JSON in Drive: 0/8.

Tasks:
- TASK_KBM_E02_V100_AI1
- TASK_KBM_E02_V100_AI2
- TASK_OMG_NOV24_V100_AI1
- TASK_OMG_NOV24_V100_AI2
- TASK_KBM_E05_V100_AI1
- TASK_KBM_E05_V100_AI2
- TASK_D25_E02_V100_AI1
- TASK_D25_E02_V100_AI2
- BLOCKER_OMG_V102_RECOVER_FROZEN_ARTIFACT

Drive tasks are not themselves executors.

## 5. OMG V1.0.2 BLOCKER

Expected exact ZIP:
`MVP7_OMG_COMPANY_DECISION_V102_10_FILES_20260929.zip`

Expected SHA-256:
`0c49038129f070c730d27ea4a095d849d4ef943ae2582fcfed00d86ea6520a7f`

Not found in:
- Google Drive
- searchable Library / prior chat files
- GitHub
- Gmail

Local PC was the only remaining recovery location, but Desktop Commander monthly usage was exhausted.

DO NOT reconstruct/regenerate this ZIP.

## 6. COPILOT CLI AUTOMATED EXECUTOR

User created a fine-grained GitHub PAT and added repository Actions secret:
`COPILOT_GITHUB_TOKEN`

Credential gate now PASSES.

Executor R2:
`docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/executors/copilot_cli_r2/`

Workflow:
`.github/workflows/ai-only-primary-executor-r2.yml`

Pinned runtime:
- Copilot CLI v1.0.89
- Linux x64 SHA-256:
  `c5c234ccba6fae2b7a9eae462caf628e86c21b5e6240ec2e885727fc148a1dcc`
- AI1 model: `gpt-6-astra`
- AI2 model: `claude-opus-5.5`
- substitution forbidden

Static validator previously PASS:
run `36717680583`.

R2 isolation intent:
- one fresh GitHub-hosted VM per role
- exact standalone Git blob verified
- fresh COPILOT_HOME
- empty model working directory
- built-in MCPs disabled
- model-visible tools restricted to view
- no sibling/prior outputs
- no external search
- one invocation
- raw stdout preserved unchanged
- no JSON repair/retry/model replacement

## 7. CRITICAL LIVE EXECUTOR STATE AT CHAT END

Latest branch HEAD:
`edcb0ff9f848df8c187b6839530615e1acd18a4e`

Latest executor run:
- workflow: AI-only primary executor R2
- run id: `36756880787`
- run number: 5
- conclusion: **failure**

Important:
- credential-gate PASSED;
- all 8 jobs passed:
  - checkout
  - exact frozen standalone identity
  - pinned Copilot CLI installation
  - isolated working-directory preparation
- all 8 jobs FAILED specifically at:
  `Run exactly one blind primary invocation`
- therefore **no raw primary output artifact was uploaded**;
- execution receipts were uploaded;
- cohort intake job itself completed successfully but had no primary outputs to compare.

Thus current blocker is no longer credentials. It is the actual Copilot CLI invocation/runtime/model/auth behavior inside step 6.

Do NOT count these as scientific primary runs unless a model actually produced preserved stdout. They are pre-output execution failures.

Immediately inspect run `36756880787` / its receipt artifacts or job logs to determine the exact CLI failure before changing anything.

Do not rerun blindly until exact cause is known.

Recent commits:
- `8ac30a83...` Trigger Copilot CLI primary executor R2
- `d3f1acb2...` Fix Copilot R2 COPILOT_HOME for pre-model executor
- `d0fc6cde...` Record attempt-1 pre-model infrastructure failure
- `edcb0ff9...` Retrigger Copilot R2 after pre-model infrastructure repair

## 8. REQUIRED NEXT ACTION IN NEW CHAT

1. Read this HANDOFF completely.
2. Check live PR #123 and Drive `Конфликтология/Почта`.
3. Inspect GitHub Actions run `36756880787`, especially all eight step-6 failures and uploaded `receipt-*` artifacts.
4. Determine one common exact cause if possible.
5. Because no model output was produced, a purely pre-model/runtime repair is allowed, but:
   - do not change frozen standalone prompts;
   - do not change cohort membership;
   - do not change factor rubric/input;
   - do not change weight grid/denominators/release gate;
   - do not change model pins merely to make a result appear unless the pinned model is objectively unavailable and the protocol is prospectively superseded before any output.
6. After a justified executor-only repair, validate statically, record the failure/repair receipt, then trigger exactly once.
7. If outputs appear, preserve them unchanged, run frozen intake/comparators, then cohort aggregator.
8. Sensitivity/Core replay only for lanes that reach frozen all-numeric eligibility.
9. PR stays Draft; no auto-merge.

## 9. NON-NEGOTIABLE INVARIANTS

- UNKNOWN != 0
- old OMG company KVS=5 / Pol=50 never restored
- no coordinator substitution
- no targeted content review
- no rerun-until-number
- no model shopping
- no post-result cohort expansion
- no post-result weight tuning
- no cross-lane factor repair
- no cross-lane historical aggregation
- AI agreement != HUMAN validation/reliability
- historical area UNO remains NOT_COMPUTED/BLOCKED
- no auto-merge
