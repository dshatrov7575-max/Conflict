#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

ROUTE_ID="AI_ONLY_DYAD_D25_E02_V100"
CONTRACT_VERSION="1.0.0"
RUBRIC_VERSION="2.1.0"
INPUT_SHA256="aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa"
ROLES=("D25_E02_V100_AI1","D25_E02_V100_AI2")
ACTORS=("D25_DISMISSED_KMG_EP_WORKERS_20111013","D25_KMG_EP_MANAGEMENT_20111013")
FACTORS=("POS_AO2","KVS_AO2")
GATES=tuple(f"C{i}" for i in range(1,9))
STATUSES={"NUMERIC","UNKNOWN","DISPUTED"}
POS_VALUES={-10,-5,0,5,10}
KVS_VALUES={0,2,5,8,10}
ATTESTATIONS=("other_coder_output_seen","prior_episode_outputs_seen","prior_r2_outputs_seen","outcome_used_as_evidence","external_sources_used")

def load(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def validate(run:dict[str,Any],role:str):
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
    if not isinstance(entries,list) or len(entries)!=4: raise ValueError("exactly four entries required")
    out={}
    for e in entries:
        actor=e.get("actor_id"); factor=e.get("factor"); key=(actor,factor)
        if actor not in ACTORS or factor not in FACTORS or key in out: raise ValueError("actor×factor set mismatch or duplicate")
        st=e.get("status"); val=e.get("value"); checks=e.get("admission_checks")
        if st not in STATUSES: raise ValueError("invalid status")
        if not isinstance(checks,dict) or set(checks)!=set(GATES): raise ValueError("C1-C8 set mismatch")
        if any(type(checks[g]) is not bool for g in GATES): raise ValueError("C1-C8 values must be booleans")
        if e.get("calculation_release") is not False: raise ValueError("primary calculation_release must be false")
        if st=="NUMERIC":
            allowed=POS_VALUES if factor=="POS_AO2" else KVS_VALUES
            if val not in allowed: raise ValueError("unlicensed numeric anchor")
            if not all(checks[g] for g in GATES): raise ValueError("NUMERIC with failed gate")
        elif st=="UNKNOWN":
            if val is not None: raise ValueError("UNKNOWN value must be null")
            if all(checks[g] for g in GATES): raise ValueError("UNKNOWN must expose at least one failed gate")
        else:
            if val is not None: raise ValueError("DISPUTED value must be null")
        out[key]=e
    if set(out)!={(a,f) for a in ACTORS for f in FACTORS}: raise ValueError("actor×factor set incomplete")
    return out

def triage(a,b):
    same=a["status"]==b["status"] and a.get("value")==b.get("value") and a["admission_checks"]==b["admission_checks"]
    if not same: return "HOLD_DISAGREEMENT"
    return "CONSENSUS_NUMERIC" if a["status"]=="NUMERIC" else ("SHARED_UNKNOWN" if a["status"]=="UNKNOWN" else "SHARED_DISPUTED")

def compare(ai1,ai2):
    if ai1.get("run_id")==ai2.get("run_id"): raise ValueError("run_id must differ")
    l=validate(ai1,ROLES[0]); r=validate(ai2,ROLES[1]); rows=[]
    for actor in ACTORS:
        for factor in FACTORS:
            a,b=l[(actor,factor)],r[(actor,factor)]
            rows.append({"actor_id":actor,"factor":factor,"ai1_status":a["status"],"ai1_value":a.get("value"),"ai2_status":b["status"],"ai2_value":b.get("value"),"same_C1_C8":a["admission_checks"]==b["admission_checks"],"triage":triage(a,b)})
    ts=[x["triage"] for x in rows]
    if "HOLD_DISAGREEMENT" in ts: state="HOLD_DISAGREEMENT"
    elif any(x in {"SHARED_UNKNOWN","SHARED_DISPUTED"} for x in ts): state="HOLD_FACTOR_INCOMPLETE"
    else: state="ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY"
    return {"route_id":ROUTE_ID,"contract_version":CONTRACT_VERSION,"input_sha256":INPUT_SHA256,"state":state,"entries":rows,"coordinator_substitution":"FORBIDDEN","targeted_content_review_rounds":0,"calculation_release":state=="ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY","simultaneous_snapshot":False,"carry_forward":"NONE","historical_snapshot":"NOT_ESTABLISHED","historical_area_UNO":"NOT_COMPUTED","human_validation":"NOT_PERFORMED"}

def sample(role,overrides=None):
    overrides=overrides or {}; entries=[]
    for actor in ACTORS:
        for factor in FACTORS:
            st,val,failed=overrides.get((actor,factor),("NUMERIC",5,()))
            checks={g:g not in set(failed) for g in GATES}
            entries.append({"actor_id":actor,"factor":factor,"status":st,"value":val,"admission_checks":checks,"evidence_references":["D25_EURASIANET_20111013"],"rationale":"synthetic","confidence":{"kind":"QUALITATIVE_UNCALIBRATED","value":"HIGH","meaning":"CONFIDENCE_IN_RECORDED_CODING_DECISION","rationale":"synthetic"},"calculation_release":False})
    return {"route_id":ROUTE_ID,"contract_version":CONTRACT_VERSION,"rubric_version":RUBRIC_VERSION,"input_sha256":INPUT_SHA256,"coder_role":role,"actual_model_label":"SYNTHETIC","model_label_source":"SELF_TEST","run_id":role+"-run","completed_at_utc":"2026-09-30T00:00:00Z","attestation":{k:False for k in ATTESTATIONS},"entries":entries}

def self_test():
    n=0
    assert compare(sample(ROLES[0]),sample(ROLES[1]))["state"]=="ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY"; n+=1
    key=(ACTORS[0],"POS_AO2"); ov={key:("UNKNOWN",None,("C5",))}
    assert compare(sample(ROLES[0],ov),sample(ROLES[1],ov))["state"]=="HOLD_FACTOR_INCOMPLETE"; n+=1
    assert compare(sample(ROLES[0]),sample(ROLES[1],ov))["state"]=="HOLD_DISAGREEMENT"; n+=1
    b=sample(ROLES[1]); b["entries"][0]["value"]=10
    assert compare(sample(ROLES[0]),b)["state"]=="HOLD_DISAGREEMENT"; n+=1
    bad=sample(ROLES[0]); bad["attestation"]["prior_r2_outputs_seen"]=True
    try: validate(bad,ROLES[0])
    except ValueError: n+=1
    else: raise AssertionError
    bad=sample(ROLES[0]); bad["entries"][0]["admission_checks"]["C5"]=False
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
    p=argparse.ArgumentParser(); p.add_argument("--ai1");p.add_argument("--ai2");p.add_argument("--out");p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test: print(json.dumps(self_test())); return
    if not(a.ai1 and a.ai2 and a.out): p.error("--ai1, --ai2 and --out are required")
    result=compare(load(a.ai1),load(a.ai2)); Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"state":result["state"],"entries":len(result["entries"])}))
if __name__=="__main__": main()
