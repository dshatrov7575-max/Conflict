# ADR 0017 — Windows owner alpha through a private WSL2 distribution

Status: implementation candidate for G10, not independently accepted.

The accepted C2A parent is 123f2b081ce2a09d7d193f9e4b20644f5802d7fe,
tree d67e39cbb965483f3c9cabcc91f724d8bf986fb4. G10 changes one README
and adds the 27 paths recorded in the source verifier. Application settings,
routes, models, enums, permissions, migrations, package metadata and all
accepted Foundation/Studio/Player source remain unchanged. The domain migration
leaf remains 0018_workspace_assessment_projection.

## Runtime and immutable inputs

The owner package targets Windows 11 x64 with existing WSL2, hardware
virtualization, PowerShell 7 and Microsoft Edge. It does not install Windows
software, enable features, elevate, change policy or configure a runner.
PostgreSQL 18.4 and CPython 3.12.14 come from the two immutable amd64 OCI
digests in the builder and Containerfile. Linux libraries are bounded by those
OCI filesystems. Nginx 1.26.3 is extracted from the two exact Debian snapshot
archives; maintainer scripts and their administrative dependencies, such as
iproute2, are not invoked. Runtime shared-library resolution is checked at
build time. The actual Debian inventory and archive checksums enter the
runtime report and SBOM.

The complete wheel closure was resolved at authoring time and embedded in the
builder. URLs, wheel filenames, exact versions, byte lengths, hashes and
Requires-Dist metadata are recorded there. Closure validation uses Linux
CPython 3.12 markers and the psycopg binary extra. Build and runtime installs
use a local wheelhouse, exact versions, --no-index, --no-deps and
--require-hashes. No resolver runs during artifact acceptance or owner startup.

One application wheel is built from a clean exact final G10 HEAD/TREE with
SOURCE_DATE_EPOCH. The accepted wheel intentionally excludes the Studio Help
catalog; its separately copied exact source-tree bytes are bound in the
runtime report. No product packaging metadata is rewritten to include it.
Two fresh runtime builds consume that same wheel. Export normalization fixes
metadata and machine-specific hosts/resolver files; independent normalized
rootfs bytes and independent ZIP bytes must match.

Payload P precedes manifest M, then SHA256SUMS S, ZIP Z, external evidence E and
the acceptance index. M hashes P only; S hashes P and M only. Neither includes
its own digest or the future ZIP digest. The verifier requires exact member
sets and rejects traversal, case collisions, extra files and altered bytes.
Test results and final Windows evidence never rewrite the ZIP. Generated CMD
wrappers are artifact members, not extra repository paths.

## Runtime lifecycle and identities

PostgreSQL and Gunicorn expose private Unix sockets. Nginx listens only on
127.0.0.1 at the installation's frozen port. Dedicated non-root service users
own the application and database processes; the bounded controller is root
only inside its own WSL distribution. Linux interop and Windows automounts are
disabled in this custom distribution. DEBUG and SQLite fallback are disabled.

Initialization creates three canonical nonstaff, nonsuperuser Django users
with unusable passwords. The package stores their exact primary keys in
protected private state. Every restart verifies those same users, exact
permissions, active status and permission-free project scope groups. It uses
the accepted Studio principal classifier and Player assessment principal
function, rejects extra/mixed capabilities, and does not reactivate revoked
users. Session renewal revokes old database sessions and creates sessions for
the same primary keys; historical actor identifiers are never rewritten.

Grant-Publisher requires the exact existing Project UUID and explicit owner
confirmation. It adds both Publisher and Assessor to the existing
studio-project:<UUID> group, leaving group permissions and user capabilities
unchanged. The three Edge profiles have different private directories and
cookies. A secret bundle crosses only captured stdin/stdout streams in memory.
The public receipt contains role names and user PKs. A temporary debugging
browser injects a host-only HttpOnly cookie, closes and flushes its protected
cookie jar, and proves its debug port closed before a working browser opens.

## Launch admission

Generated CMD entry points evaluate effective PowerShell policy and every
required script/module's zone, signature and trusted-publisher state before
executing packaged PowerShell. There is no Bypass, Unblock-File, trust import,
policy modification or automatic publisher approval. Restricted and
controlling policy denial stop before import. Internet-marked unsigned bytes
under RemoteSigned fail closed. This candidate is not claimed to be signed.

An unsigned property is not an accepted workaround for a blocking policy.
L01-L06 and actual offline L05 from the final downloaded/extracted ZIP are
mandatory. PRECODE capacity PASS for LM-STUDIO does not establish final
launch admission. Issue #28 comment 5662429304 records
WINDOWS_E2E_CHANNEL_ID=NOT_YET_BOUND. The absence of a channel does not block
this implementation, but absent real Windows evidence prevents
READY_FOR_MAIN_REVIEW. No runner or remote channel is installed here.

## Private full backup and restore

A package-level nonblocking operation lock distinguishes BUSY from UNKNOWN.
Backup stops and drains Nginx/Gunicorn without force-kill and requires zero
other PostgreSQL client sessions, active transactions and locks. Unknown,
unreadable or nonzero state is a failure, never zero. It captures the full
database, role definitions, canonical principal map and protected signing
secret. The complete graph covers all application tables, sequences,
constraints, triggers, extensions and privileges. JSON null and numeric zero
remain different values. DocumentContent.original_bytes and all immutable
evidence/receipt rows are included in full; no capture is downloaded or
invented. Foundation 2.2 export remains a separate structural reconciliation.

A root-owned private manifest binds runtime/source/wheel identities and every
backup object's length and SHA-256. Windows retains a separate trusted-origin
receipt in the existing private installation record; an arbitrary hash-valid
file is not automatically admitted as a backup. Backups are never distributed
or publicly uploaded.

Restore imports the same rootfs into a new isolated candidate, initializes an
empty database, and restores the full schema/data/roles without Django
bootstrap, generic import, reprojection or in-place downgrade. It compares
every logical table and structural dependency before opening UI, verifies the
migration plan is empty and the canonical users are exact, invalidates all
restored sessions, then compares all remaining data again. The source and old
backups are preserved. Switching to a verified candidate is a separate
confirmed action. Failed candidates remain isolated for diagnosis.

## Acceptance boundary

The literal registry is 10 portable, 10 Pester contract and 2 real Windows
E2E nodes. Portable tests exercise exported rootfs containers and full private
restore with synthetic data. Pester mocks test orchestrator contracts only.
Hosted Windows Server cannot satisfy Windows 11 capacity or E2E gates.
Accepted parent matrices require Foundation PostgreSQL 350, SQLite 322 plus
28 named skips, Product 68 per database, Chromium 10, migration and isolated
same-wheel checks. Every claim must reference final exact-head outputs.

The only permitted delivery is an ordinary bounded branch and one open Draft
PR. Merge, history rewriting, tag, release and repository settings changes
remain outside authority. Any missing required real Windows or exact-head CI
evidence produces BLOCKED_G10_CI_EVIDENCE_GAP, not a reduced acceptance gate.

