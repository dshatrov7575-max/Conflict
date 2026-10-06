# ADR 0004: Bounded Studio authorization

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
The canonical HTTP boundary is `domain.api.studio_definitions` under
`/api/foundation/`. It uses Basic authentication first for an exact anonymous
401 response and Session authentication with CSRF enforcement, plus Django
permissions for capabilities. Object scope is an explicit server-side Django
group named `studio-project:<project UUID>`; a globally permitted user without
that project grant receives 404, not object disclosure. A superuser remains an
explicit administrative override. The adapter derives `actor_identifier` from
the authenticated user. JSON, query and custom-header role/capability/actor or
stale-token claims are rejected, and public HTTP can never construct a SERVICE
principal. UI hiding is not an authorization control.

The accepted routes are exactly:

```text
POST /api/foundation/projects/<project_id>/definitions/
GET  /api/foundation/definitions/<definition_id>/
POST /api/foundation/definitions/<definition_id>/clone/
PUT  /api/foundation/definitions/<definition_id>/draft/
POST /api/foundation/definitions/<definition_id>/validate/
POST /api/foundation/definitions/<definition_id>/publish-initial/
GET  /api/foundation/help/<ui_key>/?application=STUDIO&locale=<locale>&version=<version>
```

There are no parallel `/api/studio/...` mutation aliases.

This ADR does not authorize assessment editing, Player implementation, formula
evaluation, scalar Power, prediction, risk scoring, or recommendations.
