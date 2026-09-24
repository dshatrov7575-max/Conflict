# ADR 0005: Exact pre-workspace Studio help

Status: accepted for `FOUNDATION-STUDIO-CONTRACT-ADDENDUM-001`

## Context

The existing HelpTopic resolver requires a `ProjectWorkspace`, while Studio
must render welcome, project-creation, validation and publication help before
the first workspace exists. Creating or borrowing a workspace to resolve help
would break the first-publication transaction and the project isolation
boundary. Resolving an unversioned or unsanitized topic would make displayed
guidance dependent on mutable global state.

## Decision

`HelpTopic` remains the sole immutable help-content authority. Its exact
identity is application scope, stable key, locale and version. A topic is
eligible for resolution only when it is published, stored in canonical
allowlist-sanitized form and its SHA-256 checksum matches those exact UTF-8
bytes.

`UIHelpBinding` supports two explicit, disjoint lookup modes:

- a global binding has no workspace and, in this contract version, must have
  application scope `STUDIO`;
- a workspace binding keeps the exact existing workspace boundary.

Both modes bind one application scope, UI key, locale and version to a topic
with the same application scope, locale and version. Conditional unique
constraints and matching indexes protect the two lookup identities.

The resolver requires all four identity inputs. With no workspace it searches
only global Studio bindings. With a workspace it searches only bindings owned
by that exact workspace. It never falls back between modes, applications,
locales or versions, and it rechecks the topic sanitization/checksum invariant
before returning content.

Migration `0014_foundation_studio_contract_backfill` copies each existing
workspace binding's application scope from its exact HelpTopic. It creates no
global binding and changes no topic content, version or checksum.

## Consequences

- Studio can display exact published help before first publication without a
  fake workspace.
- Existing workspace HelpTopic behavior stays available and fail-closed.
- A missing requested locale or version is an explicit resolution error.
- PLAYER and SHARED global help remain outside this addendum; adding either
  requires a later explicit contract change.
- Help storage does not become a Studio presentation model or a second domain
  authority.
