# KBM E02 demand→response dyad V1.0.0

**Status:** `FROZEN_BEFORE_PRIMARY_RESPONSES`  
**Route:** `AI_ONLY_DYAD_KBM_E02_V100`  
**Input SHA-256:** `d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42`  
**Frozen date:** 2026-09-30

## Purpose

Prospectively test whether a narrowly scoped company response in the May 2011 QarazhanbasMunai wage dispute yields reproducible company POS/KVS values under the already-fixed AO2 anchors and reactive-actor KVS rule.

This package does **not** preassign company POS/KVS. It does not create a historical same-date snapshot, a 15.12.2011 state, historical area UNO, probability, prediction, HUMAN validation or reliability.

## Temporal object

- initiating worker source statement: RFE/RL, `2011-05-17`, `D01-FPAY`;
- formal company response source statement: Nomad/Kazinform republication of KBM press-service material, page date `2011-05-27`, dateline `2011-05-26`;
- Wayback witness for company response: `2011-05-28T15:32:27Z`;
- simultaneous snapshot: `false`;
- carry-forward: `NONE`.

The earlier discovery note mistakenly used `2011-05-21` as the worker source date. That is the D01 Wayback capture date; the source-report date is `2011-05-17`. This package freezes the corrected date before primary responses.

## Worker inheritance

R2 unit `AO2S-C1-03` used the same narrow actor, same E02 PTN/reference and same D01-FPAY source. AI1 and AI2 independently returned `POS=-5` and `KVS=5` with all admission checks true; those two values were not created by targeted review. They are inherited only for eventual post-comparison dyad replay and are intentionally hidden from the company-only primary coders.

## Company evidence

The company source has a reproducible pre-cutoff Wayback replay. Raw payload was re-downloaded on 2026-09-30: `30312` bytes, SHA-256 `4280ad5774d94cae7efc788943301852550080c69c28a02fb99ddbadb4b9f06a`.

The source attributes the position to the KBM press service, describes KBM's own wage/tariff actions, rejects the contested pay-coefficient demands, gives salary/tariff figures, and reports repeated management proposals to resolve the dispute at the negotiating table.

## Primary protocol

Two independent company-only coders receive separate standalone files with identical frozen material. They code exactly:
1. company `POS_AO2`;
2. company `KVS_AO2`.

No external search, prior episode/AO2 outputs, outcome, or other coder output may be used. Targeted content review and coordinator substitution are forbidden.

Only exact two-model numeric consensus on both company factors, including identical C1-C8, makes the dyad eligible for a read-only scenario replay. Any UNKNOWN, DISPUTED, mismatch or invalid attestation preserves HOLD.

`UNKNOWN != 0`. RGU/KVPTN cannot repair missing POS/KVS. No merge is implied.
