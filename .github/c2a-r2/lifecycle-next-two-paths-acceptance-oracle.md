# C2A R2 acceleration oracle — lifecycle portable + Chromium paths

Purpose: pre-bind the exact acceptance work for the two test paths that follow `lifecycle_publication.js`, so MAIN does not idle while the JS candidate is being regenerated.

Immutable base: `22f0f173a941de88d6920b6e19821168e9b30cc8`.
Final correction scope remains exact 12 M paths / 19 aggregate. PR #94 and its target branch remain immutable until final R2.

## Path 10/12 — `production_studio/tests/test_lifecycle_publication.py`

Do not add a new test node. Preserve the accepted 13 portable + 2 Chromium registry cardinality.

Existing assertions that are now obsolete and must be rewritten in-place:

1. `test_publication_requires_human_retained_recovery_ticket_and_busy_unload_is_guarded`
   - remove the old positive expectation for `retainTicket("download")`;
   - assert download initiation is NOT retention proof;
   - assert exact-copy remains accepted only when text is byte-identical to `memory.sealedAttempt.ticketText`;
   - assert the corrected template controls `ticket-file-proof` and `acknowledge-ticket-file` are bound and byte-exact file re-import is the only second retention mechanism;
   - assert POST remains disabled for download-only, malformed copy, wrong file bytes, or cross-kind ticket proof.

2. `test_recovery_ticket_and_post_share_one_frozen_attempt_and_edits_require_new_operation`
   - keep validation contract `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` and its exact immutable FD05 request identity;
   - add a distinct publication contract `FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1`;
   - publication ticket exact keys must be only: `contract`, `contract_version`, `project_id`, `definition_id`, `operation_id`, `operation_kind`, `expected_manifest_hash`, `request_body_sha256`;
   - publication ticket must not contain POST reconstruction fields such as route, method, body bytes, If-Match, content type, CSRF/cookie/role/capability/credentials;
   - validation ticket import may restore only explicit byte-identical FD05 reconciliation;
   - publication ticket import may restore only exact FD06 operation GET identity and must never create/replace `sealedAttempt` or enable publication POST.

3. Fold P1-E checks into an existing typed-failure test rather than adding a test:
   - finite status/operation-compatible code map only;
   - unknown/malformed/control/bidi server codes map to bounded generic states;
   - 404 remains non-fingerprinting (`FOUNDATION_OBJECT_NOT_VISIBLE` or the binding bounded equivalent);
   - authentication loss, presentation denial, stale/conflict, claim-contract failure and unverified transport/representation remain distinct bounded states;
   - arbitrary exception/detail prose or raw `body.code` must never be rendered.

Cross-kind misuse oracle: validation ticket in the publication import path and publication ticket in the validation replay path must fail closed with zero mutation.

## Path 11/12 — `production_studio/browser_tests/lifecycle_publication.mjs`

Do not add a scenario. Keep the same two Chromium scenario names and the 60s CDP timeout.

Harness updates:
- `acknowledgeTicket(...)` must no longer assume every ticket is `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1`; assert contract by prepared operation kind;
- use exact-copy proof in one accepted flow and the corrected file-proof path in the other accepted flow, so both HUMAN retention mechanisms are covered without adding a test node;
- download click alone must leave `execute-sealed-attempt` disabled.

Initial-publication scenario:
- retain the existing exact single publication POST invariant;
- after unknown publication outcome, process-loss recovery must be able to proceed from the publication ticket by exact operation GET only;
- prove no second POST to the publication route occurs.

Successor scenario — required process-loss strengthening:
1. keep the existing validation lost-response / tab-loss flow and explicit byte-identical FD05 replay;
2. prepare and retain the SUCCESSOR publication ticket under the publication contract;
3. force the publication response loss;
4. close the page/target after the unknown outcome;
5. create a fresh page/target and navigate back under the same pre-issued session;
6. paste the saved publication ticket into `#import-publication-ticket` and invoke `#import-publication-ticket-action`;
7. wait only for `studio:lifecycle-publication-recovery-complete` (or the bounded failure oracle);
8. assert the recovered operation id equals the saved publication ticket operation id;
9. assert request log contains exactly one publication POST total and the post-loss action adds only the exact Foundation publication-operation GET;
10. assert no publication ticket field or operation data is written to localStorage/sessionStorage/IndexedDB/cache/service worker state.

Negative browser assertions must remain within existing scenarios/helpers: publication ticket must not unlock `#replay-validation-attempt`; validation ticket must not activate publication recovery; malformed or cross-kind import yields zero mutation.

## Execution order

Only after the JS candidate is durably persisted and Node 24 syntax/self-check passes:
1. modify/validate `test_lifecycle_publication.py` in-place without changing test count;
2. modify/validate `lifecycle_publication.mjs` in-place without changing scenario count;
3. run the existing portable + real Chromium lifecycle gates;
4. preserve each passing path as a durable blob/carrier before moving on;
5. verifier remains last because it depends on the final exact 12-path inventory/topology.

No retry, timeout increase, assertion weakening, new path, merge/rebase/cherry-pick/amend/squash/force-push/release/G10.