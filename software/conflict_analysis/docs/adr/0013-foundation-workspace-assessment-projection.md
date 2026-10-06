# ADR 0013: Foundation workspace assessment projection

- Status: accepted for `CA-SUITE-I1-FOUNDATION-FD08-ASSESSMENT-PROJECTION-001`
- Scope: deterministic Foundation-owned assessment projection and Foundation package 2.2 reconciliation only

## Context

A published typed `ProjectDefinitionVersion` is the source of the actor,
analytical-element, actor-role, and parameter-definition structure used by a
workspace.  The historical workspace graph does not itself prove which source
manifest identities produced its rows.  Project-wide parameter codes are also
not enough to distinguish successor definitions that reuse a code.

The Foundation boundary must therefore materialize a definition-bound,
workspace-specific projection without creating a second numeric lane, silently
using a default workspace, or turning a package import into a database restore.

## Decision

### Canonical projection

`ParameterValue` remains the sole numeric-value authority.  FD08 creates no
second value table, manifest-value authority, calculation, scalar Power,
formula, prediction, recommendation, ranking, risk result, evidence object, or
country-data import.

The canonical target set adds `ACTOR`, `ANALYTICAL_ELEMENT`, and
`ACTOR_ELEMENT_ROLE` without deleting or reinterpreting legacy target types.
Canonical `ParameterDefinition` rows bind all-or-none to one exact published
definition and one source-manifest parameter UUID.  Their identity is the
definition UUID plus that source UUID; their code alone is never authoritative.
The immutable snapshot contains the name, description, target type, value type,
scale minimum, maximum, and step, scale metadata, allowed statuses,
applicability, reference statement, source-manifest parameter identity, and
snapshot SHA-256.

Projected Actor, AnalyticalElement, and ActorElementRole rows retain their
source-manifest UUID and SHA-256.  Roles also retain their exact source order.
Actor and element parent links, and role actor/element links, are expressed by
the corresponding source-manifest identities.  Applicability stores source
manifest UUIDs, never projected workspace UUIDs, labels, or workbook positions.
An empty applicability family means no target in that family is applicable; it
does not mean unrestricted applicability.

All canonical projected row UUIDs are deterministic within one Workspace.  Two
workspaces pinned to the same definition have distinct projected UUIDs and the
same source mapping.  The canonical service is the only creation authority.  It
locks and revalidates Project, exact published definition, Workspace definition
and manifest-hash pin, and current projection state before it atomically creates
the complete actor hierarchy, element hierarchy, role links/order, and parameter
snapshots.

Canonical rows are append-only and protected from instance, queryset, bulk,
raw, delete, and cascade-based drift.  A replay recomputes expected rows and
hashes.  Partial, extra, orphaned, wrong-parent, wrong-order, wrong-hash,
changed-snapshot, or wrong-workspace state is an integrity conflict and is never
silently repaired.

Canonical `ParameterValue` admission proves the exact Project, Workspace,
definition snapshot, target, and applicability.  New canonical targets do not
enter a legacy-mutable save path.  Existing legacy rows retain their identity and
backward-compatible behavior without fabricated canonical provenance.

FD08 does not project an existing default or historical Studio workspace during
migration, GET, startup, export, import, package launch, or any fallback.  It
adds no HTTP route, does not create a Workspace, and grants Product no ORM or
projection authority.  `assessment_projection_status` is exactly `COMPLETE`,
`NOT_PROVEN`, or `INTEGRITY_CONFLICT`; its SHA-256 exists only for `COMPLETE`.
TimeSlice creation is permitted only after persisted receipt plus exact
row/manifest integrity proves `COMPLETE`.

### Migration and receipt

Migration `0018_workspace_assessment_projection` is additive and depends on
`0017_multilingual_evidence_lineage`.  It introduces nullable fields first,
performs only deterministic legacy-safe structural backfill, and then introduces
conditional constraints.  It preserves every legacy ParameterDefinition,
ParameterValue, target identity, primary key, foreign key, code, status, and
numeric byte.  Legacy actor, element, and role provenance remains absent; a
legacy role receives deterministic zero order.  The migration creates no
projection row, canonical snapshot, Workspace, AuditEvent, or numeric recoding.

Standalone projection writes one immutable HUMAN-attributed WORKSPACE-scope
`AuditEvent`; there is no new receipt table.  Its immutable identity binds the
exact Project, Workspace, definition ID and manifest hash, operation UUID,
request hash, source-mapping hash, snapshot hash, and projection hash.  The same
key and immutable request returns the exact persisted result; key reuse with a
different identity or bytes is a typed conflict.  A failed operation commits
neither projected rows nor a success receipt.  An unknown outcome uses exact
operation recovery, never a blind retry.

Future G7 workspace creation composes the projection inside its caller-owned
`FOUNDATION_PLAYER_WORKSPACE_CREATE_V1` operation and emits no second audit
event.

### Foundation package 2.2

Foundation 2.2 is a new, dedicated
`WORKSPACE_ASSESSMENT_PROJECTION` envelope.  Foundation 2.0 and 2.1 schemas,
bytes, validators, and behavior remain frozen.  The existing
`domain.services` `schemas/*.json` package-data glob packages the new schema;
no packaging configuration change is required.  `xlsx_adapter` remains
transport-only and unchanged.

The 2.2 package exports the exact selected Workspace pin, definition manifest
identity and payload, immutable projection receipt, projection/mapping/snapshot
hashes, projected source-manifest identities and hashes/order, and the complete
definition-bound ParameterDefinition snapshots.  It selects only snapshots for
`Workspace.definition_version`.  Thus predecessor and successor definitions that
share a parameter code remain deterministic and unambiguous.

2.2 import is exact existing-projection reconciliation, not projection creation
or repair.  It revalidates Project, Workspace, definition ID, manifest hash,
projection receipt, and projection SHA-256 before semantic use.  It then
exact-matches and reuses the same already-existing `COMPLETE` projection with
the original receipt.  An empty database, another Workspace, a missing or
changed receipt, or a partial, extra, missing, or drifted projected graph returns
a typed refusal with zero semantic writes.

This package is not `FULL_BACKUP` and is not a complete Workspace or database
restore.  It must not silently discard unsupported non-empty data or downgrade
to 2.0 or 2.1.  Such input is explicitly refused or represented as a deliberately
limited export.  Full private backup and restore of the database, stored
originals, UUIDs, foreign keys, hashes, and receipts belongs to G10.  `UNKNOWN`
remains distinct from zero.  PRE_FREEZE POS/SAL resolution is scoped only to the
exact `Workspace.definition_version` snapshot set; project-wide first-row lookup
is forbidden.

## Consequences and verification

The implementation has no hidden default-workspace projection path and no
package-based repair or restore path.  Upgrade, clean upgrade, and
legacy/empty reverse-reapply checks remain deterministic; semantic reversal is
not claimed after canonical projection data exists.
`makemigrations --check --dry-run` must report no drift.

Verification strengthens only the frozen FD08 registry: twelve portable nodes
and two PostgreSQL-only concurrency nodes.  It proves deterministic projection,
definition and workspace separation, immutable snapshots, exact ParameterValue
target admission, legacy preservation, failure rollback, replay, and typed
reconciliation refusal.  Any need to change Foundation 2.0/2.1 or add another
package path is outside this decision and stops the work.
