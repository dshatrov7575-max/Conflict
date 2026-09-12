# C2A R2 final verifier acceptance oracle

Purpose: pre-bind the last correction path while lifecycle JS/tests are being completed, so the verifier can be implemented without another discovery pass. This document changes no Product/runtime path and grants no new authority.

## Fixed identities

- Accepted G9 HEAD: `561ef5327bf655a558adb21c54d0fdf0559d7024`
- Accepted G9 TREE: `5b209c782e1ac1a4783b01391dd59d813559ce57`
- Immutable R1 HEAD: `22f0f173a941de88d6920b6e19821168e9b30cc8`
- Immutable R1 TREE: `f407e609adb2a8b94770b521a1302feb79281822`
- R1 sole parent: accepted G9 HEAD

Historical R1 verification remains valid as the original one-commit C2A delivery. Final R2 verification is a separate, dedicated two-commit topology contract. Do not weaken or repurpose `_require_single_fast_forward_commit`; FD02/FD07 and historical users keep their current semantics.

## Final R2 topology

Add a dedicated `_require_c2a_r2_topology(...)` (name may vary only if semantics are identical) that requires all of the following simultaneously:

1. exact base is accepted G9 HEAD/TREE;
2. exactly two commits above G9;
3. ordered commit 1 is exact immutable R1 HEAD;
4. R1 sole parent is exact G9 HEAD and its tree is exact immutable R1 TREE;
5. ordered commit 2 is the final R2 delivery and is not any fixed predecessor;
6. R2 sole parent is exact R1 HEAD;
7. parent counts are exactly `(1, 1)`; merge ancestry fails closed;
8. G9 -> R1 path delta is the historical exact C2A 17-path aggregate (`C2A_POST_F0L_ALLOWLIST`), with its original 9 added + 8 modified shape;
9. R1 -> R2 delta is exactly the 12 correction paths below and every status is `M`;
10. G9 -> R2 aggregate is exactly 19 paths, with 9 new and 10 existing;
11. a third commit, R1-only state, wrong R1 object/tree/parent, wrong R2 parent, path/status drift, or aggregate drift is rejected.

## Exact R1 -> R2 correction set (12, all M)

1. `.github/workflows/conflict-analysis.yml`
2. `software/conflict_analysis/README.md`
3. `software/conflict_analysis/docs/adr/0009-production-studio-c-lifecycle-publication.md`
4. `software/conflict_analysis/docs/production-studio-c-read-only-runtime.md`
5. `software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs`
6. `software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs`
7. `software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js`
8. `software/conflict_analysis/production_studio/templates/production_studio/lifecycle_publication_definition.html`
9. `software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py`
10. `software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py`
11. `software/conflict_analysis/production_studio/views.py`
12. `software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py`

Declare this as an exact set, not prefix matching.

## Exact R1 preimages for the 12 modified paths

All entries must be ordinary `100644 blob` objects at immutable R1 before R2 modifies them:

- `.github/workflows/conflict-analysis.yml` -> `1aff0000c91366028f68c1e8ce381282fa3f4ed9`
- `software/conflict_analysis/README.md` -> `a3d587b988034b31acfc8e1c4e30db279520a46a`
- `software/conflict_analysis/docs/adr/0009-production-studio-c-lifecycle-publication.md` -> `520dd4357052613b36fbf1f494b2650dc2bf5e95`
- `software/conflict_analysis/docs/production-studio-c-read-only-runtime.md` -> `7e8009fc584091ef793ea6e7b6a95f7284036d4c`
- `software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs` -> `f6ad2ff633d9c49ae4e5c69d5fff931b677e8af3`
- `software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs` -> `fa78a5b1c36d21916abc6d87f80dff1916765fdd`
- `software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js` -> `ee196705281982944e135a559fa6d7f0b4259734`
- `software/conflict_analysis/production_studio/templates/production_studio/lifecycle_publication_definition.html` -> `7ef388ac952fb48104a0aa5a18b338e21cb432d0`
- `software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py` -> `6c2bb510f11a36db9b62138f637f09bf5588753a`
- `software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py` -> `f74bd52abb55535411d0a6ed91acf35f15fe813b`
- `software/conflict_analysis/production_studio/views.py` -> `8d28a9ec84e0b981152542bc0589537d56f17679`
- `software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py` -> `2ee1c9efac4c314ca0144767e6893b3a9aae18c2`

The verifier must prove each R1 preimage exactly and require that the R2 entry remains a regular `100644 blob` with a different object id.

## Final aggregate declarations

Keep the original historical `C2A_POST_F0L_ALLOWLIST` unchanged for R1/history verification.

Define the R2 aggregate as:

`C2A_R2_FINAL_AGGREGATE_ALLOWLIST = C2A_POST_F0L_ALLOWLIST | { audited_authoring.mjs, test_read_only_static_contracts.py }`

This must prove:

- aggregate paths = 19;
- `C2A_NEW_PATHS` remains exactly 9 and unchanged;
- existing paths = 10;
- the two newly admitted existing aggregate paths are exactly:
  - `software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs`
  - `software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py`.

For accepted-G9 preimage accounting, the final existing-path map is the current 8-path `C2A_EXISTING_BASE_BLOBS` plus:

- `production_studio/browser_tests/audited_authoring.mjs` -> `f6ad2ff633d9c49ae4e5c69d5fff931b677e8af3`
- `production_studio/tests/test_read_only_static_contracts.py` -> `f74bd52abb55535411d0a6ed91acf35f15fe813b`

Because both were unchanged by R1, those identities are also their accepted-G9 preimages.

## Frozen-surface adaptation

Do not globally weaken `C2A_FROZEN_PATHS`. For final R2 mode only, exempt exactly `production_studio/browser_tests/audited_authoring.mjs` because it is now an authorized correction path. `test_read_only_static_contracts.py` is also authorized through the exact R2 delta/aggregate contract. Every other historical C2A frozen path remains byte/mode identical to accepted G9/R1 as applicable.

No models, migrations, schemas, `pyproject.toml`, domain lifecycle/persistence authority, G9 evidence semantics, `cdp_client.mjs`, or other path may drift.

## Self-check negatives required before acceptance

The verifier self-check must explicitly reject at least:

- R1-only / one commit above G9;
- three commits above G9;
- wrong first commit instead of exact R1;
- wrong R1 parent;
- wrong R1 TREE;
- R2 parent not exact R1;
- parent count 2 / merge commit;
- missing one of the exact 12 R2 delta paths;
- an added 13th R2 correction path;
- any R2 delta status other than `M`;
- G9 aggregate with 18 or 20 paths;
- wrong 9-new / 10-existing partition;
- any of the 12 R1 preimage blobs/modes drifting;
- audited_authoring/static-test exception leaking into any broader freeze exception.

The positive self-check must prove exactly G9 -> immutable R1 -> one ordinary R2 child, exact 12 M correction delta, exact 19 aggregate, and exact 9/10 new/existing split.

## Existing test/cardinality contracts remain fixed

Do not change the C2A registry:

- portable: exact 13 methods in `ProductionStudioLifecyclePublicationTests`;
- Chromium: exact 2 existing scenario method names;
- no module-level or extra test nodes.

The final verifier still must validate same-run evidence, migration/no-drift, wheel/isolated install, workflow contract and synthetic-tree equivalence. Expected totals are acceptance targets, not substitutes for executed evidence.

No merge, rebase, cherry-pick, amend, squash, reset/history rewrite, force-push, release, G10 or target PR #94 mutation is authorized by this oracle.