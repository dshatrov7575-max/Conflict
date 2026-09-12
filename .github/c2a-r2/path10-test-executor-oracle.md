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

Unchanged R1 portable test file then produced `11 passed, 2 failed in 50.89s`. Both failures are stale test assertions directly superseded by final R2 authority; no other portable node failed.

## Exact path 10 scope

Modify only:
`software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py`

Do not alter product JS, template, browser harness, verifier, counts, timeouts, retry policy, or unrelated assertions in this step.

### Required repair A — retained recovery ticket

R1 currently asserts `retainTicket("download")` in `test_publication_requires_human_retained_recovery_ticket_and_busy_unload_is_guarded`.

Final R2 authority requires the opposite: `link.click()` / download initiation alone MUST NOT prove retention and MUST NOT unlock POST. The updated test must positively enforce BOTH permitted retention paths:
1. exact-copy acknowledgement; and
2. byte-exact re-import of the saved ticket file.

It must fail if download initiation alone sets `memory.ticketRetained = true` or calls `retainTicket("download")`.

Preserve the existing gate that POST remains blocked while `!memory.ticketRetained`.

### Required repair B — process-loss publication recovery

R1 source slicing assumes the exact old declaration `async function recoverPublication()`.

The authorized candidate uses `async function recoverPublication(override = null)` so an imported publication ticket can supply a recovery-only identity after tab/process loss. Update the static source anchor accordingly (robustly to the function declaration or exact new signature) without weakening the GET-only proof.

The same existing portable node must positively enforce that publication-ticket process-loss import:
- uses `FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1`;
- restores only recovery identity;
- reaches exact FD06 operation GET `/api/foundation/projects/{project_id}/publication-operations/{operation_id}/`;
- does NOT reconstruct or issue publication POST;
- preserves zero publication POST replay.

## Non-negotiable constraints

- Keep the portable registry at exactly **13 tests**; modify semantics of existing nodes rather than adding/removing nodes.
- Do not weaken assertions merely to get green.
- No retry, timeout increase, skip, xfail, or broad substring deletion.
- Preserve all unrelated R1 assertions byte-for-byte where practical.
- Work only in an isolated carrier/recovery lane. Do not update PR #94 or target branch.
- Return: candidate test blob SHA, exact one-path `M` delta for this step, and a coupled executable run using the accepted nine-path tree + candidate test file.
- Coupled acceptance requires `node --check` PASS, `PORTABLE_NODE_COUNT=13`, and `13 passed`.
