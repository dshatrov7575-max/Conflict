# AI_EXCEPTION_REVIEW_V1 — AMENDMENT_C5_CHATGPT_REPLACEMENT_V1

Status: PREREGISTERED_BEFORE_CHATGPT_C5_RESULT

## Reason
The original Claude slot could not yield an admissible clean run; the Grok replacement self-reported outcome contamination; the Gemini replacement returned FRESH_ISOLATION_UNAVAILABLE before performing the 42 tasks. All those attempts remain preserved as audit evidence.

## Replacement
The third clean slot is reassigned to `EXPERT_C_CHATGPT_REPLACEMENT` for one fresh isolated ChatGPT temporary-chat run.

## Frozen conditions preserved
- canonical material SHA-256: `767da0d3f4fc189e587efd9084ea20ecb546f4f102c85e11f0153bc9d40a04fa`;
- same 42 frozen units;
- same cutoff `2011-12-15T23:59:59Z`;
- same evidence, availability, mapping, translation, no-rebinding, and attestation rules;
- A and B3 remain unchanged;
- no previous expert output is overwritten or reinterpreted.

## Independence requirement
The C5 run must be a fresh isolated ChatGPT temporary chat outside any Project, without prior-expert answers, prior review decisions, HUMAN coding, or outcome use. If isolation is unavailable, return `FRESH_ISOLATION_UNAVAILABLE` and do not execute the 42 tasks.

## Diversity limitation
A, B3, and C5 may use the same model family. This preserves session independence but weakens model-family diversity relative to the original A/B/C design. Final reporting must state this limitation explicitly and must not represent the three runs as three distinct model families.

## Validity
C5 is invalid for clean voting if `fresh_isolated_session=false` or `outcome_contamination_detected=true`, or if any other required isolation attestation is false.

## Non-retroactivity
This amendment authorizes only the new C5 replacement run before its result is observed. No comparison or decision rule is changed.
