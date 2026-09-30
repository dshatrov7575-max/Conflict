# Cross-lane aggregation boundary R1

**Status:** `FROZEN_BEFORE_NEW_PRIMARY_RESULTS`  
**Date:** 2026-09-30

## Purpose

Prevent accidental conversion of several bounded source-statement pair/dyad results into a historical multi-PTN snapshot or area-level UNO.

The current reproducible lanes are methodologically separate observational objects. Numeric completion of more than one lane does **not** authorize cross-lane aggregation.

## Lane boundaries

### KBM E02 V1.0.0

Route: `AI_ONLY_DYAD_KBM_E02_V100`.

PTN: E02.

Temporal object:
- worker source statement: 2011-05-17;
- company response source statement: 2011-05-27;
- simultaneous snapshot: false;
- carry-forward: NONE.

### KBM E05 V1.0.0

Route: `AI_ONLY_PAIR_KBM_E05_V100`.

PTN: E05.

Temporal object:
- company representation/negotiation stance: 2011-05-14;
- worker representation demand: 2011-05-27;
- simultaneous snapshot: false;
- carry-forward: NONE.

### OMG Nov23–24 V1.0.0

Route: `AI_ONLY_DYAD_OMG_NOV24_V100`.

PTN: E02.

Temporal object:
- bounded meeting episode: 2011-11-23..2011-11-24;
- source report date: 2011-11-30;
- simultaneous historical snapshot: false;
- carry-forward: NONE.

## Prohibited combinations

The following are forbidden unless a new prospective protocol is frozen **before** reviewing candidate combined results:

1. combining KBM E02 and KBM E05 into a two-PTN historical snapshot;
2. combining May KBM lanes with November OMG as if they were contemporaneous;
3. carrying any factor to 15.12.2011 without a separately frozen persistence/carry-forward rule and supporting evidence;
4. calculating historical area-level UNO from these lanes;
5. using a numeric value from one lane to repair UNKNOWN/DISPUTED in another lane;
6. averaging or pooling actor factors across different source dates or actor identities;
7. interpreting repeated actor identity across PTNs as evidence of temporal stability.

## Why aggregation is blocked

- the lanes have different temporal objects;
- source statements are not same-date measurements;
- no persistence rule is frozen;
- PTN coverage is incomplete for an area-level construct;
- actor scopes differ across routes;
- one lane's evidentiary completeness does not cure another lane's missingness.

## Allowed comparisons

The following are allowed as descriptive research outputs:

- compare whether separate lanes are computable or HOLD;
- compare factor coding agreement rates across lanes;
- compare sensitivity envelopes across independently eligible one-PTN scenarios;
- report that the same actor appears in more than one bounded source object;
- report differences in source/provenance quality.

Such comparisons must preserve each lane's own date, actor identity, PTN identity, source provenance and claim boundary.

## Future aggregation gate

A future multi-PTN or historical snapshot protocol must prospectively freeze, before coding/replay:

- target timestamp or event window;
- actor universe;
- PTN universe and completeness criterion;
- persistence/carry-forward rules;
- cross-source temporal admissibility;
- missing-data rule;
- multi-PTN KVPTN design;
- aggregation formula identity;
- release and claim boundaries.

Until then:
`CROSS_LANE_AGGREGATION_FORBIDDEN`.
