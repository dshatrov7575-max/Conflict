# AI_ONLY_RESEARCH_BETA_V1 — PRIMARY LAUNCH INDEX R3

Date: 2026-09-30
PR: #123
Branch: review/ai-only-research-beta-v1
Status: coordination index only.

Global rules:
- fresh independent model/chat per primary role;
- model receives ONLY its exact standalone;
- no prior AO2/R2/episode outputs, known outcome, coordinator notes, launch index, sibling output, or external search;
- preserve primary JSON unchanged;
- no rerun-until-number, model shopping, averaging, coordinator substitution, targeted content review, or UNKNOWN→0.

## Lane 0 — OMG V1.0.2

Route: AI_ONLY_DYAD_OMG_E1_V102
State: FROZEN_BEFORE_PRIMARY_RESPONSES
Launch: BLOCKED_DELIVERY_ARTIFACT_UNAVAILABLE

Exact frozen ZIP required:
MVP7_OMG_COMPANY_DECISION_V102_10_FILES_20260929.zip
SHA-256:
0c49038129f070c730d27ea4a095d849d4ef943ae2582fcfed00d86ea6520a7f

Recovery-only Drive task exists. Reconstruction/regeneration is forbidden.

## Lane 1 — KBM E02 V1.0.0

Route: AI_ONLY_DYAD_KBM_E02_V100
Input SHA: d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42
AI1 blob: 4d894bf841912788ec534904c05f53a3076bee3b
AI2 blob: 64d02513711034941da014bd40024e506a68b020
Outputs:
- KBM_E02_V100_AI1_COMPLETED.json
- KBM_E02_V100_AI2_COMPLETED.json
Comparator: engineering/KBM_E02_V100/compare_primary.py
Self-test: PASS_8_OF_8
Drive tasks: DISPATCHED.

## Lane 2 — OMG Nov23–24 V1.0.0

Route: AI_ONLY_DYAD_OMG_NOV24_V100
Input SHA: 72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4
AI1 blob: 83473066a90daf00bc2a9413cb0175d25f54b60a
AI2 blob: b8a18c8a553e1e6f1efee2bfbe4d348619795d59
Outputs:
- OMG_NOV24_V100_AI1_COMPLETED.json
- OMG_NOV24_V100_AI2_COMPLETED.json
Comparator: engineering/OMG_NOV24_V100/compare_primary.py
Self-test: PASS_8_OF_8
Drive tasks: DISPATCHED.

## Lane 3 — KBM E05 V1.0.0

Route: AI_ONLY_PAIR_KBM_E05_V100
Input SHA: 51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95
AI1 blob: bd1d89ac5b0aa046e8d4498cb3b19031dd2c60af
AI2 blob: 0a39088aaa78bbf3c1a5e7300e1f3fe23e25438c
Outputs:
- KBM_E05_V100_AI1_COMPLETED.json
- KBM_E05_V100_AI2_COMPLETED.json
Comparator: engineering/KBM_E05_V100/compare_primary.py
Self-test: PASS_8_OF_8
Drive tasks: DISPATCHED.

## Lane 4 — D25 E02 V1.0.0

Route: AI_ONLY_DYAD_D25_E02_V100
Input SHA: aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa
AI1 blob: 2b0dcd8ee954f68d74b11b8bcbf299dfb9e2da33
AI2 blob: 2911bd6975184b9d9f1faf2aa235d6322eae7152
Outputs:
- D25_E02_V100_AI1_COMPLETED.json
- D25_E02_V100_AI2_COMPLETED.json
Comparator: engineering/D25_E02_V100/compare_primary.py
Raw comparator execution: PENDING due exhausted Desktop Commander monthly limit.
Drive tasks: DISPATCHED.

D25 is a fresh replication, not an inheritance lane. Prior R2 values are hidden and may not be used for adjudication.

## Exogenous weight design

Common immutable grid:
exogenous_weight_design_v2/SENSITIVITY_GRID_V2.json

For KBM E02, OMG Nov24, KBM E05:
exogenous_weight_design_v2/LANE_BINDINGS.json

For D25:
exogenous_weight_design_v2/D25_BINDING_EXTENSION_R1.json

The grid was frozen before new primary results. No weight may be tuned to outputs.

## Intake rule

When a completed JSON appears in Google Drive / Конфликтология / Почта:
1. preserve original content;
2. identify route/role;
3. validate frozen identity/hash/attestation;
4. wait for sibling primary;
5. run only the frozen comparator;
6. invalid => REJECT_INVALID_PRIMARY_RUN;
7. mismatch => HOLD_DISAGREEMENT;
8. shared UNKNOWN/DISPUTED => HOLD_FACTOR_INCOMPLETE;
9. all required entries numeric consensus => replay eligibility only;
10. sensitivity/replay uses only the frozen exogenous grid and unchanged Core;
11. cross-lane aggregation remains forbidden.

Canonical completed scientific state remains OMG V1.0.1 HOLD_FACTOR_INCOMPLETE / NOT_COMPUTABLE_FACTOR_INCOMPLETE.
Old OMG V1.0.0 company KVS=5 and Pol=50 remain superseded internal-demo values only.
