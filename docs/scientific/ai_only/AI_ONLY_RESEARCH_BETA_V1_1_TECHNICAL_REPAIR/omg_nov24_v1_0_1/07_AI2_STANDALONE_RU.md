# OMG E02 Nov23–24 V1.0.1 — OMG_NOV24_V101_AI2 BLIND PRIMARY

Ты — независимый первичный AI-кодировщик. Выполни только этот standalone-пакет.

Не используй:
- внешний поиск;
- память о Жанаозене или известном исходе;
- прежние AO2/R2/episode outputs;
- прежние OMG V1.0.0 outputs;
- coordinator reviews;
- другой primary output.

Верни только один JSON без Markdown и пояснений. Имя результата: `OMG_NOV24_V101_AI2_COMPLETED.json`.

Это новый перспективный technical-repair route. Научный input не изменён; исправлен только response contract: поля `run_id`, `completed_at_utc`, `actual_model_label` и `model_label_source` теперь явно обязательны. Не пытайся восстанавливать или угадывать прежние ответы.

## Frozen identity

- route_id: `AI_ONLY_DYAD_OMG_NOV24_V101`
- contract_version: `1.0.1`
- rubric_version: `2.1.0`
- coder_role: `OMG_NOV24_V101_AI2`
- input_sha256: `72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4`
- event: `2011-11-23..2011-11-24`
- source_report_date: `2011-11-30`
- carry_forward: `NONE`
- simultaneous_snapshot: false
- PTN: `E02`
- ptn_id: `74872afd-9303-5d0f-a70a-d5fe7154645c`
- reference_statement: `Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.`
- reference_sha256: `197738bbdb7c8cd7dcc7b66cb2aa0b95084f72aa24e14c6604401ebd75eec172`

## Frozen source authentication

Source: Contur.kz, 30.11.2011, `Проклятый коэффициент`.  
Historical Wayback capture: `2011-12-03T22:27:42Z`.  
Archive replay: `https://web.archive.org/web/20111203222742id_/http://www.contur.kz:80/node/1822`  
Payload bytes: `156307`.  
Payload SHA-256: `d6bd3102d40bc51dde3847ffe1fe9d6abb5c3d63492ecf9ad2b96e9ae4fcd90c`.

### Mandatory source-bias warning

The article uses openly hostile, insulting and normative language toward the dismissed workers. Editorial labels, motive claims, insults, rhetorical intensity, generalized moral judgments and the author's conclusions are not factor evidence. They may not increase POS magnitude or KVS.

Use only concrete demands, actions, offers, refusals and pay-treatment statements that the article attributes to the specified narrow actor. If the decisive predicate is not clearly attributable to that actor, fail C4 and return UNKNOWN for that factor.

Both actor rows come from this same article. They are not independent corroboration.

## Actor A

actor_id: `OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR`

Scope: dismissed/former OzenMunaiGaz workers and their representatives in the 23–24 November negotiation episode, only as attributed in the frozen source.

Coder-visible evidence:
- The source states that dismissed workers wanted to return to OMG and sought higher pay treatment involving the 1.7 and 1.8 coefficients.
- It reports a 23–24 November meeting involving worker-side representatives and invited experts.
- It reports that the dismissed workers rejected the proposed settlement/compromise and did not sign the reconciliation document.
- It reports that removal of the OMG director was also among their demands; pay was therefore not the only issue.

Limited exact fragment:
`Они желают… ну, вы уже догадались – вернуться в ОМГ и умножить свои бывшие оклады на 1.7. и 1.8.`

## Actor B

actor_id: `RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR`

Scope: RD KMG / OMG employer-side position and actions in the same negotiation episode. Do not automatically attribute government-only actions to the employer.

Coder-visible evidence:
- The source describes the employer-side position that the disputed coefficients had already been incorporated in pay calculations and that additional reimbursement or a further salary increase on that basis was not accepted.
- It reports that RD KMG revised its contractor-use plan to support alternative jobs and had a multi-year arrangement creating additional contractor positions. This employment offer is context; do not treat it as pay-specific KVS unless the KVS predicate itself is met.
- It reports willingness in the negotiation context to revisit some collective-agreement provisions, but the article often merges government and employer actions. If decisive employer attribution is unclear, fail C4.
- It states that the employer/administrative side defended the legality/correctness of the existing coefficient treatment.

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
- 8: consequential action, refusal, settlement, participation or continuation explicitly conditioned on resolution of this specific issue.
- 10: issue explicitly non-negotiable and relevant settlement/option refused without it.

### Reactive-actor rule

A rebuttal, rejection, or claim that the opponent's demand is unfounded does not by itself satisfy KVS=5. KVS=5 requires an additional explicit link to that actor's own action, decision, settlement, resource allocation or policy criterion concerning pay. A dispute-wide condition does not automatically establish pay-specific KVS=8.

Do not infer KVS from strike duration, headcount, production loss, sanctions, repeated coverage or emotional intensity.

## C1-C8

For every actor×factor entry:
- C1 exact narrow actor/PTN/event identity;
- C2 evidence traceable to the frozen input;
- C3 pre-cutoff historical content authentication;
- C4 decisive predicate attributable to the narrow actor;
- C5 exactly one licensed anchor predicate fully satisfied;
- C6 provenance, dependency and hostile editorial framing reviewed;
- C7 fixed temporal mapping respected; no carry-forward;
- C8 independent frozen-run protocol respected.

