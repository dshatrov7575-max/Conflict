# D25 E02 V1.0.0 — deterministic comparison and release gate

Status: FROZEN_BEFORE_PRIMARY_RESPONSES
Input SHA-256: aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa

Required roles:
- D25_E02_V100_AI1
- D25_E02_V100_AI2

Each output must contain exactly four unique actor×factor entries:
- D25_DISMISSED_KMG_EP_WORKERS_20111013 × POS_AO2
- D25_DISMISSED_KMG_EP_WORKERS_20111013 × KVS_AO2
- D25_KMG_EP_MANAGEMENT_20111013 × POS_AO2
- D25_KMG_EP_MANAGEMENT_20111013 × KVS_AO2

Both outputs require:
- route AI_ONLY_DYAD_D25_E02_V100;
- contract 1.0.0;
- rubric 2.1.0;
- identical frozen input SHA;
- different non-empty run IDs;
- clean attestations including prior_r2_outputs_seen=false;
- calculation_release=false for each primary entry.

NUMERIC requires licensed anchor and all C1-C8 true.
UNKNOWN requires null value and at least one failed gate.
DISPUTED requires null value.

Pair comparison:
- same NUMERIC value + identical C1-C8 => CONSENSUS_NUMERIC;
- same UNKNOWN/null + identical C1-C8 => SHARED_UNKNOWN;
- same DISPUTED/null + identical C1-C8 => SHARED_DISPUTED;
- otherwise => HOLD_DISAGREEMENT.

Release:
- invalid primary => REJECT_INVALID_PRIMARY_RUN;
- any mismatch => HOLD_DISAGREEMENT;
- any shared UNKNOWN/DISPUTED => HOLD_FACTOR_INCOMPLETE;
- all four CONSENSUS_NUMERIC => ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY.

No coordinator substitution, targeted content review, averaging, vote, rerun-until-number, replacement-model shopping or UNKNOWN→0.

No previous R2 factor value is inherited or used to adjudicate this lane.

Even all-numeric consensus remains a same-report AI-only source-statement dyad, not an exact historical snapshot, 15.12.2011 state, historical area UNO, HUMAN validation, probability, prediction or risk validation.
