# AI_ONLY_RESEARCH_BETA_V1 — PROTOCOL PATCH 1

Status: FROZEN_BEFORE_AI1_AI2_FACTOR_RUNS
Date: 2026-09-28

This patch resolves two operational mismatches before any new POS/KVS factor answer exists.

1. The response status enum is `NUMERIC | UNKNOWN | DISPUTED`. The word `CODED` in the owner protocol is replaced only as an output token by `NUMERIC`, matching the frozen POS/KVS v1.2 rubric. No anchor meaning changes.
2. For this AI-only route only, G7 means protocol integrity of the two separately fixed AI runs: exact packet/version fixed before answers, separate primary outputs, no access to the other coder's output, immutable originals, and comparison only after both primary outputs. It does NOT assert HUMAN pilot or HUMAN reliability.

All G1-G6 content thresholds, POS/KVS anchors, UNKNOWN/DISPUTED semantics, evidence requirements, cutoff, actor/reference/time boundaries, RGU/KVPTN role, and Core rules remain unchanged.

If G1-G6 are not all true, NUMERIC is forbidden. G7 cannot repair an evidence failure.
