# ADR 0019 — Project geography R1

Base: c6c7118080ab1a1dcb86216f4092dabcf8125be7; tree
5a4a40431e72fb6b942b895225ce11bba2898052. Owner authorized a new branch
and exactly two ordinary commits. This supersedes the review packs' former
READ_ONLY marker; it does not mark external MVP6 clean-PC smoke as passed.

## Scope and authority

One selected Project has one approximate location; no global conflict map,
reverse geocoder, location polygons, relocation timeline, total score or
regional aggregation. Both method states remain METHOD_NOT_APPROVED.
POS/SAL, Analysis V1, G8 permissions, Studio/Player and package builders retain
their exact base bytes. MVP6 is frozen and is not repackaged by this increment.

GeographicArea and ProjectLocationRevision are immutable, including timestamps.
All instance, queryset, bulk and raw UPDATE/DELETE attempts fail. Revisions
form one chain (one root per project, one successor per predecessor).
ProjectLocationHead is a one-to-one pointer, only writable using the geography
service authority. SQL triggers additionally enforce project identity and
forward-only head movement. A PostgreSQL Project row lock serializes writers;
SQLite's writer serialization can return a bounded ETAG_CONFLICT to the loser.
The receipt and head are committed together or neither is committed.

The revision **is the append-only operation receipt**: operation UUID,
canonical request digest, actor, source, rationale, timestamp and supersedes.
An AuditEvent is intentionally not fabricated in a workspace: the existing
AuditEvent contract accepts only workspace/definition scope, while geography
belongs to Project and also works before a workspace exists. Existing audit
scopes, enum semantics and assessment provenance remain unchanged.

## API

GET location, GET bounded newest-first location-history, POST
location-revisions under `/api/foundation/geography/v1/projects/{uuid}/`.
All reads require the existing zero-permission project membership and
analysis-reader capability. Writes additionally require zero-permission
analysis-location-editor. A capability group containing Django permissions
does not authorize geography. Staff/superuser and spoofed service credentials
cannot bypass admission. The shell never imports or queries domain ORM.

Admission precedes meaningful identifier/body parsing; inaccessible and
nonexistent Project responses are identical. The POST transport enforces
session CSRF after admission, strict duplicate-free JSON (16 KiB maximum),
exact schema, finite coordinates with at most seven decimal places, latitude
[-90,90], longitude [-180,180], integer radius [0,20000000], required positive
radius for all non-POINT kinds, source/actor/rationale and pinned territory.
Unknown fields never become model attributes. There are no PATCH/DELETE APIs.

If-Match is the exact canonical head hash; the empty head has its own hash.
X-Operation-ID is globally unique. Exact same-actor/project/body replays return
the original receipt bytes even when the original If-Match is now stale.
Other operation reuse conflicts. This explicit replay exception is necessary
to recover a successful POST whose HTTP response was lost. Content-Length is
the encoded byte count; response JSON is canonical, hashed and no-store.

## Territory installation

`install_pinned_geographic_areas()` is an explicit idempotent deployment step;
GETs never seed rows. R1 admits two canonical identities: KAZ and geoBoundaries
Mangystau shapeID 16772668B64618180863447. Their common composite dataset/version
permits a same-version parent relation even though the underlying sources
differ. Geometry is entirely static. A new dataset requires new identities.

## Map data and licenses

LOCAL_GEOJSON, MapLibre GL JS 5.6.2 CSP build and same-origin worker. No blob
worker, CDN, tiles, PMTiles, OSM basemap, Yandex or runtime external request.
Natural Earth release 5.1.2 is pinned to Git f1890d9f152c896d250a77557a5751a93d494776.
Raw source metadata revealed geoBoundaries Kazakhstan ADM1 is **2017**, from
OSM/Wambacher under ODbL 1.0, with geoBoundaries product attribution CC BY 4.0.
The owner explicitly approved retaining this source with correct licensing
and date on 2026-09-16. OSM_DERIVED_ADM1_USED=true; OSM_BASEMAP_USED=false.

The openly distributed derived ADM1 GeoJSON, ODbL and CC BY snapshots, full
source citation, raw SHA lock, deterministic build script, asset hashes and
boundary policy ship in the wheel. All raw downloads occur during data build.
Russian labels use stable source feature IDs and local system fonts; no glyph
server. Boundary claims use distinct dashed lines. The UI discloses the
historical scope and policy, and provides the derived ADM1 download.

## UI and accessibility

The isolated Map navigation panel loads Foundation current/history DTOs.
An editor dialog supports map click, marker drag and numeric input in both
directions, uncertainty radius, provenance and before/after preview. Save adds
a revision; clear removes only the unsaved selection, never history. Error and
empty states are explicit; readers do not see write controls. Native dialog,
labelled inputs, Escape, focus return and numeric keyboard alternative support
keyboard use. Locations are identified by text/marker plus a radius outline,
not color alone. Layout preferences are user/project-scoped and never change
source data or Player preferences. Epoch/AbortController rejects stale reads.

## Migration and rollback

Only additive migration 0019 follows exact latest 0018. No old migration is
edited. Both databases install immutable-history and cross-identity triggers.
Forward migration and drift run on PostgreSQL 18 and SQLite. On an empty
geography installation, reverse migration removes the new schema. On a
populated installation reverse fails closed; roll back application code while
retaining schema/history or restore an explicitly selected pre-upgrade backup.
Never delete accepted revisions to permit rollback. Database administrators
remain trusted; SQL ownership is not an application role boundary.

## Verification and remaining limits

The supplied 40-oracle file is preserved byte-for-byte. Service/HTTP tests,
dedicated two-connection races on both databases, deterministic cross-backend
HTTP byte fixtures, exact wheel inventory, real Chromium at 1024×768 and
1366×768, same-origin worker/network capture and inherited Product/Analysis
gates provide the evidence. Test/browser JSON and JUnit artifacts are uploaded
by `geography-r1`. Source acceptance does not perform the separate Windows
installer/clean-PC packaging increment.

Known limits: ADM1 is historical (16 units in 2017); independent country and
province sources can differ; 0.01-degree simplified geometry is cartographic,
not a survey. Coordinates express an approximate center and the entered radius,
not a proven conflict footprint. No source network refresh occurs at runtime.
