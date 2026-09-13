# C2A R2 final 12-path assembly manifest — control plane only

FORMAL_PREPARED_COUNT = **12/12**. PATH12 has been independently accepted by MAIN. Final assembly is **UNLOCKED for a new isolated final-staging branch only**.

This manifest, recipe, acceptance-chain consistency file and reachability proof are control-plane authority and MUST NOT enter final R2. Their accepted ledger supersedes historical 8/12 state, the unrepaired PATH9 candidate, and PATH10–PATH12 placeholders. Frozen preparation maps/oracles/procedures remain historical acceptance requirements; their path sets, preimages and immutable lineage do not change.

## Immutable lineage

- Accepted G9 HEAD: `561ef5327bf655a558adb21c54d0fdf0559d7024`
- Accepted G9 TREE: `5b209c782e1ac1a4783b01391dd59d813559ce57`
- Immutable R1 HEAD: `22f0f173a941de88d6920b6e19821168e9b30cc8`
- Immutable R1 TREE: `f407e609adb2a8b94770b521a1302feb79281822`
- R1 sole parent: exact G9 above.
- Final R2 sole parent: exact R1 above. Exactly one ordinary commit above R1 and exactly two above G9; parent counts `(1, 1)`.

## Exact accepted replacement ledger

All twelve paths must be `M` relative to R1 and remain `100644 blob`; no thirteenth path is allowed.

| # | Path | Exact R1 preimage | Accepted replacement | State |
|---|---|---|---|---|
| 1 | `.github/workflows/conflict-analysis.yml` | `1aff0000c91366028f68c1e8ce381282fa3f4ed9` | `21c4b624d78f25670285f1699b67bd0d6e393f26` | PREPARED_ACCEPTED |
| 2 | `software/conflict_analysis/README.md` | `a3d587b988034b31acfc8e1c4e30db279520a46a` | `e0da5bcf5f24809f6ca788a1a8f6b0f0144bf1f3` | PREPARED_ACCEPTED |
| 3 | `software/conflict_analysis/docs/adr/0009-production-studio-c-lifecycle-publication.md` | `520dd4357052613b36fbf1f494b2650dc2bf5e95` | `c0889c969db86b55af2613fe2f633cfa2123866a` | PREPARED_ACCEPTED |
| 4 | `software/conflict_analysis/docs/production-studio-c-read-only-runtime.md` | `7e8009fc584091ef793ea6e7b6a95f7284036d4c` | `f50dd1fbc0cf967ad658327f37cd0ea70eba6a8f` | PREPARED_ACCEPTED |
| 5 | `software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs` | `f6ad2ff633d9c49ae4e5c69d5fff931b677e8af3` | `6ce3fededdae818d0b13b92ebc04bfff982e5162` | PREPARED_ACCEPTED |
| 6 | `software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs` | `fa78a5b1c36d21916abc6d87f80dff1916765fdd` | `e49e21dff75e93452b94f09fc32caa36d6800eee` | PREPARED_ACCEPTED |
| 7 | `software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js` | `ee196705281982944e135a559fa6d7f0b4259734` | `db98c5f86b907e239708b7a20719241e714afbb2` | PREPARED_ACCEPTED |
| 8 | `software/conflict_analysis/production_studio/templates/production_studio/lifecycle_publication_definition.html` | `7ef388ac952fb48104a0aa5a18b338e21cb432d0` | `a1e7e9f3fac0be61bbce6a2a4f6e8bb221f62101` | PREPARED_ACCEPTED |
| 9 | `software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py` | `6c2bb510f11a36db9b62138f637f09bf5588753a` | `680f0a857f371162e2223623d441019269d1fede` | PREPARED_ACCEPTED |
| 10 | `software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py` | `f74bd52abb55535411d0a6ed91acf35f15fe813b` | `4190bcc1871679a3b1e0a29f6991e3dc6876c912` | PREPARED_ACCEPTED |
| 11 | `software/conflict_analysis/production_studio/views.py` | `8d28a9ec84e0b981152542bc0589537d56f17679` | `955e715cb083f7e4467836ace77281de30ef1d39` | PREPARED_ACCEPTED |
| 12 | `software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py` | `2ee1c9efac4c314ca0144767e6893b3a9aae18c2` | `a24654637b3eaeedca4a55b9894abfc2296b90f5` | PREPARED_ACCEPTED |

## Accepted validation ancestry

- PATH10 HEAD: `f8c5ef4a788ad1eb3461444b8e2cdd369ddc2fd2`; TREE `5396e037f651534e5ae39cdf0b727b66436cb90f`.
- Accepted remote PATH9 binding repair HEAD: `86a652accfc36c32b4d5a53524640411da9a7f06`; sole parent PATH10.
- PATH11 HEAD: `396b62e29ea34ed8aa6f9f10f5295439c547479f`; TREE `e5cf28324f255389edfb7ee1d5146ca40299f64b`; sole parent the accepted remote PATH9 repair.
- PATH12 HEAD: `d1342cb28b74025275f78b04492f81a60075e0c8`; TREE `6ad7c8463988aab3b02e4f85aba50f370380c478`; sole parent PATH11.
- The twelve accepted replacement blobs are reachable from PATH12. This validation chain supplies blobs only and MUST NOT become final R2 history. Local repair commit `1437ebb303ed3f42ef7e2c519223d7c048be0294` is not the accepted validation predecessor.

## Final assembly and verification

1. Require the recipe, this manifest, reachability proof and acceptance-chain pins to agree on all twelve replacements and R1 preimages.
2. Start from exact immutable R1 TREE and replace only the twelve listed entries. The resulting tree must equal `6ad7c8463988aab3b02e4f85aba50f370380c478`.
3. Create exactly one ordinary R2 child of immutable R1 and publish only a new isolated final-staging branch.
4. Prove R1 -> R2 is exactly 12 M paths; G9 -> R2 is exactly 19 paths = 9 A + 10 M. The aggregate is the historical 17-path R1 allowlist plus exactly audited_authoring.mjs and test_read_only_static_contracts.py.
5. Require assembled verifier syntax/self-check and dedicated R2 topology PASS, exact replacement/readback proofs, and PR #94 OPEN/DRAFT/UNMERGED at immutable R1.
6. Full CI must subsequently run against the exact staged HEAD with fresh same-run evidence, migration/no-drift, wheel/install, workflow-contract and synthetic-tree equivalence gates. Staging readiness does not assert full exact-head CI acceptance.

## Frozen surfaces and publication boundary

PR #94, `codex/ca-suite-i1-production-studio-c2a-lifecycle-publication` and the G9 branch remain unchanged. Do not promote staging to target. No merge/rebase/cherry-pick/amend/squash/history rewrite/force push, release or G10. No workflow or product changes beyond the already accepted twelve replacement blobs are authorized by this assembly.
