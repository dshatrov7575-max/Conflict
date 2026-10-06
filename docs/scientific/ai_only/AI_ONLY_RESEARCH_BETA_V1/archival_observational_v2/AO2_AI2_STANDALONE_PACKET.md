# MVP7 AO2_AI2 — AI_ARCHIVAL_OBSERVATIONAL_V2 PRIMARY

Requested model/interface: Claude — strongest available Opus model; record exact actual label. Record the exact actual model label; do not relabel it.

You are an AI archival coder, not a human. Work only from this standalone packet. Do not use previous AI/VH answers, the other coder output, HUMAN responses, external web/search, or known conflict outcome. Background training knowledge must not be used as evidence.

Return one JSON object only. Code all 6 items × both factors = exactly 12 entries. Allowed status NUMERIC / UNKNOWN / DISPUTED. Do not code RGU/KVPTN and do not compute UNO.

# AI_ARCHIVAL_OBSERVATIONAL_V2 — RUBRIC 2.0.0-draft1

Status: FROZEN_BEFORE_PRIMARY_RESPONSES. Separate from strict-v1 POS/KVS. Strict-v1 UNKNOWN records are not overwritten.

## General
Unit = narrow evidence-supported actor × projected PTN identity × exact reference statement × admitted historical episode. Only the frozen evidence set may be used. Do not use known outcome, external search, prior AI answers, broad GU assumptions, source frequency, emotional tone, or analyst intuition. UNKNOWN != 0. No interpolation.

## POS-AO2 anchors
- -10: admitted actor evidence explicitly rejects the reference as a whole, or explicitly demands reversal/change across all essential components covered by the reference.
- -5: admitted actor evidence explicitly demands change to at least one essential component of the reference, while whole-reference rejection is not established.
- 0: actor explicitly states no directional preference toward the reference.
- +5: admitted actor evidence explicitly defends/preserves at least one essential status-quo component of the reference or explicitly rejects the corresponding change, while whole-reference acceptance is not established.
- +10: actor explicitly defends the reference as a whole and rejects substantial change across its essential components.

A demand for a pay rise is directional negative evidence for the pay component but does not by itself justify -10. A company claim that employees are fairly compensated is directional positive evidence for the pay component but does not by itself justify +10.

## KVS-AO2 anchors
This is archival decision salience, not absolute psychological importance.
- 0: actor explicitly says the issue is irrelevant/not a decision criterion.
- 2: actor explicitly calls the issue secondary to a named higher-priority issue and accepts concession on it.
- 5: the issue is explicitly included in a collective/formal demand or decision set attributable to the actor, but leading rank/settlement conditionality is not established.
- 8: actor explicitly conditions continuation, refusal, settlement, participation, or another consequential decision on resolution of this specific issue.
- 10: actor explicitly makes the specific issue non-negotiable and refuses the relevant settlement/option without it.

Do not infer KVS from strike duration, headcount, production loss, punishment severity, repeated media coverage, or persistence alone. A multi-issue decision condition cannot automatically be assigned as KVS=8 to each component unless the source makes the specific component condition explicit.

## Admission gates
A1 exact narrow actor/PTN/reference/episode identity; A2 traceable text/context; A3 pre-cutoff content proof; A4 attribution to narrow actor; A5 exactly one AO2 anchor predicate; A6 provenance/dependency reviewed; A7 fixed mapping; A8 fixed independent AI-run protocol. NUMERIC requires all A1-A8 true. Otherwise UNKNOWN/null. Incompatible admitted evidence for the same unit => DISPUTED/null.

## Output semantics
These are PROVISIONAL AI-coded archival measurements. They are not HUMAN validation, strict-v1 validation, probability, prediction, or historical truth. RGU/KVPTN remain exogenous analytic weights.

