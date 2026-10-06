#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

ROUTE_ID="AI_ONLY_PAIR_KBM_E05_V100"
CONTRACT_VERSION="1.0.0"
RUBRIC_VERSION="2.1.0"
INPUT_SHA256="51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95"
ACTOR_ID="KBM_MANAGEMENT_REPRESENTATION_STANCE_20110514"
ROLES=("KBM_E05_V100_AI1","KBM_E05_V100_AI2")
FACTORS=("POS_AO2","KVS_AO2")
GATES=tuple(f"C{i}" for i in range(1,9))
STATUSES={"NUMERIC","UNKNOWN","DISPUTED"}
POS_VALUES={-10,-5,0,5,10}
KVS_VALUES={0,2,5,8,10}
ATTESTATIONS=("other_coder_output_seen","prior_episode_outputs_seen","outcome_used_as_evidence","external_sources_used")

def load(path:str|Path)->dict[str,Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def validate(run:dict[str,Any], role:str)->dict[str,dict[str,Any]]:
    if run.get("route_id")!=ROUTE_ID: raise ValueError("route_id mismatch")
    if run.get("contract_version")!=CONTRACT_VERSION: raise ValueError("contract_version mismatch")
    if run.get("rubric_version")!=RUBRIC_VERSION: raise ValueError("rubric_version mismatch")
    if run.get("input_sha256")!=INPUT_SHA256: raise ValueError("input_sha256 mismatch")
    if run.get("coder_role")!=role: raise ValueError("coder_role mismatch")
    if not isinstance(run.get("run_id"),str) or not run["run_id"].strip(): raise ValueError("run_id missing")
    att=run.get("attestation")
    if not isinstance(att,dict): raise ValueError("attestation missing")
    for k in ATTESTATIONS:
        if att.get(k) is not False: raise ValueError(f"ineligible attestation: {k}")
    entries=run.get("entries")
    if not isinstance(entries,list) or len(entries)!=2: raise ValueError("exactly two entries required")
    out={}
    for e in entries:
        f=e.get("factor")
        if f not in FACTORS or f in out: raise ValueError("factor set mismatch or duplicate")
        if e.get("actor_id")!=ACTOR_ID: raise ValueError("actor_id mismatch")
        st=e.get("status"); val=e.get("value"); checks=e.get("admission_checks")
        if st not in STATUSES: raise ValueError("invalid status")
        if not isinstance(checks,dict) or set(checks)!=set(GATES): raise ValueError("C1-C8 set mismatch")
        if any(type(checks[g]) is not bool for g in GATES): raise ValueError("C1-C8 values must be booleans")
        if e.get("calculation_release") is not False: raise ValueError("primary calculation_release must be false")
        if st=="NUMERIC":
            allowed=POS_VALUES if f=="POS_AO2" else KVS_VALUES
            if val not in allowed: raise ValueError("unlicensed numeric anchor")
            if not all(checks[g] for g in GATES): raise ValueError("NUMERIC with failed gate")
        elif st=="UNKNOWN":
            if val is not None: raise ValueError("UNKNOWN value must be null")
            if all(checks[g] for g in GATES): raise ValueError("UNKNOWN must expose at least one failed gate")
        else:
            if val is not None: raise ValueError("DISPUTED value must be null")
        out[f]=e
    if set(out)!=set(FACTORS): raise ValueError("factor set incomplete")
    return out

def triage(a,b):
    same=a["status"]==b["status"] and a.get("value")==b.get("value") and a["admission_checks"]==b["admission_checks"]
    if not same: return "HOLD_DISAGREEMENT"
    return "CONSENSUS_NUMERIC" if a["status"]=="NUMERIC" else ("SHARED_UNKNOWN" if a["status"]=="UNKNOWN" else "SHARED_DISPUTED")

def compare(ai1,ai2):
    if ai1.get("run_id")==ai2.get("run_id"): raise ValueError("run_id must differ")
    l=validate(ai1,ROLES[0]); r=validate(ai2,ROLES[1])
    rows=[]
    for f in FACTORS:
        a,b=l[f],r[f]
        rows.append({"factor":f,"ai1_status":a["status"],"ai1_value":a.get("value"),"ai2_status":b["status"],"ai2_value":b.get("value"),"same_C1_C8":a["admission_checks"]==b["admission_checks"],"triage":triage(a,b)})
    ts=[x["triage"] for x in rows]
    if "HOLD_DISAGREEMENT" in ts: state="HOLD_DISAGREEMENT"
    elif any(x in {"SHARED_UNKNOWN","SHARED_DISPUTED"} for x in ts): state="HOLD_FACTOR_INCOMPLETE"
    else: state="ELIGIBLE_FOR_READ_ONLY_PAIR_SCENARIO_REPLAY"
    return {
      "route_id":ROUTE_ID,"contract_version":CONTRACT_VERSION,"input_sha256":INPUT_SHA256,"state":state,
      "inherited_worker_record":{"unit_id":"AO2S-C1-04","actor_id":"AOV2_KBM_STRIKERS","source_id":"D04-FUNION","source_report_date":"2011-05-27","POS_AO2":-5,"KVS_AO2":5,"status":"INHERITED_TWO_PRIMARY_NUMERIC_AGREEMENT"},
      "company_entries":rows,"coordinator_substitution":"FORBIDDEN","targeted_content_review_rounds":0,
      "calculation_release":state=="ELIGIBLE_FOR_READ_ONLY_PAIR_SCENARIO_REPLAY",
      "simultaneous_snapshot":False,"carry_forward":"NONE","historical_snapshot":"NOT_ESTABLISHED","historical_area_UNO":"NOT_COMPUTED","human_validation":"NOT_PERFORMED"
    }

def sample(role,pos=("NUMERIC",5),kvs=("NUMERIC",5),fail=None):
    fail=fail or {}; entries=[]
    for f,(st,val) in (("POS_AO2",pos),("KVS_AO2",kvs)):
        checks={g:g not in set(fail.get(f,())) for g in GATES}
        entries.append({"actor_id":ACTOR_ID,"factor":f,"status":st,"value":val,"admission_checks":checks,"evidence_references":["AKTAU_BUSINESS_KBM_RELEASE_20110514"],"rationale":"synthetic","confidence":{"kind":"QUALITATIVE_UNCALIBRATED","value":"HIGH","meaning":"CONFIDENCE_IN_RECORDED_CODING_DECISION","rationale":"synthetic"},"calculation_release":False})
    return {"route_id":ROUTE_ID,"contract_version":CONTRACT_VERSION,"rubric_version":RUBRIC_VERSION,"input_sha256":INPUT_SHA256,"coder_role":role,"actual_model_label":"SYNTHETIC","model_label_source":"SELF_TEST","run_id":role+"-run","completed_at_utc":"2026-09-30T00:00:00Z","attestation":{k:False for k in ATTESTATIONS},"entries":entries}

def self_test():
    n=0
    assert compare(sample(ROLES[0]),sample(ROLES[1]))["state"]=="ELIGIBLE_FOR_READ_ONLY_PAIR_SCENARIO_REPLAY"; n+=1
    fail={"KVS_AO2":("C5",)}
    assert compare(sample(ROLES[0],kvs=("UNKNOWN",None),fail=fail),sample(ROLES[1],kvs=("UNKNOWN",None),fail=fail))["state"]=="HOLD_FACTOR_INCOMPLETE"; n+=1
    assert compare(sample(ROLES[0]),sample(ROLES[1],kvs=("UNKNOWN",None),fail=fail))["state"]=="HOLD_DISAGREEMENT"; n+=1
    assert compare(sample(ROLES[0],pos=("NUMERIC",5)),sample(ROLES[1],pos=("NUMERIC",10)))["state"]=="HOLD_DISAGREEMENT"; n+=1
    bad=sample(ROLES[0]); bad["attestation"]["external_sources_used"]=True
    try: validate(bad,ROLES[0])
    except ValueError: n+=1
    else: raise AssertionError
    bad=sample(ROLES[0]); bad["entries"][0]["admission_checks"]["C4"]=False
    try: validate(bad,ROLES[0])
    except ValueError: n+=1
    else: raise AssertionError
    bad=sample(ROLES[0]); bad["entries"].append(dict(bad["entries"][0]))
    try: validate(bad,ROLES[0])
    except ValueError: n+=1
    else: raise AssertionError
    bad=sample(ROLES[0]); bad["entries"][0]["value"]=8
    try: validate(bad,ROLES[0])
    except ValueError: n+=1
    else: raise AssertionError
    return {"self_test":"PASS","cases":n}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--ai1"); p.add_argument("--ai2"); p.add_argument("--out"); p.add_argument("--self-test",action="store_true"); a=p.parse_args()
    if a.self_test: print(json.dumps(self_test())); return
    if not(a.ai1 and a.ai2 and a.out): p.error("--ai1, --ai2 and --out are required")
    result=compare(load(a.ai1),load(a.ai2)); Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"state":result["state"],"entries":len(result["company_entries"])}))
if __name__=="__main__": main()