NUMERIC requires all C1-C8 true.  
If no one anchor is fully supported, return UNKNOWN/null and expose at least one failed gate.  
If admitted evidence is genuinely incompatible for the same actor-factor, return DISPUTED/null.

Allowed POS: -10, -5, 0, 5, 10.  
Allowed KVS: 0, 2, 5, 8, 10.  
UNKNOWN != 0.

## Mandatory top-level contract

The JSON must contain all and only these top-level fields:
- `route_id`
- `contract_version`
- `rubric_version`
- `input_sha256`
- `coder_role`
- `actual_model_label`
- `model_label_source`
- `run_id`
- `completed_at_utc`
- `attestation`
- `entries`

Requirements:
- `actual_model_label` must be a non-empty string naming the actual model.
- `model_label_source` must be a non-empty string explaining how the model identity is known.
- `run_id` must be a newly generated non-empty unique string for this run; use a UUID if possible.
- `completed_at_utc` must be a non-empty UTC timestamp ending in `Z`.
- Do not omit any of these four fields even if the interface does not provide them automatically.

Attestation must be exactly:
- `other_coder_output_seen=false`
- `prior_episode_outputs_seen=false`
- `outcome_used_as_evidence=false`
- `external_sources_used=false`

Exactly four unique entries:
1. `OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR` / `POS_AO2`
2. `OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR` / `KVS_AO2`
3. `RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR` / `POS_AO2`
4. `RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR` / `KVS_AO2`

Each entry must contain:
- `actor_id`
- `factor`
- `status`
- `value`
- `admission_checks` with exactly C1..C8
- `evidence_references`
- `rationale`
- `confidence`
- `calculation_release=false`

Confidence object:
- `kind=QUALITATIVE_UNCALIBRATED`
- `value=HIGH|MEDIUM|LOW|UNKNOWN`
- `meaning=CONFIDENCE_IN_RECORDED_CODING_DECISION`
- `rationale=<text>`

Use this exact top-level template and replace placeholders:

```json
{
  "route_id": "AI_ONLY_DYAD_OMG_NOV24_V101",
  "contract_version": "1.0.1",
  "rubric_version": "2.1.0",
  "input_sha256": "72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4",
  "coder_role": "OMG_NOV24_V101_AI2",
  "actual_model_label": "<non-empty actual model label>",
  "model_label_source": "<non-empty source of model identity>",
  "run_id": "<new unique non-empty run id>",
  "completed_at_utc": "<UTC timestamp ending in Z>",
  "attestation": {
    "other_coder_output_seen": false,
    "prior_episode_outputs_seen": false,
    "outcome_used_as_evidence": false,
    "external_sources_used": false
  },
  "entries": [
    {
      "actor_id": "OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR",
      "factor": "POS_AO2",
      "status": "NUMERIC|UNKNOWN|DISPUTED",
      "value": null,
      "admission_checks": {"C1":false,"C2":false,"C3":false,"C4":false,"C5":false,"C6":false,"C7":false,"C8":false},
      "evidence_references": [],
      "rationale": "<text>",
      "confidence": {"kind":"QUALITATIVE_UNCALIBRATED","value":"HIGH|MEDIUM|LOW|UNKNOWN","meaning":"CONFIDENCE_IN_RECORDED_CODING_DECISION","rationale":"<text>"},
      "calculation_release": false
    },
    {
      "actor_id": "OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR",
      "factor": "KVS_AO2",
      "status": "NUMERIC|UNKNOWN|DISPUTED",
      "value": null,
      "admission_checks": {"C1":false,"C2":false,"C3":false,"C4":false,"C5":false,"C6":false,"C7":false,"C8":false},
      "evidence_references": [],
      "rationale": "<text>",
      "confidence": {"kind":"QUALITATIVE_UNCALIBRATED","value":"HIGH|MEDIUM|LOW|UNKNOWN","meaning":"CONFIDENCE_IN_RECORDED_CODING_DECISION","rationale":"<text>"},
      "calculation_release": false
    },
    {
      "actor_id": "RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR",
      "factor": "POS_AO2",
      "status": "NUMERIC|UNKNOWN|DISPUTED",
      "value": null,
      "admission_checks": {"C1":false,"C2":false,"C3":false,"C4":false,"C5":false,"C6":false,"C7":false,"C8":false},
      "evidence_references": [],
      "rationale": "<text>",
      "confidence": {"kind":"QUALITATIVE_UNCALIBRATED","value":"HIGH|MEDIUM|LOW|UNKNOWN","meaning":"CONFIDENCE_IN_RECORDED_CODING_DECISION","rationale":"<text>"},
      "calculation_release": false
    },
    {
      "actor_id": "RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR",
      "factor": "KVS_AO2",
      "status": "NUMERIC|UNKNOWN|DISPUTED",
      "value": null,
      "admission_checks": {"C1":false,"C2":false,"C3":false,"C4":false,"C5":false,"C6":false,"C7":false,"C8":false},
      "evidence_references": [],
      "rationale": "<text>",
      "confidence": {"kind":"QUALITATIVE_UNCALIBRATED","value":"HIGH|MEDIUM|LOW|UNKNOWN","meaning":"CONFIDENCE_IN_RECORDED_CODING_DECISION","rationale":"<text>"},
      "calculation_release": false
    }
  ]
}
```

Do not compute RGU, KVPTN, Pol or UNO.
