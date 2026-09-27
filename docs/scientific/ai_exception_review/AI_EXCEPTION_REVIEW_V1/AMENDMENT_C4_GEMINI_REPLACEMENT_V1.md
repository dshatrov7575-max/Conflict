# AI_EXCEPTION_REVIEW_V1 — AMENDMENT_C4_GEMINI_REPLACEMENT_V1

Status: PREREGISTERED_BEFORE_GEMINI_RESULT

## Reason for replacement
The previously preregistered Grok replacement returned a self-attestation with `outcome_contamination_detected=true`. Under the frozen comparison protocol and the Grok replacement amendment, that run is excluded from clean voting. Its result is preserved as audit evidence and is not used to modify the scientific decision rules.

## Replacement
The third clean slot is reassigned to `EXPERT_C_GEMINI_REPLACEMENT`.

No substantive protocol rule changes are made:
- canonical material SHA-256 remains `767da0d3f4fc189e587efd9084ea20ecb546f4f102c85e11f0153bc9d40a04fa`;
- the same 42 frozen units are used;
- cutoff remains `2011-12-15T23:59:59Z`;
- all evidence, mapping, translation, availability, no-rebinding, and attestation rules remain unchanged;
- A and B3 remain unchanged;
- prior Claude/Grok runs remain immutable audit artifacts.

## Contamination interpretation
The frozen packet already states that case identity is not masked and model training knowledge may exist. Training knowledge alone is not sufficient to set contamination=true. The flag is true if outcome knowledge influenced the review or the outcome was encountered during the run/search. This amendment does not weaken that rule; it records its literal interpretation to avoid over-conservative false positives.

## Validity
The Gemini replacement is invalid for clean voting if `fresh_isolated_session=false`, if another expert answer/review decision is accessed, or if `outcome_contamination_detected=true`.

## Non-retroactivity
No prior result is reinterpreted, overwritten, or promoted. This amendment only authorizes a new independent replacement run before its result is observed.
