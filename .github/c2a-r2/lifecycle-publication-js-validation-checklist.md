# C2A R2 lifecycle_publication.js validation checklist

Target: software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js

Scope:
- Validate only the C2A R2 delta.
- Preserve frozen publication contracts, canonical JSON, SHA256, UUID, manifest and receipt boundaries.
- Do not alter PR #94.

Required evidence before counting path 9/12:
- exact candidate blob
- syntax/static validation evidence
- tree inclusion proof
- no ref update until candidate is independently validated
