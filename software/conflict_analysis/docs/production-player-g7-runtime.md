# Professional Player G7 — bounded runtime contract

G7 is a tested Player product slice, not an owner-ready Studio+Player package.
G10 owns the separate Player profile and Windows launcher. This document and
ADR 0014 are required source artifacts, not installed-wheel files (RC8).

## Runtime prerequisites

Use Python 3.12 and the repository's pinned dependency ranges. Install the
wheel in an isolated environment and supply ordinary Django/PostgreSQL settings.
Do not import application code from a source checkout to make wheel checks pass.
The wheel must carry production_player Python, templates, CSS, JavaScript,
claim-boundary JSON and its SHA-256 sidecar. No external font/icon/CDN, generated
docs copy, service worker or new packaging mechanism is needed.

Apply the existing Foundation migrations (accepted domain leaf 0018). G7
introduces no migration. Explicitly run:

    python manage.py check
    python manage.py makemigrations --check --dry-run
    python manage.py provision_player_help

Help provisioning is an explicit deployment/test operation, not application
startup. Repetition is an exact no-write replay; conflicting same-version
content fails closed. The command binds historical Workspaces; new Workspaces
receive bindings atomically from their Foundation create operation.

## Authentication and entry

Only pre-issued same-origin Django sessions are supported. Tests create their
own nonstaff/nonsuperuser HUMAN users and exact project grants. No username/
password UI, Basic mode, permanent test profile or owner launcher is delivered.
An authorized user has all of:

- domain.view_project, domain.view_projectdefinitionversion;
- domain.view_projectworkspace, domain.view_timeslice;
- domain.view_experiment, domain.view_expertprofile, domain.view_assessmentset;
- domain.view_helptopic, domain.add_projectworkspace, domain.add_timeslice.

The existing studio-project:<canonical Project UUID> group is the only object
scope; it carries no permissions. Studio mixing, prohibited write permissions,
staff and superusers are rejected by Foundation on every request and replay.
Do not infer authorization from the browser shell or a disabled control.

The GET-only Product entry points are /player/, /player/projects/<project_id>/
and /player/workspaces/<workspace_id>/. Entry selects an explicit Project UUID.
No implicit current/latest/default selection substitutes for an exact identity.
Successful shell/scoped API GETs may set or refresh the CSRF cookie; no domain
write accompanies it. POST sends that token in the standard X-CSRFToken header
and requires the same-origin CSRF check.

## Foundation API

All paths below are relative to /api/foundation/player/.

| Method | Path | Result |
| --- | --- | --- |
| GET | projects/<project_id>/definitions/ | Scoped PUBLISHED versions only |
| GET | definitions/<definition_id>/ | Exact published manifest and identity |
| GET, POST | projects/<project_id>/workspaces/ | List or explicit non-default create |
| GET | workspaces/<workspace_id>/ | Verified Workspace projection status |
| GET, POST | workspaces/<workspace_id>/time-slices/ | List or immutable slice create |
| GET | workspaces/<workspace_id>/experiments/ | ASSESSMENT metadata only |
| GET | workspaces/<workspace_id>/help/<ui_key>/ | Exact workspace-bound Help |

Help requires exactly locale=ru and an explicit semantic version (G7 uses
1.0.0). No nearest/latest/locale fallback exists. The eight frozen UI keys are
player.welcome, player.published_definition, player.workspace, player.time_slice,
player.experiments_locked, player.document_locked, player.chat_locked and
player.method_unavailable.

GET responses are canonical UTF-8 JSON with no-store, nosniff and an ETag equal
to SHA-256 of the exact body bytes. Their response_sha256 binds the canonical
snapshot core excluding response_sha256. It is not a write precondition.
Foreign/absent/unauthorized objects have the same bounded protected 404 shape.

