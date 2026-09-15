# ADR 0018: Method-safe Analysis V1 dashboard boundary

- Status: Accepted by owner for bounded R0 implementation
- Date: 2026-09-15
- Parent: `4a0f0cb42aaea8d9d5f368cdc3d3de15db2f6d03`
- Parent tree: `5c32368e80b645f16af8a064fb0ec79a40fef5f3`

## Decision

A new `/analysis/` Product shell is added without changing Production Studio or
Production Player.  The shell performs no domain ORM reads.  Foundation owns
all Analysis DTOs and admits the exact Project and Workspace before values are
queried.  Access requires both the existing zero-permission Project membership
group and a separate zero-permission `analysis-reader:<project_uuid>` capability
group.  This capability does not alter the exact G8 Django permission family.

R0 exposes only persisted POS and SAL values for an exact Experiment, Actor,
AnalyticalElement and TimeSlice.  It selects terminal `ParameterValue` rows by
`successor IS NULL`, fails closed on duplicate terminal rows and does not discard
a still-terminal value merely because its linked assessment later received a
successor.  UNKNOWN and other absent states remain null; numeric zero remains a
known zero.  Current G8 raw comparison remains unchanged and is not used as a
chart read model.

The Analysis shell reuses the existing G9 value-to-Fact and Fact-to-evidence
HTTP endpoints.  It creates no evidence store, no model, no migration and no
aggregate.  Project total score, UHO, regional aggregation, automatic weights,
prediction and recommendation remain `METHOD_NOT_APPROVED`.

All Analysis assets are same-origin and packaged locally.  The Content Security
Policy does not permit CDN scripts, external styles or public tile endpoints.
Layout preferences use a separate resolution-scoped key and never overwrite
Production Player layout state.  No assessment or evidence content is persisted
in browser storage.

## Consequences

R0 changes only the new Analysis app, bounded Foundation read services/API,
Django registration/URL wiring and Python package metadata.  It does not change
models, migrations, G7/G8/G9 services, Player, Studio, G10, workflows or package
builders.  Geography and map mutation require a later R1 owner decision.
