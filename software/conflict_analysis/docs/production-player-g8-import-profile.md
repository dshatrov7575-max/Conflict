# Production Player G8 import profile and runtime contract

## Fixed source and profile identity

The packaged profile is
`domain/import_profiles/kz_zhanaozen_expert_v2_a5_v0_1.json`; its adjacent
`.sha256` file authenticates the exact JSON bytes. The profile explicitly
enumerates all 330 records and records the literal actor, element, role,
TimeSlice and canonical parameter identities needed by Foundation. `V4_ID` is
preserved verbatim as source-row/value identity and is never parsed to discover
semantic identity.

The controlling source hashes are:

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| A3 canonical glossary V4 term 2.0 | 5792 | `314ac6facb41ba532e475fb008bc8f97ba0b43df26cf0c194782cc24d93f5fff` |
| A4 coding manual V4 term 2.0 | 5914 | `ce45cc4d6a43950c8ae6d7a54a9a1a6646f7d80340d246d706588ee7060ab826` |
| A5 raw XLSX v0.1 | 198259 | `ba5dd521d61bb14d9e7f3883732d9685c79774430d4b1e3ac91f656a01744876` |
| Expert Form workbook | 84941 | `f27616595b7e58d8b636ef89fa086b696a0857d5bf39b84b1b35fa7d90e8e14c` |

A4 v2.1 is non-authoritative and is not substituted. The manifest and
`SHA256SUMS` were independently rehashed against these retained source
containers.

## Pinned mapping

- A5 `АК-01..АК-08` maps exactly to manifest actors `GU-01..GU-08`.
- A5 `КВК-01..КВК-06` maps exactly to manifest analytical elements
  `PTN-01..PTN-06`.
- `2011` with cutoff `2011-12-15`, `2022` with cutoff `2022-01-02`, and `2026`
  with cutoff `2026-08-21` map to TimeSlice codes equal to those dates.
- A5 `ПАВ/POS` and legacy `УОС` map to canonical `POS`.
- A5 `ЗВА/SAL` and legacy `КВС` map to canonical `SAL`.
- A5 `СА/POW` and legacy `РГУ` are `RECODING_REQUIRED` and create no value.
- A5 `ВСВ/ESW` and legacy `КВПТН` are `METHOD_BLOCKED` and create no value.

For each `GU × PTN` pair, the profile copies the literal code and source UUID
from the one exact `actor_element_roles` record in the published manifest. Zero
or multiple matches, a missing target, a wrong cutoff, or an applicability/name
disagreement fails closed before semantic writes.

## Transport and import

The browser sends one `multipart/form-data` request with a bounded raw XLSX file
and one strict JSON metadata part. The actual uploaded file's byte length and
SHA-256 bind preview, ticket, commit and receipt. They are not required to equal
the fixed A5 crosswalk source checksum.

Foundation previews a selected exact sheet and value column without writes.
Commit requires the retained preview checksum, operation UUID, `If-Match`, CSRF
token and explicit acknowledgement of all 42 excluded compatibility rows. The
service reparses the upload, rejects diagnostics, and atomically creates the
experiment-scoped assessments, `ParameterValue` rows, `ImportRun` and audit
receipt. A complete accepted file yields 144 assessment contexts and at most
288 value rows. Unknown and zero are distinct. Partial files can import valid
rows but never receive the full 330-row snapshot contract.

Recovery reads the immutable experiment-scoped `ImportRun` receipt. The receipt
snapshot is audit material, not a writable value lane. The Product interface
holds files, previews, tickets and operation identifiers in memory and makes
all writes through the same-origin Foundation endpoints.
