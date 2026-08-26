# ADR 0004: Atomic first-publication bootstrap

Status: accepted by `FOUNDATION-STUDIO-CONTRACT-ADDENDUM-001`.

`bootstrap_initial_project_definition()` is the sole typed first-publication
orchestrator. In one database transaction it locks the Project and DRAFT,
computes typed manifest validation, appends a DEFINITION-scoped validation
audit, performs the only `VALIDATED -> PUBLISHED` transition, creates and pins
the initial workspace to the exact manifest hash, materializes exact workspace
HelpTopic bindings, creates exactly one `ProjectPublication` carrying
`initial_workspace`, and appends definition/workspace audits.

No pre-published fake workspace, borrowed workspace, caller-provided
`valid:true`, direct status update, or second publication receipt is permitted.
An exception at any stage rolls back validation state, publication state,
workspace, HelpTopic bindings, publication receipt, and success audits together.

Audit scopes are exclusive:

- `DEFINITION`: `definition_version` is set; workspace, assessment set, and
  parameter value are null;
- `WORKSPACE`: workspace is set and `definition_version` is null.

Existing untyped historical manifests retain their previous workspace-audited
lifecycle and checksum behavior. They are never silently reclassified as the
typed contract.