# FROZEN EVIDENCE SET
{
  "route_id": "AI_ARCHIVAL_OBSERVATIONAL_V2",
  "status": "FROZEN_EVIDENCE_SET_R1",
  "admission_rule": "Only pre-cutoff authenticated/corroborated content included. Current-only D07/D15/D17/D19/D20/D21/D23/D24/D29 excluded.",
  "records": [
    {
      "evidence_id": "C03-CACI-20110817",
      "date": "2011-08-11",
      "historical_witness_date": "2011-08-17",
      "source": "Central Asia-Caucasus Analyst News Digest reproducing RFE/RL",
      "actor_scope": "OzenMunaiGaz workers",
      "content": [
        "Named OzenMunaiGaz worker reports nearly 3,000 workers filed to quit Nur-Otan.",
        "Workers said strike demands had not been met and linked that to the decision to quit.",
        "Demand set includes pay increase, equal rights with foreign workers, independent-union freedom, and release of Natalya Sokolova."
      ],
      "exact_short_snippets": [
        "nearly 3,000 workers",
        "none of their strike demands have been met",
        "a pay raise",
        "no restrictions on independent labor unions"
      ],
      "witness_locator": "Central Asia-Caucasus Analyst, 17 Aug 2011, p.23, News Digest, 11 August item",
      "witness_url": "https://www.cacianalyst.org/resources/pdf/issues/20110817Analyst.pdf",
      "status": "PRE_CUTOFF_CONTENT_CORROBORATED"
    },
    {
      "evidence_id": "D13-F56",
      "date": "2011-09-18",
      "source_label": "D13",
      "fragment_id": "56d19d98-707a-5deb-9472-d355b3835d79",
      "exact_text": "demanding payment of unfulfilled wage hikes and better labor conditions",
      "actor_scope": "Named OzenMunaiGaz driver in recovered historical context; individual corroboration only",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    },
    {
      "evidence_id": "D03-FCC",
      "date": "2011-05-27",
      "source_label": "D03",
      "fragment_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
      "exact_text": "demanding the revision of the collective contract",
      "actor_scope": "OzenMunaiGaz employees in recovered historical context; press-secretary report, not direct collective declaration",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    },
    {
      "evidence_id": "D01-FPAY",
      "date": "2011-05-21",
      "source_label": "D01",
      "fragment_id": "d3e6a365-8150-545b-8005-c18c4939142b",
      "exact_text": "strikers are demanding a pay rise",
      "actor_scope": "Qarazhanbas strike context recovered; statement relayed by regional union lawyer",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    },
    {
      "evidence_id": "D04-FUNION",
      "date": "2011-05-29",
      "source_label": "D04",
      "fragment_id": "7f0b0752-387d-5def-ba3d-ab11c4f1414b",
      "exact_text": "lifting of restrictions on the activities of independent trade unions",
      "actor_scope": "QarazhanbasMunai strike context recovered; no contractor inference",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    },
    {
      "evidence_id": "D25-FREINSTATE",
      "date": "2011-10-13",
      "source_label": "D25",
      "fragment_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
      "exact_text": "demanding reinstatement and a review of salaries",
      "actor_scope": "Dismissed workers explicitly described by the admitted archived D25 source",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    },
    {
      "evidence_id": "D25-FFAIR",
      "date": "2011-10-13",
      "source_label": "D25",
      "fragment_id": "3ca46849-549e-544d-b72c-d62ef1706612",
      "exact_text": "company insists that its employees are fairly compensated",
      "actor_scope": "KMG EP company position only",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    },
    {
      "evidence_id": "D25-FRAISES",
      "date": "2011-10-13",
      "source_label": "D25",
      "fragment_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
      "exact_text": "has raised salaries six times since 2008",
      "actor_scope": "KMG EP company position only",
      "status": "AUTHENTICATED_PRE_CUTOFF_WITNESS"
    }
  ]
}

