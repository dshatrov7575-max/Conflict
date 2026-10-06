#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

COHORT_ID="AI_ONLY_REPLICATION_COHORT_R1_20260930"
LANES={
 "KBM_E02":{"route_id":"AI_ONLY_DYAD_KBM_E02_V100","input_sha256":"d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42","expected_decisions":2,"container":"company_entries"},
 "OMG_NOV24":{"route_id":"AI_ONLY_DYAD_OMG_NOV24_V100","input_sha256":"72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4","expected_decisions":4,"container":"entries"},
 "KBM_E05":{"route_id":"AI_ONLY_PAIR_KBM_E05_V100","input_sha256":"51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95","expected_decisions":2,"container":"company_entries"},
 "D25_E02":{"route_id":"AI_ONLY_DYAD_D25_E02_V100","input_sha256":"aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa","expected_decisions":4,"container":"entries"}
}
EXPECTED_TOTAL=12
EXPECTED_BY_FACTOR={"POS_AO2":6,"KVS_AO2":6}
TRIAGE={"CONSENSUS_NUMERIC","SHARED_UNKNOWN","SHARED_DISPUTED","HOLD_DISAGREEMENT"}
ELIGIBLE_PREFIX="ELIGIBLE_FOR_READ_ONLY_"

def load(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def frac(n,d): return f"{n/d:.8f}"

def validate_lane(obj,spec):
    if obj.get("route_id")!=spec["route_id"]: raise ValueError("route mismatch")
    if obj.get("input_sha256")!=spec["input_sha256"]: raise ValueError("input hash mismatch")
    state=obj.get("state")
    if state=="REJECT_INVALID_PRIMARY_RUN":
        return state,[]
    rows=obj.get(spec["container"])
    if not isinstance(rows,list) or len(rows)!=spec["expected_decisions"]:
        raise ValueError("decision count mismatch")
    seen=set()
    for r in rows:
        f=r.get("factor")
        if f not in {"POS_AO2","KVS_AO2"}: raise ValueError("factor mismatch")
        key=(r.get("actor_id","COMPANY"),f)
        if key in seen: raise ValueError("duplicate decision")
        seen.add(key)
        if r.get("triage") not in TRIAGE: raise ValueError("triage mismatch")
    return state,rows

def aggregate(paths):
    counts={"CONSENSUS_NUMERIC":0,"SHARED_UNKNOWN":0,"SHARED_DISPUTED":0,"HOLD_DISAGREEMENT":0,"UNRESOLVED":0}
    by_factor={f:{k:0 for k in counts} for f in EXPECTED_BY_FACTOR}
    lane_states={}
    eligible=[]
    observed=0
    for key,spec in LANES.items():
        p=paths.get(key)
        if not p:
            lane_states[spec["route_id"]]="MISSING_PRIMARY_PAIR"
            counts["UNRESOLVED"]+=spec["expected_decisions"]
            missing_each=spec["expected_decisions"]//2
            for f in by_factor: by_factor[f]["UNRESOLVED"]+=missing_each
            continue
        obj=load(p)
        try:
            state,rows=validate_lane(obj,spec)
        except Exception as exc:
            lane_states[spec["route_id"]]="REJECT_INVALID_COMPARISON_ARTIFACT"
            counts["UNRESOLVED"]+=spec["expected_decisions"]
            missing_each=spec["expected_decisions"]//2
            for f in by_factor: by_factor[f]["UNRESOLVED"]+=missing_each
            continue
        lane_states[spec["route_id"]]=state
        if state=="REJECT_INVALID_PRIMARY_RUN":
            counts["UNRESOLVED"]+=spec["expected_decisions"]
            missing_each=spec["expected_decisions"]//2
            for f in by_factor: by_factor[f]["UNRESOLVED"]+=missing_each
            continue
        observed+=len(rows)
        for r in rows:
            t=r["triage"]; f=r["factor"]; counts[t]+=1; by_factor[f][t]+=1
        if isinstance(state,str) and state.startswith(ELIGIBLE_PREFIX):
            eligible.append(spec["route_id"])
    exact=counts["CONSENSUS_NUMERIC"]+counts["SHARED_UNKNOWN"]+counts["SHARED_DISPUTED"]
    result={
      "cohort_id":COHORT_ID,
      "state":"COMPLETE" if observed==EXPECTED_TOTAL and counts["UNRESOLVED"]==0 else "PARTIAL",
      "expected_lanes":4,
      "expected_decisions":EXPECTED_TOTAL,
      "observed_decisions":observed,
      "overall":{
        "exact_agreement_count":exact,
        "exact_agreement_fraction_expected_denominator":frac(exact,EXPECTED_TOTAL),
        "numeric_consensus_count":counts["CONSENSUS_NUMERIC"],
        "numeric_consensus_fraction_expected_denominator":frac(counts["CONSENSUS_NUMERIC"],EXPECTED_TOTAL),
        "shared_unknown_count":counts["SHARED_UNKNOWN"],
        "shared_unknown_fraction_expected_denominator":frac(counts["SHARED_UNKNOWN"],EXPECTED_TOTAL),
        "shared_disputed_count":counts["SHARED_DISPUTED"],
        "shared_disputed_fraction_expected_denominator":frac(counts["SHARED_DISPUTED"],EXPECTED_TOTAL),
        "disagreement_count":counts["HOLD_DISAGREEMENT"],
        "disagreement_fraction_expected_denominator":frac(counts["HOLD_DISAGREEMENT"],EXPECTED_TOTAL),
        "unresolved_count":counts["UNRESOLVED"],
        "unresolved_fraction_expected_denominator":frac(counts["UNRESOLVED"],EXPECTED_TOTAL)
      },
      "by_factor":{},
      "lane_states":lane_states,
      "eligible_replay_lanes":eligible,
      "claims":{
        "representative_sample":False,
        "population_inference":False,
        "human_validation":"NOT_PERFORMED",
        "historical_area_UNO":"NOT_COMPUTED",
        "fraction_denominator":"FROZEN_EXPECTED_DECISIONS"
      }
    }
    for f,d in by_factor.items():
        ex=d["CONSENSUS_NUMERIC"]+d["SHARED_UNKNOWN"]+d["SHARED_DISPUTED"]; den=EXPECTED_BY_FACTOR[f]
        result["by_factor"][f]={
          "expected":den,
          "exact_agreement_count":ex,
          "exact_agreement_fraction":frac(ex,den),
          "numeric_consensus_count":d["CONSENSUS_NUMERIC"],
          "shared_unknown_count":d["SHARED_UNKNOWN"],
          "shared_disputed_count":d["SHARED_DISPUTED"],
          "disagreement_count":d["HOLD_DISAGREEMENT"],
          "unresolved_count":d["UNRESOLVED"]
        }
    return result

def synthetic(spec,state="ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY",triages=None):
    triages=triages or ["CONSENSUS_NUMERIC"]*spec["expected_decisions"]; rows=[]
    actors=["A","B"] if spec["expected_decisions"]==4 else ["COMPANY"]
    i=0
    for a in actors:
        for f in ("POS_AO2","KVS_AO2"):
            rows.append({"actor_id":a,"factor":f,"triage":triages[i]});i+=1
    return {"route_id":spec["route_id"],"input_sha256":spec["input_sha256"],"state":state,spec["container"]:rows}

def self_test(tmp):
    cases=0; paths={}
    for k,s in LANES.items():
        p=Path(tmp)/f"{k}.json"; p.write_text(json.dumps(synthetic(s)),encoding="utf-8"); paths[k]=str(p)
    out=aggregate(paths); assert out["state"]=="COMPLETE" and out["overall"]["exact_agreement_count"]==12 and out["overall"]["numeric_consensus_count"]==12; cases+=1
    p=Path(paths["D25_E02"]); o=json.loads(p.read_text()); o["entries"][0]["triage"]="HOLD_DISAGREEMENT"; p.write_text(json.dumps(o)); out=aggregate(paths); assert out["overall"]["disagreement_count"]==1 and out["overall"]["exact_agreement_count"]==11; cases+=1
    p=Path(paths["KBM_E02"]); o=json.loads(p.read_text()); o["company_entries"][1]["triage"]="SHARED_UNKNOWN"; p.write_text(json.dumps(o)); out=aggregate(paths); assert out["overall"]["shared_unknown_count"]==1 and out["overall"]["exact_agreement_count"]==11; cases+=1
    missing=dict(paths); missing.pop("OMG_NOV24"); out=aggregate(missing); assert out["state"]=="PARTIAL" and out["overall"]["unresolved_count"]==4 and out["observed_decisions"]==8; cases+=1
    bad=Path(paths["KBM_E05"]); o=json.loads(bad.read_text()); o["input_sha256"]="0"*64; bad.write_text(json.dumps(o)); out=aggregate(paths); assert out["overall"]["unresolved_count"]==2; cases+=1
    return {"self_test":"PASS","cases":cases}

def main():
    p=argparse.ArgumentParser()
    for k in LANES: p.add_argument("--"+k.lower().replace("_","-"))
    p.add_argument("--out"); p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    import tempfile
    if a.self_test:
        with tempfile.TemporaryDirectory() as t: print(json.dumps(self_test(t))); return
    paths={"KBM_E02":a.kbm_e02,"OMG_NOV24":a.omg_nov24,"KBM_E05":a.kbm_e05,"D25_E02":a.d25_e02}
    result=aggregate(paths)
    if not a.out: p.error("--out required")
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":result["state"],"observed_decisions":result["observed_decisions"]}))
if __name__=="__main__": main()
