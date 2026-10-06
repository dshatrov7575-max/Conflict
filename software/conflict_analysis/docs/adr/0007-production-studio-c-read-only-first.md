# ADR 0007: Production Studio C starts with authenticated read-only

- Status: accepted for `CA-SUITE-I1-PRODUCTION-STUDIO-C0-001`
- Base: `5f73ebf2fd29a161a34ea047c7eead4fb0c582d4`
- Base tree: `ea5ff9ab510cb76f0c2b1bfda1c02c1278812aae`
- Scope: bounded C0 composition and presentation only

## Decision

Production Studio C begins with `C0_AUTHENTICATED_READ_ONLY`. The Django
composition root registers the model-free `production_studio` application at
`/studio/`; Foundation remains the only definition, package, Help,
authorization and persistence authority. Studio views never import Foundation
models, services or policy and never query the ORM.

The application surface is exactly:

| Method and path | Purpose |
| --- | --- |
| `GET /studio/` | pre-authenticated exact-UUID entry shell |
| `GET /studio/definitions/<definition_id>/` | Russian three-panel read-only shell |
| `GET /studio/claim-boundaries/read-only/v1/` | exact committed claim contract bytes |

None of those server views issues or rotates a session or sets a CSRF token.
Anonymous entry and definition requests receive the fixed 401 state. The claim
contract GET is public and does not inspect `request.user` or session state.
Authentication is a shell precondition: the host issues a Django session before
the measured C0 flow. There is no Studio login, logout, credential collection or
refresh endpoint.

Once loaded, the browser may call only these Foundation operations:

| Method and path | Use |
| --- | --- |
| `GET /api/foundation/definitions/<definition_id>/` | exact lifecycle DTO and typed manifest |
| `GET /api/foundation/definitions/<definition_id>/package/2.1/` | exact Foundation 2.1 export bytes |
| `GET /api/foundation/help/<ui_key>/?application=STUDIO&locale=<locale>&version=<topic_version>` | exact bound Help tuple, when present |

The Help request is derived only from the manifest's exact binding tuple. Its
stable key and content checksum are verified against the returned topic. A
missing tuple, 404 or identity mismatch is an explicit unavailable state; local
copy is never promoted to authoritative Help. C0 does not call any Foundation
operation with `POST`, `PUT`, `PATCH`, `DELETE` or `HEAD`, and it does not expose
an `/api/studio` mutation alias.

## Truthful read model

The shell opens accessible DRAFT, VALIDATED, PUBLISHED and RETIRED definitions
by exact UUID. It recomputes canonical manifest SHA-256, requires equality with
the DTO `manifest_hash`, and requires the quoted response ETag to identify that
same manifest. Only the literal returned lifecycle status is displayed. C0
does not infer currentness, validity, validation actors or publication facts
that Foundation did not return.

Project information is labelled as a snapshot in this definition. Actors and
analytical elements retain exact manifest identity and order but are rendered
through a bounded active window. No actor-by-element matrix, rank ordering,
total/average row, scalar Power/risk badge or cross-component magnitude heatmap
is allocated or presented.

The Foundation 2.1 download preserves the exact bytes, filename, quoted
representation ETag, semantic payload checksum and terminal newline supplied by
Foundation. Repeating the GET is a read, not a retryable attempt or package
authority in Studio.

## State and claim boundary

The only Studio persistence in the browser is:

```text
localStorage["conflict-analysis-studio:read-only-layout:v1"] =
{
  version: "STUDIO_READ_ONLY_LAYOUT_V1",
  left: 220..420,
  right: 300..500,
  activeRightTab: "document" | "chat" | "help"
}
```

Defaults are `left=272`, `right=360`, `activeRightTab="document"`, and the
serialized UTF-8 form is limited to 256 bytes. Malformed, oversized or
out-of-range state resets to those defaults. Domain, project, definition,
actor, evidence and Help identities are not persisted in localStorage,
sessionStorage, IndexedDB, Cache Storage or a service worker.

A committed Russian JSON claim contract and its adjacent SHA-256 are the
machine-readable boundary. Runtime verification must match those exact bytes
before download. The limitation banner, disabled controls and noscript state
repeat the user-visible boundary: definition status and traceability are not a
claim of substantive correctness or scientific validation. Document evidence
is unavailable until a future separately authorized C3; Chat, formula, scalar
or aggregate Power, prediction, probability, risk, ranking, recommendation,
OCR and LLM/RAG are absent or disabled.

## Consequences

Measured C0 navigation, exact definition read, optional exact Help read and
export are GET-only and leave every server row unchanged, including
`django_session`, `auth_user.last_login`, all `domain_*` rows and AuditEvents.
The existing Foundation object-scope contract is not reimplemented: anonymous
is 401, an in-scope principal without capability is 403, and absent and
inaccessible cross-project UUIDs are indistinguishable 404 outcomes.

C0 adds no model, migration, permission, validator, package generator or
evidence authority. C1, C2 and C3 are not started or implicitly authorized by
this decision.
