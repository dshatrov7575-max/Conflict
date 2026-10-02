#!/usr/bin/env python3
import argparse, json
from pathlib import Path

ITEMS={"AO2-01","AO2-02","AO2-03","AO2-04","AO2-05","AO2-06"}
FACTORS={"POS_AO2","KVS_AO2"}
POS={-10,-5,0,5,10}
KVS={0,2,5,8,10}
GATES=[f"A{i}" for i in range(1,9)]

def load(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def validate(r,role):
    if r.get("route_id")!="AI_ARCHIVAL_OBSERVATIONAL_V2": raise ValueError("route_id")
    if r.get("rubric_version")!="2.0.0-draft1": raise ValueError("rubric_version")
    if r.get("coder_role")!=role: raise ValueError("coder_role")
    a=r.get("attestation",{})
    if a.get("other_coder_output_seen") is not False: raise ValueError("other coder seen")
    if a.get("prior_ao2_outputs_seen") is not False: raise ValueError("prior AO2 seen")
    if a.get("outcome_used_as_evidence") is not False: raise ValueError("outcome used")
    if a.get("external_sources_used") is not False: raise ValueError("external sources used")
    es=r.get("entries",[])
    if len(es)!=12: raise ValueError("need 12 entries")
    keys=[(e.get("item_id"),e.get("factor")) for e in es]
    if len(set(keys))!=12 or set(keys)!={(i,f) for i in ITEMS for f in FACTORS}: raise ValueError("entry set")
    out={}
    for e in es:
        st=e.get("status"); val=e.get("value"); f=e.get("factor")
        if st not in {"NUMERIC","UNKNOWN","DISPUTED"}: raise ValueError("status")
        ch=e.get("admission_checks",{})
        if set(ch)!=set(GATES) or any(type(ch[g]) is not bool for g in GATES): raise ValueError("gates")
        if st=="NUMERIC":
            if val not in (POS if f=="POS_AO2" else KVS): raise ValueError("anchor")
            if not all(ch[g] for g in GATES): raise ValueError("numeric failed gate")
            if not e.get("evidence_ids"): raise ValueError("numeric evidence")
            if e.get("confidence") not in {"HIGH","MEDIUM"}: raise ValueError("numeric confidence")
        elif st=="UNKNOWN":
            if val is not None: raise ValueError("unknown value")
            if e.get("confidence") not in {"LOW","UNKNOWN"}: raise ValueError("unknown confidence")
        else:
            if val is not None: raise ValueError("disputed value")
            if e.get("confidence") is not None: raise ValueError("disputed confidence")
        out[(e["item_id"],f)]=e
    return out

def failed(e): return tuple(g for g in GATES if e["admission_checks"][g] is False)
def evid(e): return tuple(sorted(e.get("evidence_ids",[])))

def route(a,b):
    if "DISPUTED" in (a["status"],b["status"]): return "AO2_DISPUTED"
    if a["status"]=="NUMERIC" and b["status"]=="NUMERIC":
        if a["value"]==b["value"] and evid(a)==evid(b): return "AO2_NUMERIC_CONSENSUS_CANDIDATE"
        return "TARGETED_CRITIQUE_REQUIRED"
    if a["status"]=="UNKNOWN" and b["status"]=="UNKNOWN":
        if failed(a)==failed(b): return "AO2_SHARED_UNKNOWN"
        return "TARGETED_CRITIQUE_REQUIRED"
    return "TARGETED_CRITIQUE_REQUIRED"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ai1"); ap.add_argument("--ai2"); ap.add_argument("--out")
    ap.add_argument("--self-test",action="store_true")
    x=ap.parse_args()
    if x.self_test:
        def e(s,v=None,fail=(),ids=("E1",)):
            return {"status":s,"value":v,"admission_checks":{g:g not in fail for g in GATES},"evidence_ids":list(ids)}
        assert route(e("NUMERIC",-5),e("NUMERIC",-5))=="AO2_NUMERIC_CONSENSUS_CANDIDATE"
        assert route(e("NUMERIC",-5),e("NUMERIC",-10))=="TARGETED_CRITIQUE_REQUIRED"
        assert route(e("UNKNOWN",fail=("A5",)),e("UNKNOWN",fail=("A5",)))=="AO2_SHARED_UNKNOWN"
        assert route(e("UNKNOWN",fail=("A5",)),e("UNKNOWN",fail=("A4",)))=="TARGETED_CRITIQUE_REQUIRED"
        assert route(e("DISPUTED"),e("UNKNOWN",fail=("A5",)))=="AO2_DISPUTED"
        print(json.dumps({"self_test":"PASS","cases":5})); return
    a=load(x.ai1); b=load(x.ai2)
    if a.get("run_id")==b.get("run_id"): raise ValueError("same run_id")
    A=validate(a,"AO2_AI1"); B=validate(b,"AO2_AI2")
    rows=[]
    for i in sorted(ITEMS):
      for f in ("POS_AO2","KVS_AO2"):
        aa,bb=A[(i,f)],B[(i,f)]
        rows.append({"item_id":i,"factor":f,"ai1_status":aa["status"],"ai1_value":aa["value"],"ai2_status":bb["status"],"ai2_value":bb["value"],"triage":route(aa,bb),"calculation_eligible":False,"final_value":None})
    counts={k:sum(r["triage"]==k for r in rows) for k in ("AO2_NUMERIC_CONSENSUS_CANDIDATE","AO2_SHARED_UNKNOWN","AO2_DISPUTED","TARGETED_CRITIQUE_REQUIRED")}
    out={"route_id":"AI_ARCHIVAL_OBSERVATIONAL_V2","rubric_version":"2.0.0-draft1","state":"PRIMARY_COMPARISON","counts":counts,"entries":rows,"human_validation":"NOT_PERFORMED","strict_v1_overwritten":False,"uno":"NOT_COMPUTED","note":"Numeric consensus is only a candidate; coordinator verification is mandatory before any Core use."}
    Path(x.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(counts))
if __name__=="__main__": main()
