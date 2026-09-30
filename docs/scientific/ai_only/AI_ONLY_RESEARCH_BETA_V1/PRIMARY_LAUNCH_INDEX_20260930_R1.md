# AI_ONLY_RESEARCH_BETA_V1 — PRIMARY LAUNCH INDEX R1

Date: 2026-09-30
PR: #123
Branch: `review/ai-only-research-beta-v1`
Status: coordination index only; does not change frozen scientific inputs.

## Global rules

- Each primary run must be performed in a fresh independent model/chat.
- Send the model **only** the exact standalone file for its role.
- Do not include this index, PR comments, prior outputs, outcome, coordinator notes or sibling primary output in model context.
- Do not use external search unless the standalone explicitly allows it; current four launchable standalones forbid it.
- Preserve returned primary JSON byte/content unchanged after receipt.
- No rerun-until-number, model shopping, averaging or coordinator substitution.
- UNKNOWN != 0.
- Primary outputs do not authorize calculation by themselves.

## Lane 1 — OMG V1.0.2

Route: `AI_ONLY_DYAD_OMG_E1_V102`
State: `FROZEN_BEFORE_PRIMARY_RESPONSES`
Launch state: `BLOCKED_DELIVERY_ARTIFACT_UNAVAILABLE_IN_CURRENT_GIT_DRIVE_LIBRARY`

Frozen control documents and engineering exist in GitHub, but the exact conversation ZIP/standalone payload referenced by receipt is not available in current GitHub, Drive `Конфликтология/Почта`, or searchable Library.

Required rule: **do not reconstruct or regenerate the frozen standalone after freeze**.

Expected frozen ZIP identity from receipt:
- `MVP7_OMG_COMPANY_DECISION_V102_10_FILES_20260929.zip`
- SHA-256 `0c49038129f070c730d27ea4a095d849d4ef943ae2582fcfed00d86ea6520a7f`

Next gate: recover exact frozen delivery artifact, then launch two blind company runs.

## Lane 2 — KBM E02 V1.0.0

Route: `AI_ONLY_DYAD_KBM_E02_V100`
Input SHA-256: `d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42`
State: `READY_FOR_TWO_BLIND_PRIMARY_RUNS`

AI1:
- path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/kbm_e02_v1_0_0/06_AI1_STANDALONE_RU.md`
- Git blob SHA: `4d894bf841912788ec534904c05f53a3076bee3b`
- raw URL: `https://raw.githubusercontent.com/dshatrov7575-max/Conflict/review/ai-only-research-beta-v1/docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/kbm_e02_v1_0_0/06_AI1_STANDALONE_RU.md`
- expected output: `KBM_E02_V100_AI1_COMPLETED.json`

AI2:
- path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/kbm_e02_v1_0_0/07_AI2_STANDALONE_RU.md`
- Git blob SHA: `64d02513711034941da014bd40024e506a68b020`
- raw URL: `https://raw.githubusercontent.com/dshatrov7575-max/Conflict/review/ai-only-research-beta-v1/docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/kbm_e02_v1_0_0/07_AI2_STANDALONE_RU.md`
- expected output: `KBM_E02_V100_AI2_COMPLETED.json`

Post-run comparator:
`episode_input_v1/engineering/KBM_E02_V100/compare_primary.py`
Self-test: `PASS_8_OF_8`.

## Lane 3 — OMG Nov23–24 V1.0.0

Route: `AI_ONLY_DYAD_OMG_NOV24_V100`
Input SHA-256: `72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4`
State: `READY_FOR_TWO_BLIND_PRIMARY_RUNS`

AI1:
- path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/omg_e02_nov24_v1_0_0/06_AI1_STANDALONE_RU.md`
- Git blob SHA: `83473066a90daf00bc2a9413cb0175d25f54b60a`
- raw URL: `https://raw.githubusercontent.com/dshatrov7575-max/Conflict/review/ai-only-research-beta-v1/docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/omg_e02_nov24_v1_0_0/06_AI1_STANDALONE_RU.md`
- expected output: `OMG_NOV24_V100_AI1_COMPLETED.json`

AI2:
- path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/omg_e02_nov24_v1_0_0/07_AI2_STANDALONE_RU.md`
- Git blob SHA: `b8a18c8a553e1e6f1efee2bfbe4d348619795d59`
- raw URL: `https://raw.githubusercontent.com/dshatrov7575-max/Conflict/review/ai-only-research-beta-v1/docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/omg_e02_nov24_v1_0_0/07_AI2_STANDALONE_RU.md`
- expected output: `OMG_NOV24_V100_AI2_COMPLETED.json`

Post-run comparator:
`episode_input_v1/engineering/OMG_NOV24_V100/compare_primary.py`
Self-test: `PASS_8_OF_8`.

## Lane 4 — KBM E05 representation

State: `DISCOVERY_ONLY_COMPANY_PROVENANCE_PENDING`
No primary launch. No factor values assigned.
Next gate: authenticated pre-cutoff company E05 statement.

## Intake rule

When a primary output appears in `Конфликтология/Почта`:
1. preserve original bytes/content;
2. identify lane/role from JSON identity;
3. validate against frozen route/contract/rubric/input hash and clean attestations;
4. wait for sibling primary;
5. run only the frozen deterministic comparator;
6. publish HOLD or replay eligibility exactly as comparator defines;
7. never repair UNKNOWN/disagreement manually.
