#!/usr/bin/env python3
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ALLOWED={"RESOLVED","NOT_RESOLVED","NEED_HUMAN"}
MATERIAL="767da0d3f4fc189e587efd9084ea20ecb546f4f102c85e11f0153bc9d40a04fa"

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def validate(resp, reviewer_id, registry):
    if resp.get("review_id")!="AI_EXCEPTION_REVIEW_V1": raise ValueError("bad review_id")
    if resp.get("reviewer_id")!=reviewer_id: raise ValueError("bad reviewer_id")
    if resp.get("material_sha256")!=MATERIAL: raise ValueError("bad material hash")
    att=resp.get("attestation",{})
    for k in ("no_other_reviewer_answers_seen","no_ai_answers_seen","no_outcome_used","no_factor_scoring_or_uno"):
        if att.get(k) is not True: raise ValueError("attestation failed: "+k)
    entries=resp.get("entries")
    if not isinstance(entries,list) or len(entries)!=registry["count"]: raise ValueError("must contain exactly 42 entries")
    expected={u["unit_id"] for u in registry["units"]}
    ids=[e.get("unit_id") for e in entries]
    if len(set(ids))!=len(ids) or set(ids)!=expected: raise ValueError("unit set mismatch or duplicate")
    out={}
    for e in entries:
        st=e.get("status")
        if st not in ALLOWED: raise ValueError("bad status")
        if not isinstance(e.get("reason"),str) or not e["reason"].strip(): raise ValueError("missing reason")
        c=e.get("confidence")
        if type(c) not in (int,float) or c<0 or c>1: raise ValueError("bad confidence")
        ru=e.get("remaining_unknowns")
        if not isinstance(ru,list): raise ValueError("remaining_unknowns must be list")
        if st=="RESOLVED":
            if not isinstance(e.get("exact_evidence"),str) or not e["exact_evidence"].strip(): raise ValueError("RESOLVED needs exact_evidence")
            if not isinstance(e.get("evidence_reference"),str) or not e["evidence_reference"].strip(): raise ValueError("RESOLVED needs evidence_reference")
            if ru: raise ValueError("RESOLVED requires empty remaining_unknowns")
        else:
            if not ru or not all(isinstance(x,str) and x.strip() for x in ru): raise ValueError(st+" requires remaining_unknowns")
        out[e["unit_id"]]=e
    return out

def route(a,b):
    sa,sb=a["status"],b["status"]
    if "NEED_HUMAN" in (sa,sb): return "ESCALATE_REQUIRED"
    if sa=="NOT_RESOLVED" and sb=="NOT_RESOLVED": return "OPEN_NOT_RESOLVED"
    if sa=="RESOLVED" and sb=="RESOLVED": return "DOUBLE_HUMAN_RESOLVED_CANDIDATE"
    return "DIFFERENCE_REQUIRES_COORDINATOR"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--e1",type=Path); ap.add_argument("--e2",type=Path)
    ap.add_argument("--registry",type=Path); ap.add_argument("--out",type=Path)
    ap.add_argument("--self-test",action="store_true")
    x=ap.parse_args()
    if x.self_test:
        tests=[
          ("RR",route({"status":"RESOLVED"},{"status":"RESOLVED"}),"DOUBLE_HUMAN_RESOLVED_CANDIDATE"),
          ("NN",route({"status":"NOT_RESOLVED"},{"status":"NOT_RESOLVED"}),"OPEN_NOT_RESOLVED"),
          ("RN",route({"status":"RESOLVED"},{"status":"NOT_RESOLVED"}),"DIFFERENCE_REQUIRES_COORDINATOR"),
          ("HN",route({"status":"NEED_HUMAN"},{"status":"NOT_RESOLVED"}),"ESCALATE_REQUIRED")]
        assert all(g==e for _,g,e in tests)
        print(json.dumps({"self_test":"PASS","tests":[t[0] for t in tests]})); return
    if not all((x.e1,x.e2,x.registry,x.out)): ap.error("need --e1 --e2 --registry --out")
    reg=load(x.registry)
    e1raw,e2raw=load(x.e1),load(x.e2)
    e1=validate(e1raw,"HUMAN_EXCEPTION_E1",reg)
    e2=validate(e2raw,"HUMAN_EXCEPTION_E2",reg)
    rows=[]
    verify=[]
    for u in reg["units"]:
        uid=u["unit_id"]; tri=route(e1[uid],e2[uid])
        rows.append({"unit_id":uid,"kind":u["kind"],"e1_status":e1[uid]["status"],"e2_status":e2[uid]["status"],"triage":tri,"admission_changed":False})
        if tri!="OPEN_NOT_RESOLVED":
            verify.append({"unit_id":uid,"kind":u["kind"],"triage":tri,"coordinator_disposition":None,"verified_evidence_reference":None,"reason":None,"remaining_unknowns":None})
    result={"review_id":"AI_EXCEPTION_REVIEW_V1","state":"HUMAN_EXCEPTION_RESPONSES_COMPARED","material_sha256":MATERIAL,"generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "counts":{k:sum(r["triage"]==k for r in rows) for k in ("DOUBLE_HUMAN_RESOLVED_CANDIDATE","OPEN_NOT_RESOLVED","DIFFERENCE_REQUIRES_COORDINATOR","ESCALATE_REQUIRED")},
      "units":rows,"human_reliability":"NOT_COMPUTED","admission_changed":False,"frozen_H1_H2_release":"UNCHANGED_NO_AUTOMATIC_DISTRIBUTION"}
    x.out.mkdir(parents=True,exist_ok=False)
    (x.out/"HUMAN_EXCEPTION_COMPARISON_RESULTS.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (x.out/"COORDINATOR_VERIFICATION_TEMPLATE.json").write_text(json.dumps({"state":"PENDING_COORDINATOR_VERIFICATION","entries":verify},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (x.out/"RUN_MANIFEST.json").write_text(json.dumps({"response_sha256":{"E1":sha(x.e1),"E2":sha(x.e2)},"registry_sha256":sha(x.registry)},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result["counts"],ensure_ascii=False))

if __name__=="__main__":
    main()
