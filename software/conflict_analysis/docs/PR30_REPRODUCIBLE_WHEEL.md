# PR-30 — reproducible application wheel gate

## Purpose

This slice closes the confirmed cross-job wheel-identity gap observed after the
green PR-29 run. The SQLite and PostgreSQL jobs built application wheels with
identical member names, member bytes, CRC values and sizes, but different
SHA-256 values because all 210 ZIP entries inherited each job's checkout/build
time.

It does not change Calculation Core, formulas, models, migrations, routes,
scientific inputs, HUMAN/AI lanes, historical admission or claim boundaries.

## Canonical builder

`scripts/build_reproducible_wheel.py` is now the only supported application
wheel builder for the required workflow and the production Docker target. It:

- uses the already locked build environment and `--no-build-isolation`;
- seals `SOURCE_DATE_EPOCH` to `315532800` (`1980-01-01T00:00:00Z`, the
  earliest DOS/ZIP timestamp);
- rejects a conflicting caller-supplied epoch;
- rejects an output directory inside the project source tree;
- requires exactly one output wheel;
- verifies every ZIP member has the canonical timestamp;
- emits machine-readable size, entry count and SHA-256 evidence.

Source bytes and `RECORD` still determine wheel identity; only incidental build
time is removed.

## Required gate

The SQLite and PostgreSQL jobs publish the SHA-256 of their independently built
application wheels as job outputs. The production image retains the identity of
the exact independently built wheel installed into that image and publishes it
from the installed-runtime probe. The stable `Required product gate` now fails
unless:

1. all independent product jobs pass;
2. all three wheel digests are non-empty; and
3. the SQLite, PostgreSQL and production-image wheel digests are byte-for-byte
   identical.

The aggregate uploads
`conflict-required-wheel-reproducibility-<run>-<attempt>` as evidence.

## Boundaries

This establishes reproducibility of the pure application wheel across the two
supported Ubuntu required jobs. It does not by itself establish reproducible
OCI image layers, registry publication, image signing, SBOM/attestation
verification, deployment correctness or scientific validity.
