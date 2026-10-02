#!/usr/bin/env python3
import argparse, json
from pathlib import Path

ITEMS=["1abf6c8c-5295-5837-b75f-00c55daf3a8c","951f300c-27d0-5a09-b312-e3fdad147f54","bc34ea72-a9ac-5e81-ab20-3f2efb729872","3fba0d88-4c72-5d24-b879-52904c88a0e5","cd9eb952-6af0-5708-8703-49673415cbe7","092a3bde-2c62-5bae-a31d-b5c8751eb201","3f4dc104-40c7-59db-ad5c-61f8a80232bc","2c58ce09-3654-5a87-89be-4b1953f467c7","5e3146aa-0dfd-5be2-8f8d-39b94edee3ff","a6f0883a-d5fc-521b-8662-1c160fded750","d0c7e8eb-6859-55ff-921a-f2e43e8f03d0","79748746-11e6-506c-82d5-bc5fe877beb0"]
POS_VALUES={-10,-5,0,5,10}
KVS_VALUES={0,2,5,8,10}
STATUS={"NUMERIC","UNKNOWN","DISPUTED"}
GATES=("G1","G2","G3","G4","G5","G6","G7")

def load(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def canon_list(x):
    return tuple(sorted(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")) for v in (x or [])))

def validate(r, role):
    if r.get("protocol_id")!="AI_ONLY_RESEARCH_BETA_V1" or r.get("protocol_patch")!="PATCH_1": raise ValueError("bad protocol id/patch")
    if r.get("coder_role")!=role: raise ValueError("bad coder_role")
    if not isinstance(r.get("run_id"),str) or not r["run_id"].strip(): raise ValueError("missing run_id")
    a=r.get("attestation",{})
    for k in ("other_coder_output_seen","prior_factor_outputs_seen","outcome_used_as_evidence"):
        if a.get(k) is not False: raise ValueError("ineligible attestation: "+k)
    es=r.get("entries")
    if not isinstance(es,list) or len(es)!=24: raise ValueError("need exactly 24 entries")
    keys=[(e.get("coding_item_id"),e.get("factor")) for e in es]
    expected={(i,f) for i in ITEMS for f in ("POS","KVS")}
    if len(set(keys))!=24 or set(keys)!=expected: raise ValueError("entry set mismatch/duplicate")
    out={}
    for e in es:
        st=e.get("status"); factor=e.get("factor"); val=e.get("value")
        if st not in STATUS: raise ValueError("bad status")
        checks=e.get("admission_checks")
        if not isinstance(checks,dict) or any(type(checks.get(g)) is not bool for g in GATES): raise ValueError("bad G1-G7")
        if not isinstance(e.get("reason_codes"),list): raise ValueError("reason_codes must list")
        if not isinstance(e.get("evidence_references"),list): raise ValueError("evidence_references must list")
        if not isinstance(e.get("verbatim_evidence"),list): raise ValueError("verbatim_evidence must list")
        if not isinstance(e.get("rationale"),str) or not e["rationale"].strip(): raise ValueError("missing rationale")
        if st=="NUMERIC":
            allowed=POS_VALUES if factor=="POS" else KVS_VALUES
            if val not in allowed: raise ValueError("unlicensed numeric anchor")
            if not all(checks[g] for g in GATES): raise ValueError("NUMERIC with failed gate")
            if not e["evidence_references"] or not e["verbatim_evidence"]: raise ValueError("NUMERIC lacks evidence")
            if not isinstance(e.get("rubric_rule_ref"),str) or not e["rubric_rule_ref"].strip(): raise ValueError("NUMERIC lacks rule ref")
            if e.get("confidence") not in ("HIGH","MEDIUM"): raise ValueError("bad NUMERIC confidence")
            if factor=="KVS" and val!=0:
                if not e.get("choice_context") or not e.get("alternatives_set") or not e.get("satisfaction_criterion"):
                    raise ValueError("nonzero KVS lacks context/alternatives/criterion")
        elif st=="UNKNOWN":
            if val is not None: raise ValueError("UNKNOWN value must null")
            if e.get("confidence") not in ("LOW","UNKNOWN"): raise ValueError("bad UNKNOWN confidence")
            if all(checks[g] for g in GATES) and not e.get("reason_codes"): raise ValueError("UNKNOWN needs explicit unresolved reason")
        elif st=="DISPUTED":
            if val is not None: raise ValueError("DISPUTED value must null")
            if e.get("confidence") is not None: raise ValueError("DISPUTED confidence must null")
            if not e.get("conflict_alternatives") or len(e["conflict_alternatives"])<2: raise ValueError("DISPUTED needs >=2 alternatives")
        out[(e["coding_item_id"],factor)]=e
    return out

def failed_gates(e): return tuple(g for g in GATES if e["admission_checks"][g] is False)

def decisive_evidence(e):
    return (canon_list(e.get("evidence_references")), canon_list(e.get("verbatim_evidence")))

def route(a,b):
    if "DISPUTED" in (a["status"],b["status"]):
        return "AI_DISPUTED"
    if a["status"]=="NUMERIC" and b["status"]=="NUMERIC":
        if a["value"]==b["value"] and decisive_evidence(a)==decisive_evidence(b):
            return "AI_NUMERIC_CONSENSUS_CANDIDATE"
        return "TARGETED_CRITIQUE_REQUIRED"
    if a["status"]=="UNKNOWN" and b["status"]=="UNKNOWN":
        if failed_gates(a)==failed_gates(b):
            return "AI_SHARED_UNKNOWN"
        return "TARGETED_CRITIQUE_REQUIRED"
    return "TARGETED_CRITIQUE_REQUIRED"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ai1",type=Path); ap.add_argument("--ai2",type=Path); ap.add_argument("--out",type=Path)
    ap.add_argument("--self-test",action="store_true")
    x=ap.parse_args()
    if x.self_test:
        def e(st,val=None,failed=(),refs=("f1",),quotes=("q1",)):
            checks={g:g not in failed for g in GATES}
            return {"status":st,"value":val,"admission_checks":checks,"evidence_references":list(refs),"verbatim_evidence":list(quotes)}
        assert route(e("NUMERIC",5),e("NUMERIC",5))=="AI_NUMERIC_CONSENSUS_CANDIDATE"
        assert route(e("NUMERIC",5),e("NUMERIC",10))=="TARGETED_CRITIQUE_REQUIRED"
        assert route(e("NUMERIC",5),e("NUMERIC",5,refs=("f2",)))=="TARGETED_CRITIQUE_REQUIRED"
        assert route(e("UNKNOWN",failed=("G3",)),e("UNKNOWN",failed=("G3",)))=="AI_SHARED_UNKNOWN"
        assert route(e("UNKNOWN",failed=("G3",)),e("UNKNOWN",failed=("G4",)))=="TARGETED_CRITIQUE_REQUIRED"
        assert route(e("DISPUTED"),e("UNKNOWN",failed=("G3",)))=="AI_DISPUTED"
        print(json.dumps({"self_test":"PASS","cases":6})); return
    if not all((x.ai1,x.ai2,x.out)): ap.error("need --ai1 --ai2 --out")
    r1,r2=load(x.ai1),load(x.ai2)
    if r1.get("run_id")==r2.get("run_id"): raise ValueError("run_id must differ")
    a,b=validate(r1,"AI1"),validate(r2,"AI2")
    rows=[]
    for item in ITEMS:
        for factor in ("POS","KVS"):
            x1,x2=a[(item,factor)],b[(item,factor)]
            tri=route(x1,x2)
            rows.append({"coding_item_id":item,"factor":factor,"ai1_status":x1["status"],"ai1_value":x1["value"],"ai2_status":x2["status"],"ai2_value":x2["value"],"triage":tri,"final_value":None,"calculation_eligible":False})
    counts={k:sum(r["triage"]==k for r in rows) for k in ("AI_NUMERIC_CONSENSUS_CANDIDATE","AI_SHARED_UNKNOWN","AI_DISPUTED","TARGETED_CRITIQUE_REQUIRED")}
    out={"protocol_id":"AI_ONLY_RESEARCH_BETA_V1","protocol_patch":"PATCH_1","state":"PRIMARY_AI_COMPARISON","counts":counts,"entries":rows,"human_validation":"NOT_PERFORMED","human_reliability":"NOT_PERFORMED","uno":"NOT_COMPUTED","note":"No final numeric value is released automatically; numeric consensus candidates require coordinator evidence/rule verification."}
    x.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(counts,ensure_ascii=False))

if __name__=="__main__": main()
