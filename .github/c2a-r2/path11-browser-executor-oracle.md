# C2A R2 path 11 — lifecycle Chromium executor oracle

Authority: active C2A R2 correction under Issue #68 / staging Issue #95. Recovery/control-plane document only; MUST NOT enter the final exact 12-path R2 commit.

## Immutable inputs

- R1: `22f0f173a941de88d6920b6e19821168e9b30cc8`.
- R1 browser harness blob: `fa78a5b1c36d21916abc6d87f80dff1916765fdd`.
- Final path-9 lifecycle JS candidate blob: `f9ee82c148e1659c122024dd43a2f876348e6073`.
- Corrected template blob: `a1e7e9f3fac0be61bbce6a2a4f6e8bb221f62101`.
- Path 10 must already be green before promotion of this path; this oracle is prebinding only.

## Registry and timeout invariants

Modify exactly:
`software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs`

Keep the existing scenario registry at exactly two names:
1. `test_chromium_draft_preview_atomic_initial_publish_recover_and_reload`
2. `test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent`

Do not add/remove/rename scenarios. Keep `STUDIO_CDP_TIMEOUT_MS` default `60000`; keep the Python wrapper subprocess timeout `300`; no retry, sleep, timeout increase, assertion weakening, or `cdp_client.mjs` change.

## Exact R1 gaps to repair in-place

### A. Event capture

R1 `EVENT_NAMES` has validation-ticket import but not publication-ticket import. Add only the final-JS event needed for process-loss proof:
`studio:lifecycle-publication-ticket-imported`.

Do not introduce persistent browser storage for tickets, operation IDs, receipts, or hashes.

### B. Ticket acknowledgement helper

R1 `acknowledgeTicket()` hardcodes `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` and requires `ticket_sha256`; this is invalid for publication tickets.

Refactor/parameterize the existing helper rather than adding scenarios:
- VALIDATE_DEFINITION -> contract `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1`; keep full HUMAN ticket / `ticket_sha256` assertions.
- PUBLISH_INITIAL / PUBLISH_SUCCESSOR -> contract `FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1`; assert exact publication ticket semantics and no HUMAN-only `ticket_sha256` assumption.
- Before either accepted retention proof, click `#download-recovery-ticket` in at least one publication flow and prove `#execute-sealed-attempt` remains disabled: download initiation alone is not retention.
- Use exact-copy proof in one accepted publication flow.
- Use byte-exact saved-file re-import through `#ticket-file-proof` + `#acknowledge-ticket-file` in the other accepted publication flow.
- The emitted retained methods must be exactly `exact-copy` or `byte-exact-file` as applicable.

### B1. Exact byte-file proof implementation seam — no cdp_client change

The corrected template exposes `<input id="ticket-file-proof" type="file">` and button `#acknowledge-ticket-file`. R1 `CDPClient.send()` is generic and already supports arbitrary protocol methods, so `cdp_client.mjs` must stay frozen.

Implement byte-exact file proof inside `lifecycle_publication.mjs` only:
1. create one disposable temp file containing the exact saved ticket text bytes, including terminal LF; do not normalize/reformat JSON;
2. use the existing page session with CDP `DOM.getDocument`, `DOM.querySelector` for `#ticket-file-proof`, then `DOM.setFileInputFiles` with exactly that temp file path;
3. click `#acknowledge-ticket-file` normally and require `studio:lifecycle-ticket-retained` with method `byte-exact-file`;
4. delete the temp file/directory in a `finally` path even on failure;
5. no persistent browser storage or project-tree file may be used for this proof.

Do not emulate file selection by assigning `.value` or fabricating `input.files` in page JavaScript; the proof must exercise the actual file-input path used by `File.arrayBuffer()` in final JS.

### C. Initial publication scenario — one POST only

Preserve preview/editor -> publisher -> initial publication semantics.

After the intentionally lost FD06 response:
- unknown outcome must be observed for `PUBLISH_INITIAL`;
- recovery may use only the exact operation-status GET;
- total requests to the initial publication POST path must remain exactly **1**;
- no publication POST may be reconstructed by ticket import/recovery;
- final persisted state remains PUBLISHED/current and storage boundary remains empty of operation/ticket data.