Workspace POST accepts exactly id, code, version, name, definition_id,
definition_manifest_hash, is_default=false and metadata={}. TimeSlice POST
accepts exactly id, code, version, name, cutoff_date, order and metadata={}.
Idempotency-Key is one canonical lowercase RFC 4122 UUIDv4. If-Match is one
strong quoted lowercase SHA-256: the selected published Definition manifest
for Workspace create and the Workspace definition_manifest_hash for slice
create. No alternate Workspace hash is invented.

Fresh 201 and exact replay 200 return identical persisted receipt bytes.
Receipt lookup follows current authorization; changed principal/request/
scope/route cannot disclose prior receipt content. Same-key replay has zero
writes. Identity conflicts and all failures roll back the request. Persisted
result drift is a conflict, not an invitation to repair or decorate the receipt.

The browser seals body bytes, key and If-Match in memory before each POST.
Busy/unresolved operations block submit/context navigation and install a
beforeunload advisory. Unknown outcome permits only explicit reconciliation
of that exact sealed request. There is no automatic retry or replacement key.
Reload/tab loss cannot reconstruct a lost operation identity from current rows;
the UI discloses that limitation.

## Analysis and UI boundaries

COMPLETE means the accepted Foundation verifier proves receipt, manifest,
canonical rows, counts, snapshots and hashes. NOT_PROVEN and INTEGRITY_CONFLICT
have null projection SHA and disable analysis/slice creation. The historical
default Workspace stays unprojected. The Product never trusts stored status
or joins/reconciles canonical projection rows itself.

Persisted slices cannot be renamed/deleted/hidden through metadata. The date is
rendered as its exact calendar string without UTC/local-time conversion.
The tree reads arbitrary manifest cardinality in a bounded DOM, never a fixed
6-by-8 matrix. Experiment tabs are read-only metadata; no values or aggregation.

Only top-surface commands use data-command-id. The exact Workspace and slice
command IDs and Russian accessible labels are fixed in the in-package claim
contract. Two bounded pointer/keyboard splitters and F6/Shift+F6 support the
three panels. Browser Ctrl+R is not intercepted. The only persistent key is
conflict-analysis-player:layout:v1, with bounded version/width/right-tab
presentation state; never IDs, hashes, receipts, CSRF, credentials or content.

Disabled, keyboard-discoverable surfaces are network-silent:
Документ — Доступно после этапа доказательств;
Чат — Доступно после этапа чата;
+ — Доступно после этапа экспериментов.
There is no active calculation strategy or beta-method claim.

## Verification and delivery

Run the frozen Foundation 12 portable + 2 PostgreSQL-only nodes, Product 10
portable nodes and 2 real Chromium/PostgreSQL scenarios. The SQLite Foundation
focused result is exactly 12 passes + 2 named skips; PostgreSQL is 14 passes.
Full Foundation adds those nodes to accepted FD08: 300 passes on PostgreSQL,
277 passes + 23 expected skips on SQLite. Inherited C0/C1 Product counts are
19+8 per engine; G7 adds 10. Inherited Chromium 1 plus G7 2 equals 3.

JavaScript syntax, migration no-drift, verifier negative self-checks, frozen
source anchors, wheel contents and isolated installation are independent gates.
Use the exact Chrome for Testing 152.0.7977.64 for browser evidence.

Real attempt-1 push and PR jobs consume repository FD08_ACCEPTED_HEAD/TREE:
68b14882a06b2e90710ebd06e584dc5300fdfe7e /
5969ee705ae935bf305a1b2531bc3bc77ade03cb.
The PR remains OPEN/DRAFT/UNMERGED, with base
codex/ca-suite-i1-foundation-fd08-assessment-projection and head
codex/ca-suite-i1-player-g7-professional-shell. Evidence must bind the exact
event commit, tree, sole first parent, same run/attempt and artifact checksums.
Skipped/empty/stale jobs and push-only PASS do not prove acceptance.
Preserve the first real failure even after later PASS. Stop at
READY_FOR_MAIN_REVIEW or a concrete BLOCKED_G7_*; do not start G8 or merge/release.
