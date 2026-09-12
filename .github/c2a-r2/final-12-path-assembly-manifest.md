# C2A R2 final 12-path assembly manifest — control plane only

This document is a recovery/assembly oracle. It MUST NOT enter the final R2 commit. It exists to eliminate rediscovery and copy mistakes when paths 10–12 become green.

## Immutable lineage

- Accepted G9 HEAD: `561ef5327bf655a558adb21c54d0fdf0559d7024`
- Accepted G9 TREE: `5b209c782e1ac1a4783b01391dd59d813559ce57`
- Immutable R1 HEAD: `22f0f173a941de88d6920b6e19821168e9b30cc8`
- Immutable R1 TREE: `f407e609adb2a8b94770b521a1302feb79281822`
- R1 sole parent: exact accepted G9 HEAD above.
- Final R2 must be the sole ordinary fast-forward child of R1.
- Final topology over G9: exactly two commits, ordered G9 -> exact R1 -> exact R2; parent counts `(1, 1)`; no merge commit and no third commit.

## Exact R1 -> R2 correction delta

All twelve paths below must be `M` relative to R1, mode/type `100644 blob`, with no extra path.

| # | Path | Exact R1 preimage blob | Current replacement identity | State / source |
|---|---|---|---|---|
| 1 | `.github/workflows/conflict-analysis.yml` | `1aff0000c91366028f68c1e8ce381282fa3f4ed9` | `21c4b624d78f25670285f1699b67bd0d6e393f26` | PREPARED_ACCEPTED; workflow recovery run `34692057352` |
| 2 | `software/conflict_analysis/README.md` | `a3d587b988034b31acfc8e1c4e30db279520a46a` | `e0da5bcf5f24809f6ca788a1a8f6b0f0144bf1f3` | PREPARED_ACCEPTED |
| 3 | `software/conflict_analysis/docs/adr/0009-production-studio-c-lifecycle-publication.md` | `520dd4357052613b36fbf1f494b2650dc2bf5e95` | `c0889c969db86b55af2613fe2f633cfa2123866a` | PREPARED_ACCEPTED |
| 4 | `software/conflict_analysis/docs/production-studio-c-read-only-runtime.md` | `7e8009fc584091ef793ea6e7b6a95f7284036d4c` | `f50dd1fbc0cf967ad658327f37cd0ea70eba6a8f` | PREPARED_ACCEPTED |
| 5 | `software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs` | `f6ad2ff633d9c49ae4e5c69d5fff931b677e8af3` | `6ce3fededdae818d0b13b92ebc04bfff982e5162` | PREPARED_ACCEPTED; carrier `32e142d83a581913655878b10ea989575fce3e63` |
| 6 | `software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs` | `fa78a5b1c36d21916abc6d87f80dff1916765fdd` | `PENDING_PATH11_GREEN_BLOB` | PREBOUND_ONLY; oracle commit `e11c199109b7510405b739ac91e181f720802d41`, blob `12b1281178a905fdd0377a2734d13dfb54bda3bb` |
| 7 | `software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js` | `ee196705281982944e135a559fa6d7f0b4259734` | `f9ee82c148e1659c122024dd43a2f876348e6073` | CANDIDATE_NEEDS_COUPLED_GATES; carrier `e8af8eb8f137b760553d6dedc7f4b335869be61e`, tree `5fa4d96d3577fe585507309bec4a5a34b8160904` |
| 8 | `software/conflict_analysis/production_studio/templates/production_studio/lifecycle_publication_definition.html` | `7ef388ac952fb48104a0aa5a18b338e21cb432d0` | `a1e7e9f3fac0be61bbce6a2a4f6e8bb221f62101` | PREPARED_ACCEPTED |
| 9 | `software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py` | `6c2bb510f11a36db9b62138f637f09bf5588753a` | `PENDING_PATH10_GREEN_BLOB` | EXECUTOR_LANE PR #100; oracle commit `217ab93fe9b0941f960d4438b8d949b1498a8a7d`, blob `e271029f1f028702fd4f5e0aa6ddbd006c96b493` |
| 10 | `software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py` | `f74bd52abb55535411d0a6ed91acf35f15fe813b` | `4190bcc1871679a3b1e0a29f6991e3dc6876c912` | PREPARED_ACCEPTED |
| 11 | `software/conflict_analysis/production_studio/views.py` | `8d28a9ec84e0b981152542bc0589537d56f17679` | `955e715cb083f7e4467836ace77281de30ef1d39` | PREPARED_ACCEPTED |
| 12 | `software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py` | `2ee1c9efac4c314ca0144767e6893b3a9aae18c2` | `PENDING_PATH12_GREEN_BLOB` | PREBOUND_ONLY; verifier oracle commit `4cb990b1ec367abcc8db79f803ae94cf7a40f4ab`, blob `d7fb8630496a351b426d9d967357c2788b7d478b` |