# ITEM ORDER FOR AO2_AI2
[
  {
    "item_id": "AO2-04",
    "actor_key": "AOV2_KBM_STRIKERS",
    "actor_name": "Workers explicitly identified with QarazhanbasMunai in admitted pre-cutoff material",
    "ptn_id": "728c8406-ba99-5787-9557-933b5670be7c",
    "element_code": "E05",
    "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов.",
    "evidence_ids": [
      "D04-FUNION"
    ],
    "scope_note": "Company-specific worker actor only."
  },
  {
    "item_id": "AO2-01",
    "actor_key": "AOV2_OMG_STRIKERS",
    "actor_name": "Workers explicitly identified with OzenMunaiGaz in admitted pre-cutoff material",
    "ptn_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
    "element_code": "E02",
    "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.",
    "evidence_ids": [
      "C03-CACI-20110817",
      "D13-F56"
    ],
    "scope_note": "No extrapolation to all GU01 or other companies."
  },
  {
    "item_id": "AO2-06",
    "actor_key": "AOV2_KMG_EP_MANAGEMENT",
    "actor_name": "KMG EP management/company position as explicitly attributed in admitted D25 material",
    "ptn_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
    "element_code": "E02",
    "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.",
    "evidence_ids": [
      "D25-FFAIR",
      "D25-FRAISES"
    ],
    "scope_note": "Company position only; not all GU05/employers."
  },
  {
    "item_id": "AO2-03",
    "actor_key": "AOV2_KBM_STRIKERS",
    "actor_name": "Workers explicitly identified with QarazhanbasMunai in admitted pre-cutoff material",
    "ptn_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
    "element_code": "E02",
    "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.",
    "evidence_ids": [
      "D01-FPAY"
    ],
    "scope_note": "Company-specific worker actor only."
  },
  {
    "item_id": "AO2-02",
    "actor_key": "AOV2_OMG_STRIKERS",
    "actor_name": "Workers explicitly identified with OzenMunaiGaz in admitted pre-cutoff material",
    "ptn_id": "728c8406-ba99-5787-9557-933b5670be7c",
    "element_code": "E05",
    "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов.",
    "evidence_ids": [
      "C03-CACI-20110817",
      "D03-FCC"
    ],
    "scope_note": "No extrapolation to all workers or contractors."
  },
  {
    "item_id": "AO2-05",
    "actor_key": "AOV2_DISMISSED_KMG_EP_WORKERS_D25",
    "actor_name": "Dismissed workers explicitly described in the admitted D25 source",
    "ptn_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
    "element_code": "E02",
    "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения.",
    "evidence_ids": [
      "D25-FREINSTATE"
    ],
    "scope_note": "Only the dismissed-worker group explicitly described in D25; not all GU03/job seekers."
  }
]

# OUTPUT TEMPLATE
{
  "route_id": "AI_ARCHIVAL_OBSERVATIONAL_V2",
  "rubric_version": "2.0.0-draft1",
  "coder_role": "AO2_AI2",
  "actual_model_label": null,
  "run_id": null,
  "completed_at_utc": null,
  "attestation": {
    "other_coder_output_seen": null,
    "prior_ao2_outputs_seen": null,
    "outcome_used_as_evidence": null,
    "external_sources_used": null
  },
  "entries": [
    {
      "item_id": "AO2-01",
      "factor": "POS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-01",
      "factor": "KVS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-02",
      "factor": "POS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-02",
      "factor": "KVS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-03",
      "factor": "POS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-03",
      "factor": "KVS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-04",
      "factor": "POS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-04",
      "factor": "KVS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-05",
      "factor": "POS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-05",
      "factor": "KVS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-06",
      "factor": "POS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    },
    {
      "item_id": "AO2-06",
      "factor": "KVS_AO2",
      "status": null,
      "value": null,
      "admission_checks": {
        "A1": null,
        "A2": null,
        "A3": null,
        "A4": null,
        "A5": null,
        "A6": null,
        "A7": null,
        "A8": null
      },
      "evidence_ids": [],
      "rationale": null,
      "confidence": null
    }
  ]
}
