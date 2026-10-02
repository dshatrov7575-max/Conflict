# KBM E05 V1.0.0 — deterministic comparison and release gate

Status: FROZEN_BEFORE_PRIMARY_RESPONSES
Input SHA-256: 51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95

Required roles:
- KBM_E05_V100_AI1
- KBM_E05_V100_AI2

Each output must contain exactly two unique company factor entries:
- POS_AO2
- KVS_AO2

Identity requirements:
- route AI_ONLY_PAIR_KBM_E05_V100;
- contract 1.0.0;
- rubric 2.1.0;
- identical frozen input SHA;
- different non-empty run IDs;
- clean attestations;
- calculation_release=false in every primary entry.

Per-entry validation:
- POS numeric anchors: -10,-5,0,5,10;
- KVS numeric anchors: 0,2,5,8,10;
- NUMERIC requires all C1-C8 true;
- UNKNOWN requires null value and at least one failed gate;
- DISPUTED requires null value.

Pair comparison:
- same NUMERIC value + identical C1-C8 => CONSENSUS_NUMERIC;
- same UNKNOWN/null + identical C1-C8 => SHARED_UNKNOWN;
- same DISPUTED/null + identical C1-C8 => SHARED_DISPUTED;
- otherwise => HOLD_DISAGREEMENT.

Release state:
- invalid primary => REJECT_INVALID_PRIMARY_RUN;
- any mismatch => HOLD_DISAGREEMENT;
- any shared UNKNOWN/DISPUTED => HOLD_FACTOR_INCOMPLETE;
- both company factors CONSENSUS_NUMERIC => ELIGIBLE_FOR_READ_ONLY_PAIR_SCENARIO_REPLAY.

Inherited worker record, used only after successful company comparison:
- unit AO2S-C1-04;
- worker POS=-5;
- worker KVS=5;
- source report date 2011-05-27;
- carry-forward NONE.

Forbidden:
- coordinator substitution;
- targeted content review;
- averaging;
- majority vote;
- rerun-until-number;
- replacement-model shopping;
- UNKNOWN to zero;
- RGU/KVPTN adjustment to bypass missing factors.

Even an all-numeric result remains a non-simultaneous source-statement pair. It is not a historical same-date snapshot, a 15.12.2011 state, historical area UNO, HUMAN validation, probability, prediction or risk validation.
