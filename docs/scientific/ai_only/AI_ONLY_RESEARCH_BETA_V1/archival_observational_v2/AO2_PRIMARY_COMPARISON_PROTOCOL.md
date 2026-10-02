# AO2 PRIMARY COMPARISON PROTOCOL

Status: FROZEN_BEFORE_PRIMARY_RESPONSES

Validate 12 unique item×factor entries from each primary coder. Permitted status: NUMERIC / UNKNOWN / DISPUTED. POS_AO2 anchors: -10,-5,0,5,10. KVS_AO2 anchors: 0,2,5,8,10. NUMERIC requires A1-A8 all true and at least one frozen evidence ID.

Primary routing:
1. Same NUMERIC anchor + compatible decisive evidence/rationale -> AO2_NUMERIC_CONSENSUS_CANDIDATE.
2. Different numeric anchors, NUMERIC vs UNKNOWN/DISPUTED, or materially different decisive evidence -> TARGETED_CRITIQUE_REQUIRED.
3. UNKNOWN + UNKNOWN with same decisive failed gates -> AO2_SHARED_UNKNOWN.
4. DISPUTED in either output -> AO2_DISPUTED.
5. Maximum one targeted critique round, on the same frozen evidence. No rerun-until-agreement, no model shopping, no averaging.

Coordinator verifies every numeric consensus candidate against the frozen rubric before any calculation use. Original primary outputs remain immutable. Any new evidence requires AO2 EFFECTIVE_INPUT_R2 and new primary runs.
