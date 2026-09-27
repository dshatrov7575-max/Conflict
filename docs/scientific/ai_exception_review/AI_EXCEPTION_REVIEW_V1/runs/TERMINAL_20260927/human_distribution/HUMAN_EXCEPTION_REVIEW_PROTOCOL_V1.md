# HUMAN_EXCEPTION_REVIEW_PROTOCOL_V1

Status: FROZEN_BEFORE_HUMAN_RESPONSES

## Scope
This protocol governs the two independent human exception reviews E1 and E2 for the 42 units routed to HUMAN_EXCEPTION_QUEUE by the terminal AI comparison. It is not HUMAN POS/KVS coding, not adjudication of H1/H2, and not inter-coder reliability measurement.

## Independence
E1 and E2 receive the same factual packet but do not see each other's answers, AI answers, AI voting, prior comparison results beyond the fact that the units require human exception review, or the conflict outcome. Each reviewer works independently.

## Response requirements
Each reviewer returns exactly one JSON response covering all 42 unit_ids in HUMAN_EXCEPTION_UNIT_REGISTRY.json. Required top-level attestations:
- no_other_reviewer_answers_seen=true
- no_ai_answers_seen=true
- no_outcome_used=true
- no_factor_scoring_or_uno=true

Per unit:
- status is RESOLVED / NOT_RESOLVED / NEED_HUMAN;
- reason is non-empty;
- confidence is [0,1];
- RESOLVED requires exact_evidence and evidence_reference and requires remaining_unknowns=[];
- NOT_RESOLVED and NEED_HUMAN require at least one remaining_unknown.

## Frozen comparison routing
The comparator does not judge semantic equivalence of evidence and does not change admission automatically.

For each unit:
1. Either reviewer NEED_HUMAN -> ESCALATE_REQUIRED.
2. Both NOT_RESOLVED -> OPEN_NOT_RESOLVED.
3. One RESOLVED and the other NOT_RESOLVED -> DIFFERENCE_REQUIRES_COORDINATOR.
4. Both RESOLVED -> DOUBLE_HUMAN_RESOLVED_CANDIDATE.
5. Any other status combination -> DIFFERENCE_REQUIRES_COORDINATOR.

Every DOUBLE_HUMAN_RESOLVED_CANDIDATE still requires a separate coordinator evidence-authentication step. Human agreement alone is not sufficient to change admission, mapping, translation, or availability status.

## Coordinator verification
The comparator emits COORDINATOR_VERIFICATION_TEMPLATE.json only for candidate/difference/escalation units. The coordinator must inspect original evidence and both independent responses without altering them. A coordinator disposition can be VERIFIED_RESOLVED / OPEN_NOT_RESOLVED / RETURN_FOR_SPECIFIC_CHECK. The coordinator must state exact evidence reference and reasoning.

No numerical agreement statistic, kappa, or HUMAN reliability claim is produced from E1/E2 exception review.

## Scientific boundary
This protocol cannot:
- assign POS/KVS;
- assign or infer RGU/KVPTN;
- compute UNO;
- release frozen H1/H2 automatically;
- claim model validation;
- modify frozen Fact/Fragment/DocumentVersion/Source chains.

The formal H1/H2 double-blind coding pilot remains a separate later stage.
