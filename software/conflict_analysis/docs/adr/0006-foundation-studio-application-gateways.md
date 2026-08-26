# ADR 0006: Foundation Studio application gateways

- Status: accepted for the bounded Foundation dependency
- Task: `FOUNDATION-STUDIO-APPLICATION-GATEWAYS-001`
- Base: `b8a543c09cc89b1b7378f21215f70afa586b248d`
- Scope: HTTP/application composition only; no model, enum, schema or migration

## Decision

The canonical `/api/foundation/` boundary exposes the accepted typed-definition
services without adding a Studio persistence or lifecycle authority. Authenticated
Django users are converted to HUMAN `StudioPrincipal` values. Existing project
groups named `studio-project:<Project UUID>` are the only object-scope grants.
Inaccessible objects are resolved as 404 before capability disclosure.

The exact added operations are:

| Method and path | Django route name | Authority |
| --- | --- | --- |
| `POST definitions/<definition_id>/publish-successor/` | `foundation-definition-publish-successor` | canonical ordinary publication, no workspace |
| `GET definitions/<definition_id>/` | existing `foundation-definition-open` | typed DRAFT, VALIDATED, PUBLISHED or RETIRED read |
| `POST projects/<project_id>/definition-packages/2.1/preview/` | `foundation-definition-package-21-preview` | non-mutating server preview |
| `POST projects/<project_id>/definition-packages/2.1/attempt/` | `foundation-definition-package-21-attempt` | durable canonical import attempt |
| `GET definitions/<definition_id>/package/2.1/` | `foundation-definition-package-21-export` | existing package exporter plus HTTP representation |
| `POST projects/bootstrap-first-draft/` | `foundation-project-bootstrap-first-draft` | atomic Project, scope, DRAFT and CREATE audit |

There is no `/api/studio` alias.

## Lifecycle and conflict contract

Lifecycle reads refetch and validate the exact persisted typed manifest and hash.
PUBLISHED and RETIRED DTOs are read-only. The DRAFT-only opener remains available
to internal callers whose precondition is specifically DRAFT.

Successor publication accepts only `{}` or one bounded `locale`; it delegates to
the canonical ordinary publication service with `workspace_spec=None`. It creates
no workspace and never repins an existing workspace. A retry or changed-current
race is classified from persisted identities by
`FoundationStudioApplicationConflict`, never exception prose, and returns stable
409 `SUCCESSOR_PUBLICATION_CONFLICT`.

First-project bootstrap accepts exactly:

```text
{
  project: {id, code, version, name, description, metadata},
  definition: {id, code, version, manifest, semantic_version, construct_version}
}
```

One transaction creates the Project, the derived scope group, creator membership,
the canonical first DRAFT and one trusted HUMAN definition CREATE audit. Project
UUID/code, group-name and first-definition UUID collisions have explicit 409 codes.
Any failure rolls back every row and membership.

## Package ingress and authorization

Preview and attempt admit and capture at most one immutable HTTP byte stream. A
successfully admitted body is consumed once, preserves exact `HTTP_BYTES`, full
SHA-256 and actual byte length, and is parsed without a second body read or JSON
reserialization. The transport budget limits bytes consumed from the request,
not merely bytes retained in memory: a known numeric `Content-Length` over the
limit is rejected before any read, and an absent, untrusted or mismatched length
can consume at most `max_bytes + 1` before rejection. Invalid media type, charset
or Content-Length is rejected at HTTP admission without a durable receipt.
Over-budget HTTP bodies likewise have no receipt and no claimed full-body raw
identity because their remainder is intentionally never consumed. Admitted
malformed or schema-invalid attempts still reach the canonical durable REJECTED
receipt path. The same limit applies when Django already exposes a private
preloaded `_body`: its size is checked before hashing or copying, and an
oversized preloaded body never becomes an exact `HTTP_BYTES` identity.

Before package work, the adapter requires all of:

1. authenticated HUMAN user;
2. exact project object scope;
3. Django `domain.add_importrun` entry permission;
4. HUMAN `DEFINITION_READ`.

Attempt performs the same non-mutating server preview and then checks the HUMAN
capability for the server-selected action:

| Intended action | Additional HUMAN check | Sealed SERVICE capability set |
| --- | --- | --- |
| malformed/unparseable | none beyond entry/read | `FOUNDATION_IMPORT` |
| `CREATE_DRAFT` | `DRAFT_CREATE` | `FOUNDATION_IMPORT`, `DRAFT_CREATE` |
| `BOOTSTRAP_PUBLISHED` | `DEFINITION_VALIDATE`, `DEFINITION_PUBLISH` | import, create, validate, publish |
| `REUSE_EXACT` | none beyond read | `FOUNDATION_IMPORT` |

Unknown actions fail closed. Only after HUMAN checks does the server construct a
sealed SERVICE principal. Public body, query and headers cannot select its actor,
role, capabilities, purpose or stale token.

Preview accepts no query. Attempt accepts the exact single-valued query set
`locale`, `initial_workspace_id`, `initial_workspace_code`,
`initial_workspace_version`, `initial_workspace_name` and
`initial_workspace_is_default` only when its own preview returns
`BOOTSTRAP_PUBLISHED`; otherwise every workspace query is rejected. Boolean text
is exactly `true` or `false`, and workspace metadata is server-fixed `{}`.

Preview returns the immutable action plus raw and semantic identities without a
write. Every admitted attempt returns HTTP 200 with REJECTED, FAILED or COMMITTED,
its canonical result and a projection of the single durable `ImportRun`. Auth,
scope and HTTP-admission failures create no receipt.

## Exact export representation

The HTTP adapter calls only
`export_project_definition_package_2_1(definition)`. It constructs:

```text
response_bytes = (canonical_json(package) + "\n").encode("utf-8")
representation_sha256 = sha256(response_bytes)
ETag = quoted representation_sha256
semantic_payload_sha256 = package.manifest.payload_sha256
```

The response is the exact byte sequence with terminal newline, not a DRF JSON
render. The representation validator and semantic payload checksum remain distinct
and are tested independently by exact byte-for-byte reimport.

## Security and verification

Basic authentication precedes session authentication. Anonymous requests are 401;
in-scope users missing an exact permission are 403; missing or inaccessible objects
are 404. Unsafe session requests require real CSRF. Explicit body/query/header
spoof vectors include actor, role, capability, service context/purpose, project
authority and stale-token authority.

For an authenticated unsafe session request, the adapter runs Django's real
cookie/header check against the underlying `HttpRequest` before transport
admission. Django does not treat `application/json` as a form body, so this avoids
DRF form parsing and preserves zero-byte 403 denial for a missing or invalid CSRF
token. Only after CSRF succeeds may the view invoke the canonical bounded HTTP
transport gate and capture; Basic authentication reaches that same single gate.
Malformed media/charset and known oversize lengths are rejected before body I/O.

Acceptance preserves all accepted FSA tests and adds SQLite and PostgreSQL 18
route, lifecycle, conflict, raw-byte, receipt, rollback and concurrency gates.
`makemigrations --check --dry-run` must report no changes.
