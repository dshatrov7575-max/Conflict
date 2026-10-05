# PR-31 — Node-24-native required Actions

## Purpose

The green PR-29 and PR-30 required workflows still emitted GitHub's deprecation
warning because four pinned official Actions commits declared the Node 20 action
runtime and were only being force-executed on Node 24 by the hosted runner.

This slice replaces only those workflow dependencies. It does not change
product code, Calculation Core, formulas, models, migrations, scientific data
or claim boundaries.

## Exact official pins

- `actions/checkout@v7.0.1` →
  `3d3c42e5aac5ba805825da76410c181273ba90b1`;
- `actions/setup-python@v7.0.0` →
  `5fda3b95a4ea91299a34e894583c3862153e4b97`;
- `actions/setup-node@v7.0.0` →
  `820762786026740c76f36085b0efc47a31fe5020`;
- `actions/upload-artifact@v7.0.1` →
  `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`.

Each exact commit's `action.yml` declares `runs.using: node24`. The current
GitHub-hosted runner version is newer than the minimum `2.327.1` required by
these Node 24 releases.

## Cache boundary

`setup-node@v7` can automatically enable npm caching from package metadata. The
required product workflow has no npm dependency installation and does not need
that mutable cache surface, so both invocations explicitly set
`package-manager-cache: false`.

## Fail-closed verification

The required-gate verifier pins all four exact commit identities and rejects
removal of either cache-disable declaration. The ordinary full-product jobs,
production image gate and three-way reproducible-wheel comparison remain
unchanged and must pass live before technical acceptance.

## Boundaries

This removes the confirmed Node 20 action-runtime deprecation from the required
product workflow only. Historical research workflows are outside this focused
slice. It does not establish registry signing, SBOM/attestation verification,
deployment correctness or scientific validity.
