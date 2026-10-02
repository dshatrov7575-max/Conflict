# AI_ONLY_RESEARCH_BETA_V1 — PRIMARY LAUNCH INDEX R2

Date: 2026-09-30
PR: #123
Branch: review/ai-only-research-beta-v1
Status: coordination index only.

Global rules:
- Fresh independent model/chat per primary role.
- Model receives ONLY its exact standalone file.
- No prior outputs, outcome, coordinator notes, launch index, sibling output or external search.
- Preserve primary JSON unchanged.
- No rerun-until-number, model shopping, averaging, coordinator substitution or UNKNOWN→0.

## 1. OMG V1.0.2

Route: AI_ONLY_DYAD_OMG_E1_V102
State: FROZEN_BEFORE_PRIMARY_RESPONSES
Launch: BLOCKED_DELIVERY_ARTIFACT_UNAVAILABLE

Exact frozen ZIP required:
MVP7_OMG_COMPANY_DECISION_V102_10_FILES_20260929.zip
SHA-256:
0c49038129f070c730d27ea4a095d849d4ef943ae2582fcfed00d86ea6520a7f

Do not reconstruct or regenerate. Recovery-only task dispatched to Drive Почта.

## 2. KBM E02 V1.0.0

Route: AI_ONLY_DYAD_KBM_E02_V100
Input SHA-256:
d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42

AI1 standalone:
episode_input_v1/kbm_e02_v1_0_0/06_AI1_STANDALONE_RU.md
Git blob: 4d894bf841912788ec534904c05f53a3076bee3b
Output: KBM_E02_V100_AI1_COMPLETED.json

AI2 standalone:
episode_input_v1/kbm_e02_v1_0_0/07_AI2_STANDALONE_RU.md
Git blob: 64d02513711034941da014bd40024e506a68b020
Output: KBM_E02_V100_AI2_COMPLETED.json

Comparator:
episode_input_v1/engineering/KBM_E02_V100/compare_primary.py
Self-test: PASS_8_OF_8
Drive tasks: DISPATCHED.

## 3. OMG Nov23–24 V1.0.0

Route: AI_ONLY_DYAD_OMG_NOV24_V100
Input SHA-256:
72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4

AI1 standalone:
episode_input_v1/omg_e02_nov24_v1_0_0/06_AI1_STANDALONE_RU.md
Git blob: 83473066a90daf00bc2a9413cb0175d25f54b60a
Output: OMG_NOV24_V100_AI1_COMPLETED.json

AI2 standalone:
episode_input_v1/omg_e02_nov24_v1_0_0/07_AI2_STANDALONE_RU.md
Git blob: b8a18c8a553e1e6f1efee2bfbe4d348619795d59
Output: OMG_NOV24_V100_AI2_COMPLETED.json

Comparator:
episode_input_v1/engineering/OMG_NOV24_V100/compare_primary.py
Self-test: PASS_8_OF_8
Drive tasks: DISPATCHED.

## 4. KBM E05 V1.0.0

Route: AI_ONLY_PAIR_KBM_E05_V100
Input SHA-256:
51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95

AI1 standalone:
episode_input_v1/kbm_e05_v1_0_0/06_AI1_STANDALONE_RU.md
Git blob: bd1d89ac5b0aa046e8d4498cb3b19031dd2c60af
Output: KBM_E05_V100_AI1_COMPLETED.json

AI2 standalone:
episode_input_v1/kbm_e05_v1_0_0/07_AI2_STANDALONE_RU.md
Git blob: 0a39088aaa78bbf3c1a5e7300e1f3fe23e25438c
Output: KBM_E05_V100_AI2_COMPLETED.json

Comparator:
episode_input_v1/engineering/KBM_E05_V100/compare_primary.py
Self-test: PASS_8_OF_8
Drive tasks: DISPATCHED.

## Intake rule

When an output appears in Конфликтология/Почта:
1. preserve original bytes/content;
2. validate route/contract/rubric/input hash/role/attestation;
3. wait for sibling primary;
4. run only the frozen comparator;
5. if invalid => REJECT_INVALID_PRIMARY_RUN;
6. if mismatch => HOLD_DISAGREEMENT;
7. if shared UNKNOWN/DISPUTED => HOLD_FACTOR_INCOMPLETE;
8. only complete numeric consensus => replay eligibility, not automatic calculation;
9. any replay must use prospectively frozen exogenous RGU/KVPTN and unchanged Core.

Canonical completed scientific state remains:
OMG V1.0.1 = HOLD_FACTOR_INCOMPLETE / NOT_COMPUTABLE_FACTOR_INCOMPLETE.

Old OMG V1.0.0 company KVS=5 and Pol=50 remain superseded internal technical-demo values only.
