#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

PASS_STATE="AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS"
HOLD_STATE="AI_ONLY_RESEARCH_BETA_RC_HOLD"
REQUIRED_LABEL="AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена."
GATES=("G1","G2","G3","G4","G5","G6","G7","G8")

def load(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def evaluate(inp):
    details={}
    details["G1"]="PASS" if inp.get("cohort_fixed") is True and inp.get("new_lane_after_results") is False and inp.get("all_four_lanes_reported") is True else "FAIL"
    roles=inp.get("primary_roles",{})
    details["G2"]="PASS" if isinstance(roles,dict) and len(roles)==8 and all(v=="VALID" for v in roles.values()) else "FAIL"
    details["G3"]="PASS" if inp.get("input_provenance_integrity")=="PASS" and inp.get("post_result_rebinding") is False else "FAIL"
    details["G4"]="PASS" if inp.get("all_lane_comparators_executed") is True and inp.get("coordinator_substitution_used") is False and inp.get("targeted_content_review_used") is False and inp.get("all_lane_outcomes_retained") is True else "FAIL"
    details["G5"]="PASS" if inp.get("cohort_aggregator_test")=="PASS" and inp.get("cohort_aggregate_schema")=="PASS" and inp.get("denominator_rule_preserved") is True else "FAIL"
    details["G6"]="PASS" if inp.get("weight_grid_unchanged") is True and inp.get("weight_runner_test")=="PASS" and inp.get("weights_inferred_from_evidence_or_outcome") is False else "FAIL"

    eligible=inp.get("eligible_lanes",[])
    replay=inp.get("eligible_lane_core_replay",{})
    if not eligible:
        details["G7"]="PASS_NOT_TRIGGERED"
    else:
        ok=isinstance(replay,dict) and set(replay)==set(eligible) and all(v=="PASS" for v in replay.values())
        details["G7"]="PASS" if ok else "FAIL"

    claims=inp.get("claims",{})
    claims_ok=(
        inp.get("required_label")==REQUIRED_LABEL
        and claims.get("historical_snapshot")=="NOT_ESTABLISHED"
        and claims.get("historical_area_UNO") in {"NOT_COMPUTED","BLOCKED"}
        and claims.get("human_validation")=="NOT_PERFORMED"
        and claims.get("human_reliability") in {"NOT_MEASURED","NOT_PERFORMED"}
        and claims.get("predictive_probability_risk_validation") in {"NOT_CLAIMED","BLOCKED_NOT_CLAIMED"}
    )
    details["G8"]="PASS" if claims_ok else "FAIL"

    passable=all(details[g]=="PASS" for g in ("G1","G2","G3","G4","G5","G6","G8")) and details["G7"] in {"PASS","PASS_NOT_TRIGGERED"}
    return {
      "gate_id":"AI_ONLY_RESEARCH_BETA_V1_RELEASE_GATE_R1",
      "state":PASS_STATE if passable else HOLD_STATE,
      "gates":details,
      "eligible_lanes":eligible,
      "separate_release_states":{
        "external_substantive_historical_measurement":"HOLD",
        "historical_area_UNO":"BLOCKED",
        "human_validated_scientific_release":"NOT_PERFORMED",
        "predictive_probability_risk_validation":"BLOCKED_NOT_CLAIMED"
      }
    }

def base_input():
    return {
      "cohort_fixed":True,
      "new_lane_after_results":False,
      "all_four_lanes_reported":True,
      "primary_roles":{f"R{i}":"VALID" for i in range(8)},
      "input_provenance_integrity":"PASS",
      "post_result_rebinding":False,
      "all_lane_comparators_executed":True,
      "coordinator_substitution_used":False,
      "targeted_content_review_used":False,
      "all_lane_outcomes_retained":True,
      "cohort_aggregator_test":"PASS",
      "cohort_aggregate_schema":"PASS",
      "denominator_rule_preserved":True,
      "weight_grid_unchanged":True,
      "weight_runner_test":"PASS",
      "weights_inferred_from_evidence_or_outcome":False,
      "eligible_lanes":[],
      "eligible_lane_core_replay":{},
      "required_label":REQUIRED_LABEL,
      "claims":{
        "historical_snapshot":"NOT_ESTABLISHED",
        "historical_area_UNO":"NOT_COMPUTED",
        "human_validation":"NOT_PERFORMED",
        "human_reliability":"NOT_PERFORMED",
        "predictive_probability_risk_validation":"NOT_CLAIMED"
      }
    }

def self_test():
    n=0
    x=base_input(); assert evaluate(x)["state"]==PASS_STATE and evaluate(x)["gates"]["G7"]=="PASS_NOT_TRIGGERED"; n+=1
    x=base_input(); x["eligible_lanes"]=["L1"]; x["eligible_lane_core_replay"]={"L1":"PASS"}; assert evaluate(x)["state"]==PASS_STATE; n+=1
    x=base_input(); x["primary_roles"]["R7"]="MISSING"; assert evaluate(x)["state"]==HOLD_STATE and evaluate(x)["gates"]["G2"]=="FAIL"; n+=1
    x=base_input(); x["eligible_lanes"]=["L1"]; x["eligible_lane_core_replay"]={"L1":"MISMATCH"}; assert evaluate(x)["state"]==HOLD_STATE; n+=1
    x=base_input(); x["coordinator_substitution_used"]=True; assert evaluate(x)["state"]==HOLD_STATE; n+=1
    x=base_input(); x["required_label"]=""; assert evaluate(x)["state"]==HOLD_STATE; n+=1
    return {"self_test":"PASS","cases":n}

def main():
    p=argparse.ArgumentParser();p.add_argument("--input");p.add_argument("--out");p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test:
        print(json.dumps(self_test(),ensure_ascii=False));return
    if not(a.input and a.out):p.error("--input and --out required")
    result=evaluate(load(a.input))
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":result["state"]},ensure_ascii=False))
if __name__=="__main__":main()
