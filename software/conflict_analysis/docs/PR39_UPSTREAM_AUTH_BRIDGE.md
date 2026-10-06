# PR-39 — fail-closed trusted upstream authentication bridge

## Purpose

Replace the explicit production authentication gap with a bounded, provider-neutral
bridge from a trusted reverse proxy / upstream SSO into Django sessions.

This PR does not implement a particular OAuth/OIDC/SAML provider. It defines and
tests the trust boundary the external identity layer must satisfy.

## Proxy contract

The trusted proxy MUST:

1. terminate/authenticate the upstream user;
2. remove any client-supplied `X-Conflict-Auth-User` and
   `X-Conflict-Auth-Secret` headers;
3. inject exactly one canonical `X-Conflict-Auth-User` header;
4. inject the configured shared `X-Conflict-Auth-Secret`;
5. continue to strip/set `X-Forwarded-Proto` according to the existing HTTPS
   boundary.

The application requires `UPSTREAM_AUTH_SHARED_SECRET`, minimum 32 characters,
and compares it with `hmac.compare_digest`.

## User admission

Upstream identity is not user provisioning.

- unknown usernames are rejected;
- inactive users are rejected;
- no user is auto-created;
- users must be provisioned explicitly in the local authorization database;
- local permissions/project-scope groups remain authoritative after login;
- staff/superuser semantics are not granted by the upstream header.

The custom backend is a `RemoteUserBackend` with
`create_unknown_user = False`.

## Session behavior

A valid trusted-header request establishes the normal Django session. However,
the trusted headers are required on every subsequent production request: if
they disappear, the middleware logs out an existing upstream-authenticated
session. This prevents a stale session cookie from becoming a second,
independent authentication channel.

## Alternative auth paths

Production DRF authentication is explicitly restricted to
`SessionAuthentication`. `BasicAuthentication` is not enabled in production,
so an Authorization: Basic header cannot bypass the upstream SSO boundary.

## Verification

Unit/contract tests prove:

- pre-provisioned active user authenticates;
- unknown user returns 403 and is not created;
- inactive user returns 403;
- missing half of the header pair returns 403;
- wrong shared secret returns 403;
- ambiguous/comma-joined and malformed usernames are rejected;
- a session without fresh trusted headers is logged out;
- production middleware/backend order is exact;
- BasicAuthentication is absent.

Production Compose CI additionally proves:

- valid trusted headers -> 200;
- same session cookie without fresh trusted headers -> 401;
- wrong shared secret -> 403;
- unknown upstream user -> 403 and no user creation.

## Boundaries

This is a host-integration contract, not an identity-provider implementation.
A real deployment still must configure a reverse proxy/SSO product to satisfy
the stripping/injection rules and protect the shared secret.

The proxy, host administrator, application process, migration owner and
PostgreSQL superuser remain trusted authorities within their documented
boundaries.

Scientific validation, HUMAN reliability, historical admission, historical
area UNO and predictive/probability/risk validity are unchanged.
