# MAIN EXECUTION HANDOFF — C2A R2 PATH 9/12

Target: `software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js`

Read these exact governance artifacts first:
- `.github/c2a-r2/lifecycle-publication-js-execution-oracle.md` from commit `38f34a5cdf146aa99c2585ffe710546fdc984c45`
- `.github/c2a-r2/lifecycle-publication-js-source-audit.md` from commit `45b0259ab3fa8de473f34244e8e1eb3a3dc8b4cd`
- corrected template blob `a1e7e9f3fac0be61bbce6a2a4f6e8bb221f62101`

Work only from immutable R1 `22f0f173a941de88d6920b6e19821168e9b30cc8` / tree `f407e609adb2a8b94770b521a1302feb79281822`.

Produce only a one-path `M` candidate for the target JS in this step. Required fixes are exact:
1. strict dual validation/publication recovery ticket contracts;
2. download initiation is not retention proof;
3. POST unlock only after exact-copy or byte-exact file re-import;
4. no frozen `X-CSRFToken` inside semantic attempt or restored validation attempt;
5. fresh current presentation authority + action capability + same-origin CSRF at the actual allowed send boundary;
6. publication-ticket import can perform only exact FD06 operation GET recovery and can never reconstruct/enable publication POST.

Preserve all existing receipt/hash/identity checks, no retries, no timeout increases, no browser persistence expansion, no new Foundation authority, no test-count change.

Required terminal evidence before MAIN counts path 9/12:
- candidate Git blob SHA;
- unattached tree SHA;
- exact one-path `M` status against R1;
- `node --check production_studio/static/production_studio/lifecycle_publication.js` PASS;
- static evidence for the six invariants above.

Do not update PR #94 or its target branch. No merge/rebase/cherry-pick/amend/squash/force-push/release/G10.