# MVP7 OMG Episode E1 — Calculation Release Gate V1

**Status:** `FROZEN_BEFORE_EPISODE_PRIMARY_RESPONSES`

## Required evidence/coding conditions

1. Both independent episode responses validate against the frozen schema.
2. Attestations show no other primary output, external search, or outcome use.
3. The deterministic comparator classifies every factor entry.
4. At most one targeted review round is used.
5. Coordinator verifies each surviving numeric entry against the frozen
   evidence and rubric.
6. All four episode entries are numeric; otherwise release is blocked.
7. Original primary outputs remain immutable.

## Required design conditions

1. `EXOGENOUS_WEIGHT_DESIGN_V1` is the only weight provenance.
2. Baseline and sensitivity grid are unchanged after factor results are seen.
3. RGU/KVPTN are not inferred from evidence or outcome.
4. Main results use positive weights and fixed actor/PTN topology.
5. Zero-weight stresses are separated from the main envelope.

## Required technical conditions

1. Exact pinned Core identities are recorded.
2. Standalone sensitivity tests pass.
3. Baseline result replays exactly through the pinned Core.
4. Input and result digests are preserved.
5. Every noncomputable scenario remains in the report.

## Release outcomes

- `RELEASED_AS_AI_ONLY_EPISODE_SCENARIO`: all gates pass.
- `HOLD_FACTOR_INCOMPLETE`: any factor entry remains UNKNOWN/DISPUTED.
- `HOLD_COMPARATOR_OR_REVIEW`: primary comparison is unresolved.
- `HOLD_CORE_REPLAY_MISMATCH`: standalone and Core results differ.
- `HOLD_PROVENANCE`: source or design provenance is incomplete.

Even a released episode scenario is not:

- HUMAN validation;
- a December 2011 snapshot;
- an area-level historical UNO;
- predictive validation;
- a probability or risk estimate.
