# KBM E02 V1.0.0 — KBM_COMPANY_E02_V100_AI2 BLIND PRIMARY

Ты — независимый первичный AI-кодировщик. Выполни **только этот standalone-пакет**. Не используй внешний поиск, память о Жанаозене/Каражанбасе, прежние AO2/episode outputs, исход конфликта, другой primary output или coordinator review.

Верни **только один JSON**, без Markdown и пояснений, и сохрани его как `KBM_E02_V100_AI2_COMPLETED.json`.

## Frozen identity

- route_id: `AI_ONLY_DYAD_KBM_E02_V100`
- contract_version: `1.0.0`
- rubric_version: `2.1.0`
- coder_role: `KBM_COMPANY_E02_V100_AI2`
- input_sha256: `d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42`
- actor_id: `KBM_MANAGEMENT_FORMAL_RESPONSE_20110527`
- PTN: E02
- ptn_id: `74872afd-9303-5d0f-a70a-d5fe7154645c`
- reference_statement: `Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.`
- reference_sha256: `197738bbdb7c8cd7dcc7b66cb2aa0b95084f72aa24e14c6604401ebd75eec172`
- object: non-simultaneous demand→formal-response dyad
- carry_forward: NONE
- source-report date for company statement: 2011-05-27
- the page dateline reports 2011-05-26
- historical same-date snapshot: false

Ты кодируешь **только два company fields**: `POS_AO2` и `KVS_AO2`. Значения worker-side намеренно не показаны и не должны выводиться.

## Frozen company evidence

Source ID: `KBM_NOMAD_PRESS_RESPONSE_20110527`  
Publisher/page: Nomad, 27.05.2011.  
Original URL identity: `http://nomad.su/?a=11-201105270010`  
Wayback replay: `https://web.archive.org/web/20110528153227id_/http://www.nomad.su/?a=11-201105270010`  
Capture: `2011-05-28T15:32:27Z`  
Raw payload: `30312` bytes  
SHA-256: `4280ad5774d94cae7efc788943301852550080c69c28a02fb99ddbadb4b9f06a`  
Authentication: `P1_ARCHIVE_REPLAY_AUTHENTICATED`.

The archived page explicitly attributes the information to the KBM press service. It reports a company response to the wage dispute. The company rejects the strikers' requested pay coefficients as unfounded and cites official/legal opinions supporting its position. It also describes KBM's **own** wage/tariff actions: recurring increases, a stated cumulative 2007–2011 wage-increase range, and current minimum/maximum tariff figures. The page further reports that KBM management had repeatedly proposed resolving the dispute at the negotiating table.

Limited verbatim evidence from the authenticated page:
- `КБМ произведено повышение заработных плат работников в диапазоне от 59,5% до 90,1 % от размера заработной платы`
- `за столом переговоров`

These are the company's declared positions/actions. They are not independent proof that compensation was fair, and nothing here establishes worker acceptance, a 15.12.2011 state, or a simultaneous snapshot.

## POS_AO2 anchors

- -10 = explicit rejection/change of the whole reference across all essential components.
- -5 = explicit demand to change at least one essential component.
- 0 = explicit absence of directional preference.
- +5 = explicit defence/preservation of at least one status-quo component.
- +10 = explicit defence of the whole reference and rejection of substantial change across all essential components.

## KVS_AO2 anchors

- 0 = issue explicitly irrelevant/not a decision criterion.
- 2 = issue explicitly secondary to a named higher-priority issue and concession accepted.
- 5 = issue explicitly included in actor's own formal demand set or actor's own declared action/decision/settlement set.
- 8 = consequential action/refusal/settlement/participation/continuation explicitly conditioned on resolution of this specific issue.
- 10 = issue explicitly non-negotiable and relevant settlement/option refused without it.

### Reactive-actor rule

A mention, rebuttal, rejection, or statement that the opponent's demand is unfounded does **not by itself** satisfy KVS=5. For KVS=5 there must additionally be an explicit link to KBM's own action, decision, settlement, resource allocation or policy criterion concerning pay. A condition about the labour dispute as a whole does not automatically establish pay-specific KVS=8.

Do not infer KVS from strike duration, headcount, production loss, sanctions, media repetition or intensity.

## Admission checks

For each factor give C1-C8:
- C1 exact narrow actor/PTN/reference/temporal identity;
- C2 evidence traceable to this frozen input;
- C3 pre-cutoff historical content authentication;
- C4 decisive predicate attributable to KBM;
- C5 exactly one licensed anchor predicate fully satisfied;
- C6 provenance/dependency/limitations considered;
- C7 fixed PTN/reference/non-simultaneous mapping respected, no carry-forward;
- C8 independent-run protocol respected.

NUMERIC requires all C1-C8 true. If no one anchor is fully satisfied, return `UNKNOWN` with `value=null` and at least one failed gate. If admitted evidence is genuinely incompatible for the same factor, return `DISPUTED/null`.

Allowed POS values: -10, -5, 0, 5, 10.  
Allowed KVS values: 0, 2, 5, 8, 10.  
`UNKNOWN != 0`.

## Required output

Use this exact top-level structure:

```json
{
  "route_id": "AI_ONLY_DYAD_KBM_E02_V100",
  "contract_version": "1.0.0",
  "rubric_version": "2.1.0",
  "input_sha256": "d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42",
  "coder_role": "KBM_COMPANY_E02_V100_AI2",
  "actual_model_label": "<actual model>",
  "model_label_source": "<how model identity is known>",
  "run_id": "<unique run id>",
  "completed_at_utc": "<UTC timestamp>",
  "attestation": {
    "other_coder_output_seen": false,
    "prior_episode_outputs_seen": false,
    "outcome_used_as_evidence": false,
    "external_sources_used": false
  },
  "entries": [
    {
      "actor_id": "KBM_MANAGEMENT_FORMAL_RESPONSE_20110527",
      "factor": "POS_AO2",
      "status": "NUMERIC|UNKNOWN|DISPUTED",
      "value": null,
      "admission_checks": {"C1":false,"C2":false,"C3":false,"C4":false,"C5":false,"C6":false,"C7":false,"C8":false},
      "evidence_references": ["KBM_NOMAD_PRESS_RESPONSE_20110527"],
      "rationale": "<reason>",
      "confidence": {
        "kind": "QUALITATIVE_UNCALIBRATED",
        "value": "HIGH|MEDIUM|LOW|UNKNOWN",
        "meaning": "CONFIDENCE_IN_RECORDED_CODING_DECISION",
        "rationale": "<reason>"
      },
      "calculation_release": false
    },
    {
      "actor_id": "KBM_MANAGEMENT_FORMAL_RESPONSE_20110527",
      "factor": "KVS_AO2",
      "status": "NUMERIC|UNKNOWN|DISPUTED",
      "value": null,
      "admission_checks": {"C1":false,"C2":false,"C3":false,"C4":false,"C5":false,"C6":false,"C7":false,"C8":false},
      "evidence_references": ["KBM_NOMAD_PRESS_RESPONSE_20110527"],
      "rationale": "<reason>",
      "confidence": {
        "kind": "QUALITATIVE_UNCALIBRATED",
        "value": "HIGH|MEDIUM|LOW|UNKNOWN",
        "meaning": "CONFIDENCE_IN_RECORDED_CODING_DECISION",
        "rationale": "<reason>"
      },
      "calculation_release": false
    }
  ]
}
```

Do not compute RGU, KVPTN, Pol or UNO.
