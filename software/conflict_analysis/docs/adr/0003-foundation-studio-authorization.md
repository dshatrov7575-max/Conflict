# ADR 0003: Foundation Studio authorization boundary

Status: accepted by `FOUNDATION-STUDIO-CONTRACT-ADDENDUM-001`.

The server derives a `StudioPrincipal` from authenticated Django permissions;
request bodies and headers never select a role or actor. The canonical service
capability matrix is:

- `STUDIO_EDITOR`: read and create/open/clone/save DRAFT definitions;
- `STUDIO_PUBLISHER`: read, validate, and publish definitions;
- `VIEWER`: read only;
- `PLAYER`: no Studio mutation capability;
- `SERVICE`: no implicit authority. A service must declare an attributable
  actor, bounded purpose, and explicit capabilities. Foundation 2.1 import also
  requires the dedicated `FOUNDATION_IMPORT` capability; a controlled
  structural installer separately requires `STRUCTURE_MUTATE`.

Every DRAFT/lifecycle service enforces its capability independently of the UI.
The HTTP boundary uses session authentication plus Django permissions and
derives `actor_identifier` from the authenticated user. UI hiding is not an
authorization control.

This ADR does not authorize assessment editing, Player implementation, formula
evaluation, scalar Power, prediction, risk scoring, or recommendations.
