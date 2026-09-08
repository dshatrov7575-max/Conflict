# ADR 0014 — Bounded Professional Player G7

Status: implementation decision under Issue #25, V2 and RC1–RC8.
Base: accepted FD08 68b14882a06b2e90710ebd06e584dc5300fdfe7e,
tree 5969ee705ae935bf305a1b2531bc3bc77ade03cb. Its accepted F1 ancestor is
d2f5a881e10dbb688371e8c5add6bf9375404738.

## Decision

Use a separate production_player presentation application and a separate
Foundation Player HTTP boundary. Product composes only same-origin Foundation
DTOs. It does not import domain models, execute ORM queries, reconcile projection
rows, grant permissions or own domain persistence.

Player authentication uses pre-issued Django sessions for active, nonstaff,
nonsuperuser HUMAN users. All ten frozen read/create permissions are required.
Studio permissions and prohibited relevant write permissions are rejected.
The existing persisted studio-project:<canonical Project UUID> group, derived
by project_access_group_name, remains the sole object-scope grant and contains
no permissions. Roles, scope and operation authority cannot come from JSON,
query parameters, headers, browser storage or UI controls.

Method/media admission precedes authentication and object scope; scope precedes
protected lifecycle/receipt disclosure. After scope admission, every session
POST undergoes real Django CSRF cookie/header/origin enforcement. A successful
scoped GET or Product shell may issue/refresh the CSRF cookie. This does not
write domain tables and creates no login, credential form or alternate Basic mode.
Foreign, absent, unauthorized and non-published definitions have one bounded
protected 404 response.

## Atomic Workspace operation

The Foundation service locks Project, selected published Definition and exact
Workspace topology in a consistent order. The existing default Workspace must
pin a published Definition in the same Project, with one canonical initial
ProjectPublication receipt and a receipted current Definition. No repair or
default reassignment is permitted.

For an authorized exact operation replay, reconcile the persisted operation
before constructing any new Workspace. Compare current result fields solely
for integrity, invoke the frozen FD08 replay verification, and verify the exact
G7 Help-binding namespace. Return canonical bytes of the persisted immutable
receipt with zero writes.

For a fresh request, one outer transaction creates the non-default Workspace,
invokes accepted FD08 combined projection and creates its exact Help bindings.
Exactly one FOUNDATION_PLAYER_WORKSPACE_CREATE_V1 AuditEvent is the combined
Workspace/projection receipt. Help creates no extra AuditEvent. Failure in any
part rolls back the entire request, including the receipt. Global operation UUID
collisions are classified only as bounded typed conflicts; no foreign receipt
is disclosed. Project locking serializes same-project races while independent
projects retain independent lanes.

The canonical request hash binds contract/version, POST route, exact Project,
strong If-Match and the exact body. Principal is derived and checked separately.
Fresh 201 and exact replay 200 contain the same persisted receipt bytes,
independent of PostgreSQL JSONB key order. No replay flag or dynamic decoration
is added. Body ETag and Content-Length derive from those exact bytes.

## Read evidence and immutable TimeSlice

Workspace status is derived from verify_workspace_assessment_projection, never
from the stored status alone. COMPLETE exposes the exact projection SHA.
NOT_PROVEN and INTEGRITY_CONFLICT expose null SHA and cannot enable analysis.
A drifted Workspace is diagnostic only; an unverified manifest is not supplied
as a usable analysis Definition. No GET, import, startup or package operation
silently projects the historical default Workspace.

TimeSlice creation locks the exact Workspace and requires COMPLETE through
require_complete_workspace_assessment_projection before constructing a validated
instance. No bulk/raw insertion, persisted update/delete or metadata-hiding
path exists. One FOUNDATION_PLAYER_TIME_SLICE_CREATE_V1 AuditEvent binds the
immutable created slice and request. Dates are calendar dates, not timestamps.
Replay compares integrity but returns persisted receipt bytes, never mutable
row-derived replacement response content.

## Version-exact Help lifecycle

The checksum-bound Russian catalog is defined in player_help_catalog.py.
The explicit provision_player_help command creates exact immutable PLAYER
HelpTopic rows and binds all existing Workspaces. It fails closed on partial
or conflicting content. Workspace creation binds the same catalog in its outer
transaction; reads and replay never provision or repair it.

The only Help route is workspace-scoped:
/api/foundation/player/workspaces/<workspace_id>/help/<ui_key>/?locale=ru&version=1.0.0.
It uses the accepted resolver, sanitization and content checksum. G7 binding
exactness applies only to the fixed locale/catalog version namespace; valid
later immutable versions may coexist and cannot mutate version 1.0.0 in place.
Pre-workspace onboarding uses local immutable prose, not a fictitious global
PLAYER Help binding.

## Delivery boundary

The professional three-panel shell provides exact published structure,
Workspace and TimeSlice create/open, assessment-only experiment metadata and
versioned Help. Toolbar command identities, local SVG icons, keyboard focus,
bounded splitters and presentation-only localStorage are fixed by the UI
contract. Document, Chat and experiment creation stay disabled and network-silent.
No values, calculation, graph, ranking, modeling, XLSX, evidence UI or G8 is added.

The exact source delta is 29 paths: 6 modified and 23 new. Models, enums,
migrations, FD08 projection/packages and Studio source remain frozen. Source
ADR/runtime documents are verified in the repository, not installed in the
wheel (RC8). Wheel discovery adds only production_player and its in-package
runtime assets; no alternate docs packaging mechanism is introduced.

The claim is PLAYER_PRODUCT_SLICE_DELIVERED, not OWNER_PLAYER_PACKAGE_READY or
COMPLETE_SUITE_ALPHA. Third-profile/Windows-launcher/owner packaging belongs to
G10. Independent MAIN acceptance requires real exact-head attempt-1 push and
Draft-PR CI, the frozen 12+2+10+2 registry, full inherited regressions, wheel
isolation and preserved first-failure evidence. No merge or release is authorized.
