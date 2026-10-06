# D25 E02 V1.0.0 — D25_E02_V100_AI2 BLIND PRIMARY

Ты — независимый первичный AI-кодировщик. Выполни только этот standalone-пакет.

Запрещено использовать:
- внешний поиск;
- прежние AO2/R2/episode outputs;
- известный исход конфликта;
- coordinator review;
- sibling primary output.

Верни только один JSON без Markdown и пояснений. Имя результата: `D25_E02_V100_AI2_COMPLETED.json`.

## Frozen identity

- route_id: `AI_ONLY_DYAD_D25_E02_V100`
- contract_version: `1.0.0`
- rubric_version: `2.1.0`
- coder_role: `D25_E02_V100_AI2`
- input_sha256: `aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa`
- source_report_date: `2011-10-13`
- carry_forward: NONE
- simultaneous_snapshot: false
- PTN: E02
- ptn_id: `74872afd-9303-5d0f-a70a-d5fe7154645c`
- reference_statement: `Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.`
- reference_sha256: `197738bbdb7c8cd7dcc7b66cb2aa0b95084f72aa24e14c6604401ebd75eec172`

Ты кодируешь ровно четыре записи:
1. worker POS_AO2
2. worker KVS_AO2
3. company POS_AO2
4. company KVS_AO2

Никакие прежние значения не показаны и не должны реконструироваться.

## Frozen source authentication

Source ID: `D25_EURASIANET_20111013`
Publisher: EurasiaNet
Publication date: 2011-10-13
Original URL identity: `http://www.eurasianet.org/node/64310`
Wayback capture: `2011-10-16T06:09:58Z`
Archive replay: `https://web.archive.org/web/20111016060958id_/http://www.eurasianet.org:80/node/64310`
Payload bytes: `56719`
Payload SHA-256: `c6ae02c231a18cf574743016e307a1b2d302edbc6fe7386c8dc636c679395005`
Witness: `AW-D25-20111016060958`

Provenance status: archive payload/hash/size were rechecked in the frozen R2 acquisition context; this standalone inherits that receipt and does not claim a new network acquisition.

## Actor A — dismissed KMG EP workers

actor_id: `D25_DISMISSED_KMG_EP_WORKERS_20111013`

Scope: the large group of dismissed KMG EP workers described as maintaining the tent-city protest in D25; do not broaden to all KMG EP workers or the sector.

Evidence ID: `D25-FREINSTATE`

Exact fragment:
`demanding reinstatement and a review of salaries`

Context:
`The workers fired by KMG EP have not faded away. A large group has set up a tent city in the center of Zhanaozen, a dusty town three hours’ drive from the regional administrative center of Aktau. From there, they have kept up their protest, demanding reinstatement and a review of salaries.`

Prospective rule:
`review of salaries` does **not automatically** equal `pay rise`. For POS=-5, the admitted wording/context itself must support a demand to change the current pay arrangement, not merely a neutral review procedure. If that directional predicate is not fully supported, fail C5 and return UNKNOWN for worker POS.

Continued protest, tent-camp duration, headcount or consequences do not by themselves justify KVS=8/10.

## Actor B — KMG EP management

actor_id: `D25_KMG_EP_MANAGEMENT_20111013`

Scope: only the company/KMG EP position explicitly attributed by D25. Do not convert journalist characterizations into company statements.

Evidence IDs: `D25-FFAIR`, `D25-FRAISES`

Exact fragments:
- `company insists that its employees are fairly compensated`
- `has raised salaries six times since 2008`

Context:
`Thus far, KMG EP has been uncompromising over the key demand of higher take-home pay. The company insists that its employees are fairly compensated, noting that it has raised salaries six times since 2008 and that it offered strikers the chance to return to work.`

Mandatory voice boundary:
The first sentence, `KMG EP has been uncompromising over the key demand...`, is journalist voice unless explicitly attributed to the company. It may not by itself establish company KVS, non-negotiability or priority.

Prospective KVS rule:
Past salary increases may establish company action history, but do not automatically satisfy KVS=5 for the current source object. KVS=5 requires that the admitted source explicitly links pay to the company's own declared action/decision/settlement/policy criterion in the relevant object, not merely provide historical justification.

## POS_AO2 anchors

- -10: explicit rejection/change of the whole reference across all essential components.
- -5: explicit demand to change at least one essential component.
- 0: explicit absence of directional preference.
- +5: explicit defence/preservation of at least one status-quo component.
- +10: explicit defence of the whole reference and rejection of substantial change across all essential components.

## KVS_AO2 anchors

- 0: issue explicitly irrelevant/not a decision criterion.
- 2: issue explicitly secondary to a named higher-priority issue and concession accepted.
- 5: issue explicitly included in the actor's own formal demand set or declared action/decision/settlement set.
- 8: consequential action/refusal/settlement/participation/continuation explicitly conditioned on resolution of this specific issue.
- 10: issue explicitly non-negotiable and relevant settlement/option refused without it.

## C1-C8

For every actor×factor:
- C1 exact actor/PTN/source identity;
- C2 frozen text/context traceable;
- C3 pre-cutoff historical content authentication;
- C4 decisive predicate attributable to the narrow actor;
- C5 exactly one licensed anchor fully satisfied;
- C6 provenance/dependency/voice boundary reviewed;
- C7 fixed same-report mapping respected; no carry-forward;
- C8 independent frozen-run protocol respected.

NUMERIC requires all C1-C8 true.
If no one anchor is fully supported, return UNKNOWN/null with at least one failed gate.
If admitted evidence is genuinely incompatible for the same actor-factor, return DISPUTED/null.

Allowed POS values: -10,-5,0,5,10.
Allowed KVS values: 0,2,5,8,10.
UNKNOWN != 0.

## Required top-level fields

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

Attestation must be exactly:
- other_coder_output_seen=false
- prior_episode_outputs_seen=false
- prior_r2_outputs_seen=false
- outcome_used_as_evidence=false
- external_sources_used=false

Exactly four unique entries:
- D25_DISMISSED_KMG_EP_WORKERS_20111013 / POS_AO2
- D25_DISMISSED_KMG_EP_WORKERS_20111013 / KVS_AO2
- D25_KMG_EP_MANAGEMENT_20111013 / POS_AO2
- D25_KMG_EP_MANAGEMENT_20111013 / KVS_AO2

Each entry:
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
