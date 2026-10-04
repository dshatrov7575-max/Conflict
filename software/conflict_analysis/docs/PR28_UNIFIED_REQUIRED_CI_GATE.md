# PR-28 — Unified Product CI Gate

## Purpose

This change closes the repository-wide test-coverage gap identified by the external hostile reviews. A pull request that changes `software/conflict_analysis/**` now starts one stable product gate instead of relying on historical branch-specific routes or a default `pytest` command limited to Domain and Calculation Core.

The stable check name is:

```text
Required / Unified Product Gate
```

The workflow runs for every pull request touching the product tree, for pushes to `main`, and by explicit manual dispatch. Repository branch-protection configuration is not changed by this commit; making the check mandatory at the GitHub ruleset level remains an administrative operation.

## Gate contents

The single PostgreSQL 18 job:

1. checks out the exact event head;
2. installs Python 3.12 and Node.js 24;
3. locates the runner Chromium binary;
4. builds the single root wheel;
5. installs that wheel outside the source tree and verifies package origins;
6. resolves Calculation and Scenario routes, templates and static assets;
7. runs `collectstatic` from the installed wheel;
8. checks migrations and applies them to PostgreSQL 18;
9. runs the root `pytest` registry with Player and Scenario browser flags enabled;
10. rejects any failed, errored or skipped test in the final JUnit receipt.

The test process is network-denied except for localhost database and live-server traffic. No model API or external research source is used.

## Default test registry

The root `pytest.ini` now covers:

- `conflict_analysis/tests`;
- `domain/tests`;
- `calculation/tests`;
- `production_studio/tests`;
- `production_player/tests`;
- `player_integration/tests`;
- `scenario_modeling/tests`.

A green root `pytest` can therefore no longer mean only Domain and Calculation Core.

## Supply-chain scope

The workflow's GitHub actions are pinned to exact commits:

- `actions/checkout` — `11d5960a326750d5838078e36cf38b85af677262`;
- `actions/setup-python` — `a26af69be951a213d495a4c3e4e4022e16d87065`;
- `actions/setup-node` — `49933ea5288caeca8642d1e84afbd3f7d6820020`.

Dependency lockfiles, immutable container-image digests and production deployment settings remain separate hardening tasks. This PR does not claim full supply-chain reproducibility.

## Scientific and product boundaries

This gate establishes technical regression coverage only. It does not establish:

- HUMAN validation or reliability;
- historical snapshot or historical area UNO;
- construct or predictive validity;
- truth of evidence or admission of exact editions;
- production deployment readiness.

Calculation Core, formulas, domain models, migrations, scientific state and RunReceipt contracts are unchanged.
