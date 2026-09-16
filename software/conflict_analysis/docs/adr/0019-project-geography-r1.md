# ADR 0019 — Project geography R1

Base: c6c7118080ab1a1dcb86216f4092dabcf8125be7; tree
5a4a40431e72fb6b942b895225ce11bba2898052. Owner authorized a new branch
and two ordinary commits, followed by one explicitly authorized correction. This supersedes the review packs' former
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

`install_pinned_geographic_areas()` remains an explicit idempotent deployment
operation. Reads never create or repair rows. The current catalog is extracted
from Natural Earth v5.1.2 commit f1890d9f152c896d250a77557a5751a93d494776:
KAZ (Admin 0), and Mangystau NE_ID **1159314605**, ADM1_CODE KAZ-3236,
ISO KZ-MAN. Its source name is Mangghystau, Russian NAME_RU is
Мангистауская область. A test binds the service catalog to the generated asset.
Metadata records Natural Earth, exact commit/tag/theme and Public Domain.

Dataset version **1.0.1** produces new immutable area UUIDs and versioned rows.
Existing 1.0.0 areas/revisions are retained without retagging or deletion; new
writes admit only the new catalog. This is a data/catalog correction, so the
model structure, migration 0019 and API schema are unchanged. Apply the explicit
catalog installer during deployment before editing locations. A new revision
can supersede an older version while preserving its original provenance.

## Natural Earth-only map data and licenses

LOCAL_GEOJSON, MapLibre GL JS 5.6.2 CSP build and same-origin worker. No blob
worker, CDN, public tiles, PMTiles, OSM basemap, Yandex or external runtime request.
All geographic data are exclusively from nvkelso/natural-earth-vector tag v5.1.2,
commit f1890d9f152c896d250a77557a5751a93d494776, tree
ed868934eff4da3bd5579e025bb8ff1212757937, dated 2022-05-13. Countries and Admin 1
use theme 5.1.1, disputed lines 5.1.0, populated places 5.1.2. Natural Earth
terms are retained verbatim; geography is Public Domain. MapLibre retains its
unchanged BSD-3-Clause license. Source run 35139143356 is superseded.

The correction excludes all previous non-Natural-Earth map data and their four
license/metadata files. Old V1 license approval has been explicitly superseded.
No license claim from that superseded map is used by the current catalog or UI.

Five exact raw files (four GeoJSON plus LICENSE.md) are SHA-256 checked before
parsing. Filtering uses the approved nine countries, CRS84 and [35,30,100,61];
Admin 1 requires ADM0_A3=KAZ. Geometry is retained exactly, tolerance=0. The
builder verifies emitted geometries and available NAME_RU against the raw pin.
NE_ID is used for Admin 1 because Natural Earth reuses ISO KZ-ALA for Almaty
region and city. All FCLASS_* disputed attributes are retained. NAME_RU wins
over the versioned label fallback; local DOM labels require no glyph server.

The supplied builder needed real-data corrections (duplicate ISO identity,
NAME_RU priority, strict CRS, classification retention and cross-platform LF).
Its original hashes and integration details are recorded in
maps/BUILDER_PATCHES_RU.md. The supplied verifier is unchanged and validates
actual runtime bytes through a flattened temporary view. The builder receipt
uses canonical JSON with LF; the outer runtime inventory preserves the existing
Foundation canonical hash without LF. Both are shipped and cross-checked.
Two full builds must be byte-identical. Raw caches never enter Git or wheel.

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

The 40-oracle file retains every oracle ID and assertion; authorized source
and license expectations now require Natural Earth and zero excluded assets. Service/HTTP tests,
dedicated two-connection races on both databases, deterministic cross-backend
HTTP byte fixtures, exact wheel inventory, real Chromium at 1024×768 and
1366×768, same-origin worker/network capture and inherited Product/Analysis
gates provide the evidence. Test/browser JSON and JUnit artifacts are uploaded
by `geography-r1`. Source acceptance does not perform the separate Windows
installer/clean-PC packaging increment.

Known limits: this is a historical May 2022 release with 16 Kazakhstan Admin 1
units. Names such as Нур-Султан and Алма-Ата are retained where NAME_RU supplies
them. It does not certify contemporary boundaries/names. Disputed boundaries
remain a versioned cartographic policy, not a legal conclusion. Approximate
coordinates and radius do not establish a surveyed conflict footprint. Source
acceptance does not repackage MVP6 or pass its external clean-PC smoke.

## Corrective history

The owner authorized exactly one third ordinary commit after B
2731ecd26dde5f321507ca237c4d18167d8bd631 (parent A
ba09340fecc446f677f8b4cf0c4ba3e565ebcee5):
`fix(geography): replace ODbL map data with Natural Earth`.
The workflow checks all three exact deltas, parents and messages, and prohibits
changes to models, migration 0019, Geography API schema, protected analytical
services, Studio/Player and package builders. No amend or history rewrite.