This scenario may use the same-page recovery button; process-loss publication import is mandatory in the successor scenario below.

### D. Successor scenario — validation replay stays distinct

Preserve the existing validation process-loss proof:
- retain HUMAN validation ticket;
- force lost FD05 response;
- close the page;
- create a fresh page with the same pre-issued publisher session;
- explicitly reapply the same `publisherSessionCookieValue` to the fresh page via existing `setSessionCookie`; this reuses the already-issued session and must not mint credentials/session state;
- import through `#import-recovery-ticket` + `#import-validation-ticket`;
- explicit `#replay-validation-attempt` performs the same FD05 request only;
- exactly two validation POSTs total with identical Idempotency-Key, If-Match and `{}` body.

Validation-ticket semantics must not be replaced by publication GET-only semantics.

### E. Successor publication — mandatory process-loss GET-only import

Replace R1 same-page publication recovery with the final process-loss proof:
1. prepare `PUBLISH_SUCCESSOR` and retain the exact publication ticket bytes;
2. assert contract `FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1`, operation kind `SUCCESSOR`, and a different operation ID from the validation ticket;
3. force loss of the single successor publication POST response;
4. observe `studio:lifecycle-unknown-outcome`;
5. record the request-log cutoff, close the page, create a fresh page, explicitly reapply only the same pre-issued publisher session cookie, and navigate normally;
6. fill `#import-publication-ticket` with the saved exact publication ticket bytes;
7. click `#import-publication-ticket-action`;
8. observe `studio:lifecycle-publication-ticket-imported`, then wait only for `studio:lifecycle-publication-recovery-complete` or the already-bounded recovery failure state;
9. recovered operation ID must equal the saved publication ticket operation ID;
10. across the entire scenario there must be exactly **1** successor publication POST;
11. after the loss/cutoff, publication recovery traffic for that operation must contain the exact operation-status **GET** and no publication POST;
12. final predecessor/noncurrent and successor/current persisted truth remains unchanged.

### F. Cross-kind fail-closed negatives inside existing scenarios

Without adding a third scenario, prove zero-mutation cross-kind misuse:
- HUMAN validation ticket submitted to `#import-publication-ticket` / `#import-publication-ticket-action` is rejected and causes no publication POST;
- publication ticket submitted to `#import-recovery-ticket` / `#import-validation-ticket` is rejected and causes no validation replay POST;
- after each negative, clear/reset the import control as needed and continue with the valid contract path.

Use request-count baselines around each negative so rejection is demonstrated by zero mutation, not merely by UI text.

## Storage / request accounting acceptance

For both scenarios preserve `assertStorageBoundary` and include all retained ticket text and operation IDs in forbidden values after recovery. Browser persistent storage must contain none of them.

The final harness must make request accounting explicit:
- initial publication POST count = 1;
- successor publication POST count = 1;
- validation POST count in successor scenario = 2, identical same-request reconciliation;
- publication process-loss recovery after page close = exact operation GET only;
- cross-kind negative imports = zero mutation.

For process-loss publication recovery, define the request-log cutoff immediately after observing `studio:lifecycle-unknown-outcome` and before closing the old page. After the fresh-page import, filter requests after that index and require the exact operation endpoint GET while rejecting any POST to either publication route.

## Promotion gates

Before counting path 11 prepared:
1. exact one-path `M` delta for `lifecycle_publication.mjs` relative to the accepted path-10 carrier/state;
2. Node 24 `node --check` PASS for the browser harness and lifecycle JS;
3. portable registry remains exactly 13;
4. Chromium registry remains exactly the existing 2 C2A scenario names;
5. run both existing C2A Chromium scenarios with `STUDIO_CDP_TIMEOUT_MS=60000` and no retry/timeout change;
6. both PASS with request counts and storage assertions above;
7. persist exact candidate blob/tree before further work.

PR #94 / target branch remain immutable. No merge, rebase, cherry-pick, amend, squash, history rewrite, force push, release, or G10.