Formal prepared count remains **8/12** until the lifecycle JS + path10 coupled portable gate is fully green. The path-7 blob above is deliberately not counted as prepared yet.

## Reachable partial assembly identities

- Accepted prepared 8/12 carrier: branch `agent/c2a-r2-prepared-8of12-carrier`, TREE `85eb00ed30263b49381c1994cb266754396c0683`.
- Nine-path lifecycle-JS candidate carrier: branch `agent/c2a-r2-lifecycle-js-p1be-candidate`, commit `e8af8eb8f137b760553d6dedc7f4b335869be61e`, TREE `5fa4d96d3577fe585507309bec4a5a34b8160904`, sole parent exact R1.
- Path10 executor branch `agent/c2a-r2-lifecycle-test-carrier` currently points to the same `e8af8eb8...` candidate until a test-file-only commit arrives.

Do not merge or cherry-pick any carrier. They are blob/tree preservation and execution lanes only.

## Aggregate G9 -> R2 invariant

Final aggregate must contain exactly **19 changed paths** relative to accepted G9:
- exactly **9 new** historical C2A paths;
- exactly **10 existing** paths.

The final 19-path aggregate is the historical R1 17-path allowlist plus exactly:
1. `software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs`
2. `software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py`

The final verifier must independently enforce this 19-path aggregate and the exact 12-path all-`M` R1 -> R2 correction delta.

## Promotion sequence after path10 arrives

1. Verify PR #100/head movement against `e8af8eb8...`: exactly one additional changed path, `test_lifecycle_publication.py`, status `M`; no other path.
2. Require Node 24 lifecycle JS `node --check` PASS, portable collection exactly 13, and `13 passed` with no skip/xfail/retry/timeout/assertion weakening.
3. Only then freeze exact path10 blob and construct/persist a reachable 10/12 carrier from immutable R1 using the eight accepted blobs + lifecycle JS candidate + green test blob.
4. Implement/validate path11 from its bound oracle; require exact two Chromium scenario names and both green at unchanged timeouts; persist exact path11 blob and reachable 11/12 carrier.
5. Implement verifier last from the bound verifier oracle; require exact topology/path/preimage/aggregate self-check negatives; persist exact path12 blob.
6. Construct the final R2 tree by replacing exactly the twelve entries in immutable R1 TREE with the twelve final blobs. Before any target ref movement, compare R1 -> candidate and G9 -> candidate and require all cardinalities/statuses/invariants above.
7. Only after full precommit PASS create the ordinary R2 child of exact R1 and update the target branch by normal fast-forward. No merge/rebase/cherry-pick/amend/squash/history rewrite/force-push.

## Frozen surfaces / prohibitions

PR #94 and `codex/ca-suite-i1-production-studio-c2a-lifecycle-publication` remain immutable at R1 until final validated R2. G10, calculation/modeling, release, old failed R1 CI rerun, timeout increases, retries, assertion weakening, and any correction path outside the exact twelve are forbidden.
