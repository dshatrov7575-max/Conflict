# C2A R2 path 10 — lifecycle portable test executor oracle

Authority: Issue #68 active C2A R2 correction. This document is recovery/control-plane only and MUST NOT enter the final R2 12-path commit.

## Frozen executable evidence

Diagnostic run `34706180227`, job `103586525631`, materialized exact combined nine-path tree `5fa4d96d3577fe585507309bec4a5a34b8160904` using lifecycle JS blob `f9ee82c148e1659c122024dd43a2f876348e6073`.

Proven PASS before portable execution:
- immutable R1 checkout `22f0f173a941de88d6920b6e19821168e9b30cc8`;
- exact nine-path tree identity `5fa4d96d3577fe585507309bec4a5a34b8160904`;
- Node `v24.20.0`;
- `node --check software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js` PASS;
- exact portable collection `PORTABLE_NODE_COUNT=13`.

Unchanged R1 portable test file then produced `11 passed, 2 failed in 50.89s`. Both observed failures are stale R1 assertions directly superseded by final R2 authority; independent readback also found one latent stale assertion masked by the old recovery-function anchor.

## Exact path 10 scope

Modify only:
`software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py`

Do not alter product JS, template, browser harness, verifier, counts, timeouts, retry policy, or unrelated assertions in this step.

### Required repair A — retained recovery ticket

R1 currently asserts `retainTicket("download")` in `test_publication_requires_human_retained_recovery_ticket_and_busy_unload_is_guarded`.

Final R2 authority requires the opposite: `link.click()` / download initiation alone MUST NOT prove retention and MUST NOT unlock POST. The updated test must positively enforce BOTH permitted retention paths:
1. exact-copy acknowledgement; and
2. byte-exact re-import of the saved ticket file.

Required static proof in the existing node:
- `retainTicket` accepts only `exact-copy` and `byte-exact-file`;
- `downloadTicket()` does not call `retainTicket` and leaves the send gate locked;
- `ticket-file-proof` and `acknowledge-ticket-file` are bound;
- file size must exactly equal ticket byte length and every byte must compare equal before `retainTicket("byte-exact-file")`;
- exact-copy mismatch leaves POST locked;
- preserve the existing send-boundary guard `!memory.ticketRetained` before publication POST.

### Required repair B — process-loss publication recovery

R1 source slicing assumes the exact old declaration `async function recoverPublication()`.

The authorized candidate uses `async function recoverPublication(override = null)` so an imported publication ticket can supply a recovery-only identity after tab/process loss. Update the static source anchor accordingly without weakening the GET-only proof.

The same existing portable node must positively enforce that publication-ticket process-loss import:
- uses `FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1` version `1.0.0`;
- exact publication ticket key set is only: `contract`, `contract_version`, `project_id`, `definition_id`, `operation_id`, `operation_kind`, `expected_manifest_hash`, `request_body_sha256`;
- exact-key validation rejects extras, so no route/method/If-Match/body/body bytes/content type/CSRF/header material can enter the publication recovery ticket;
- imported publication ticket creates `recoveryOnly: true`, does not assign/reconstruct a sealed POST attempt, and reaches only exact FD06 operation GET `/api/foundation/projects/{project_id}/publication-operations/{operation_id}/`;
- `recoverPublication` contains GET and no publication POST reconstruction/replay;
- validation recovery remains the separate `FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` full semantic request and explicit same-request FD05 replay only;
- cross-kind misuse remains fail closed.

### Required repair C — latent 404 wording drift

After repair B, the old node would next reach an obsolete exact source-string assertion: `404 означает только отсутствие видимого результата`.

Final R2 candidate intentionally uses bounded/non-fingerprinting recovery semantics: code `FOUNDATION_OBJECT_NOT_VISIBLE` and user text `404 не раскрывает существование operation; исход остаётся неизвестным.`

Update the existing assertion to prove the semantic invariant, not a broad substring: 404 must not disclose operation existence, outcome stays unresolved, and the recovery path remains GET-only with zero publication POST reconstruction.

## Masked-assertion readback completed

MAIN independently read every assertion after the two observed failure points against the exact durable JS candidate `f9ee82c148e1659c122024dd43a2f876348e6073`.

For `test_publication_requires_human_retained_recovery_ticket_and_busy_unload_is_guarded`, every post-failure R1 invariant other than the obsolete download-positive assertion remains present in the candidate: exact-copy retention, byte-exact file seam, exact ticket-copy comparison, `buildTicket(attemptCore)` before freezing the sealed attempt, reset of `memory.ticketRetained = false`, the `!memory.ticketRetained` send gate before `fetch(attempt.route, { method: "POST" ... })`, and the dirty/busy/sealed/unresolved beforeunload guard.

For `test_publication_unknown_outcome_disables_post_and_uses_only_operation_recovery_get`, after changing the declaration anchor to `recoverPublication(override = null)`, the remaining receipt/cache/Vary assertions still bind to candidate source; the only additional stale exact string is repair C above. Therefore no fourth masked stale R1 source-string assertion is currently identified in those two failing nodes.

This does not substitute for executable `13/13`; it narrows the next executor cycle and forbids broad unrelated test edits.

## Existing-node strengthening, no cardinality growth

Keep exactly 13 methods in `ProductionStudioLifecyclePublicationTests`. In the existing recovery-ticket node, preserve the full HUMAN ticket exact-key oracle and additionally assert the exact publication-ticket key set above plus forbidden transport fields. Do not create a 14th node.

## Non-negotiable constraints

- Keep the portable registry at exactly **13 tests**; modify semantics of existing nodes rather than adding/removing nodes.
- Do not weaken assertions merely to get green.
- No retry, timeout increase, skip, xfail, or broad substring deletion.
- Preserve all unrelated R1 assertions byte-for-byte where practical.
- Work only in an isolated carrier/recovery lane. Do not update PR #94 or target branch.
- Return: candidate test blob SHA, exact one-path `M` delta for this step, and a coupled executable run using the accepted nine-path tree + candidate test file.
- Coupled acceptance requires Node 24 `node --check` PASS, `PORTABLE_NODE_COUNT=13`, and `13 passed`.
