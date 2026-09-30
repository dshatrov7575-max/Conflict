# KBM E05 representation pair V1.0.0

**Status:** `FROZEN_BEFORE_PRIMARY_RESPONSES`  
**Route:** `AI_ONLY_PAIR_KBM_E05_V100`  
**Input SHA-256:** `51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95`  
**Frozen date:** 2026-09-30

## Purpose

Prospectively test a narrow representation/negotiation pair under E05 without treating retrospective allegations as company statements and without reusing E02 factors.

This is a non-simultaneous pair of dated source statements:
- company stance: 14.05.2011;
- worker demand: 27.05.2011;
- carry-forward: NONE;
- simultaneous snapshot: false.

## Worker inheritance

R2 unit `AO2S-C1-04` uses the same narrow worker actor, same E05 PTN/reference, and the same D04-FUNION source. Two independent R2 primary coders returned worker `POS=-5`, `KVS=5`; these entries did not require a new E05 company adjudication. The worker values are inherited only for eventual post-comparison replay and are hidden from the new company-only coders.

## Company evidence

A pre-cutoff Wayback replay exists for the 14.05.2011 Aktau-business republication of a KarazhanbasMunai company release:
- capture: `2011-05-15T05:47:06Z`;
- raw bytes: `58775`;
- SHA-256: `8c88985bf55e2cfa149395cb8e98de6d87798edcb9f18e614f58279935a8f63b`.

The source states the company's view on the internal union dispute, procedural legitimacy of removing the union chairman, negotiation methods, and collective-agreement commission work. Company POS/KVS are **not** preassigned.

## Primary protocol

Two fresh independent coders each code exactly:
1. company `POS_AO2`;
2. company `KVS_AO2`.

They receive only their standalone file. No external search, prior episode/AO2 outputs, known outcome, coordinator review, or sibling primary output.

Coordinator substitution: FORBIDDEN.  
Targeted content review rounds: 0.  
Rerun-until-number/model shopping: FORBIDDEN.

Only exact two-model numeric consensus on both company factors, including identical C1-C8, makes the pair eligible for a later read-only scenario replay.

Any UNKNOWN, DISPUTED, mismatch, or invalid attestation preserves HOLD.

`UNKNOWN != 0`.

No CalculationSnapshot, RGU/KVPTN, Pol, historical area UNO, HUMAN validation, probability, prediction or risk estimate is produced by this package.
