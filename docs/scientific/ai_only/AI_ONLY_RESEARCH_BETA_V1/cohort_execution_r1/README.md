# Cohort Execution R1

Deterministic intake/orchestration layer for `AI_ONLY_REPLICATION_COHORT_R1_20260930`.

It does not execute models. It consumes returned primary JSON files, invokes only the frozen lane comparators, then invokes the frozen cohort aggregator.

Expected input filenames:
- KBM_E02_V100_AI1_COMPLETED.json
- KBM_E02_V100_AI2_COMPLETED.json
- OMG_NOV24_V100_AI1_COMPLETED.json
- OMG_NOV24_V100_AI2_COMPLETED.json
- KBM_E05_V100_AI1_COMPLETED.json
- KBM_E05_V100_AI2_COMPLETED.json
- D25_E02_V100_AI1_COMPLETED.json
- D25_E02_V100_AI2_COMPLETED.json

Rules:
- missing files remain unresolved;
- comparator validation failure is recorded as `REJECT_INVALID_PRIMARY_RUN`;
- no replacement, adjudication, averaging, rerun or repair is attempted;
- sensitivity and Core replay are not run automatically;
- eligible lanes are only flagged for the separately frozen Core/sensitivity gate.

This script is scientific workflow plumbing only. It does not change factor values, cohort membership, weights, claims, or release criteria.
