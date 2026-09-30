# KBM E05 V1.0.0 — KBM_E05_V100_AI2 BLIND PRIMARY

Ты — независимый первичный AI-кодировщик. Выполни только этот standalone-пакет.

Запрещено использовать:
- внешний поиск;
- прежние AO2/episode outputs;
- известный исход конфликта;
- coordinator review;
- sibling primary output;
- любую память о значениях worker-side.

Верни только один JSON без Markdown и пояснений. Имя результата: `KBM_E05_V100_AI2_COMPLETED.json`.

## Frozen identity

- route_id: `AI_ONLY_PAIR_KBM_E05_V100`
- contract_version: `1.0.0`
- rubric_version: `2.1.0`
- coder_role: `KBM_E05_V100_AI2`
- input_sha256: `51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95`
- company actor_id: `KBM_MANAGEMENT_REPRESENTATION_STANCE_20110514`
- PTN: E05
- ptn_id: `728c8406-ba99-5787-9557-933b5670be7c`
- reference_statement: `Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов.`
- reference_sha256: `f689f671787c35619a3a32c6079908fb8ac5436a30cd832355b0238fe44f1deb`
- object: non-simultaneous company-stance → later worker-demand source-statement pair
- company source-report date: 2011-05-14
- worker source-report date: 2011-05-27
- carry_forward: NONE
- simultaneous_snapshot: false

Ты кодируешь только два company fields:
1. company POS_AO2;
2. company KVS_AO2.

Worker factor values намеренно не показаны и не должны выводиться.

## Frozen company evidence

Source ID: `AKTAU_BUSINESS_KBM_RELEASE_20110514`  
Publisher: aktau-business.com  
Publication date: `2011-05-14`  
Original URL identity: `http://www.aktau-business.com/2011/05/14/kbm.html`  
Wayback capture: `2011-05-15T05:47:06Z`  
Archive replay: `https://web.archive.org/web/20110515054706id_/http://www.aktau-business.com:80/2011/05/14/kbm.html`  
Raw payload: `58775` bytes  
SHA-256: `8c88985bf55e2cfa149395cb8e98de6d87798edcb9f18e614f58279935a8f63b`  
Authentication: `P1_ARCHIVE_REPLAY_AUTHENTICATED`.

The archived page reproduces a KarazhanbasMunai company release concerning the internal union dispute and negotiation procedures. Coder-visible content:

- The company describes a dispute inside the Karazhanbas workers' union and competing positions around union leadership.
- Management states that it is not entitled to interfere in the union's internal affairs.
- At the same time, the company states that the demand to remove the incumbent union chairman was unlawful because the required procedure for a general meeting had not been observed.
- The company says some collective-agreement demands had already been considered by a commission and certain agreements had been reached, pending worker approval.
- Management officially states that conducting negotiations through the protest action in that manner was unacceptable and that rights should be defended through lawful procedures.
- The company reports that constructive dialogue with participants ended the 12 May protest action.

This evidence authenticates what the archived company-release republication reported. It does not prove that the company's legal or factual characterizations were historically correct.

Do not import worker allegations, HRW retrospective paraphrases, government-only statements or later outcome information as company evidence.

## POS_AO2 anchors

- -10: explicit rejection/change of the whole reference across all essential components.
- -5: explicit demand to change at least one essential component.
- 0: explicit absence of directional preference.
- +5: explicit defence/preservation of at least one status-quo component.
- +10: explicit defence of the whole reference and rejection of substantial change across all essential components.

## KVS_AO2 anchors

- 0: issue explicitly irrelevant/not a decision criterion.
- 2: issue explicitly secondary to a named higher-priority issue and concession accepted.
- 5: issue explicitly included in actor's own formal demand set or actor's own declared action/decision/settlement/negotiation set.
- 8: consequential action/refusal/settlement/participation/continuation explicitly conditioned on resolution of this specific issue.
- 10: issue explicitly non-negotiable and relevant settlement/option refused without it.

### Reactive-actor rule

A rebuttal, rejection, or statement that the opponent's demand is unlawful/unfounded does not by itself satisfy KVS=5.

For KVS=5 there must additionally be an explicit link to the company's own action, decision, settlement, resource allocation, negotiation rule or policy criterion concerning E05.

A general preference for lawful procedure does not automatically establish E05-specific KVS=8.

Do not infer KVS from strike duration, sanctions, later violence, publicity, repetition, or rhetoric.

## Admission checks C1-C8

For each factor:
- C1 exact narrow company actor / PTN / reference / temporal object;
- C2 evidence traceable to this frozen input;
- C3 pre-cutoff historical content authentication;
- C4 decisive predicate attributable to company;
- C5 exactly one licensed anchor predicate fully satisfied;
- C6 provenance/dependency/source limitations considered;
- C7 fixed PTN/reference/non-simultaneous mapping respected; no carry-forward;
- C8 frozen independent-run protocol respected.

NUMERIC requires all C1-C8 true.
If no one licensed anchor is fully supported, return UNKNOWN with value=null and at least one failed gate.
If admitted evidence is genuinely incompatible for the same factor, return DISPUTED/null.

Allowed POS values: -10, -5, 0, 5, 10.
Allowed KVS values: 0, 2, 5, 8, 10.
UNKNOWN != 0.

## Required JSON structure

Top-level:
- route_id
- contract_version
- rubric_version
- input_sha256
- coder_role
- actual_model_label
- model_label_source
- run_id
- completed_at_utc
- attestation
- entries

Attestation must be:
- other_coder_output_seen=false
- prior_episode_outputs_seen=false
- outcome_used_as_evidence=false
- external_sources_used=false

Exactly two entries:
1. actor_id `KBM_MANAGEMENT_REPRESENTATION_STANCE_20110514` / factor `POS_AO2`
2. same actor / factor `KVS_AO2`

Each entry must contain:
- actor_id
- factor
- status
- value
- admission_checks C1..C8
- evidence_references
- rationale
- confidence
- calculation_release=false

Confidence:
- kind=QUALITATIVE_UNCALIBRATED
- value=HIGH|MEDIUM|LOW|UNKNOWN
- meaning=CONFIDENCE_IN_RECORDED_CODING_DECISION
- rationale=text

Do not compute RGU, KVPTN, Pol or UNO.
