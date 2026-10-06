#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

Q8=Decimal("0.00000001")
DESIGN_ID="AI_ONLY_COMMON_EXOGENOUS_WEIGHT_DESIGN_V2"

class DesignInputError(ValueError): pass

def q8(v:Decimal)->str: return format(v.quantize(Q8,rounding=ROUND_HALF_EVEN),"f")
def D(v:object)->Decimal:
    if isinstance(v,bool) or v is None: raise DesignInputError("finite numeric value required")
    try: x=Decimal(str(v))
    except Exception as exc: raise DesignInputError("invalid numeric value") from exc
    if not x.is_finite(): raise DesignInputError("non-finite numeric value")
    return x

def load(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def validate_grid(grid):
    if grid.get("design_id")!=DESIGN_ID: raise DesignInputError("wrong design_id")
    if grid.get("status")!="FROZEN_BEFORE_NEW_PRIMARY_RESULTS": raise DesignInputError("grid is not frozen")
    if grid.get("baseline")!={"r_actor_a":"1","r_actor_b":"1","q":"1"}: raise DesignInputError("unexpected baseline")
    if len(grid.get("positive_rgu_scenarios",[]))!=7: raise DesignInputError("positive grid count")
    if grid.get("positive_q_scale_checks")!=["0.1","1","10"]: raise DesignInputError("q checks mismatch")
    if len(grid.get("zero_weight_stress",[]))!=4: raise DesignInputError("stress count")

def get_binding(bindings,route):
    if bindings.get("design_id")!=DESIGN_ID or bindings.get("status")!="FROZEN_BEFORE_NEW_PRIMARY_RESULTS":
        raise DesignInputError("bindings not frozen")
    hits=[x for x in bindings.get("lanes",[]) if x.get("route_id")==route]
    if len(hits)!=1: raise DesignInputError("route binding missing or duplicate")
    return hits[0]

def consensus_value(row):
    if row.get("triage")!="CONSENSUS_NUMERIC": raise DesignInputError("non-consensus factor row")
    if row.get("ai1_value")!=row.get("ai2_value"): raise DesignInputError("consensus values differ")
    return D(row.get("ai1_value"))

def extract_company_only(c,b):
    inh=c.get("inherited_worker_record")
    if not isinstance(inh,dict) or inh.get("actor_id")!=b["actor_a"]:
        raise DesignInputError("inherited actor mismatch")
    a={"POS":D(inh.get("POS_AO2")),"KVS":D(inh.get("KVS_AO2"))}
    vals={}
    for row in c.get("company_entries",[]):
        f=row.get("factor")
        if f in {"POS_AO2","KVS_AO2"}: vals[f]=consensus_value(row)
    if set(vals)!={"POS_AO2","KVS_AO2"}: raise DesignInputError("company factors incomplete")
    return {b["actor_a"]:a,b["actor_b"]:{"POS":vals["POS_AO2"],"KVS":vals["KVS_AO2"]}}

def extract_full(c,b):
    vals={}
    for row in c.get("entries",[]):
        a=row.get("actor_id"); f=row.get("factor")
        if a in {b["actor_a"],b["actor_b"]} and f in {"POS_AO2","KVS_AO2"}:
            vals[(a,f)]=consensus_value(row)
    req={(b["actor_a"],"POS_AO2"),(b["actor_a"],"KVS_AO2"),(b["actor_b"],"POS_AO2"),(b["actor_b"],"KVS_AO2")}
    if set(vals)!=req: raise DesignInputError("full dyad factors incomplete")
    return {a:{"POS":vals[(a,"POS_AO2")],"KVS":vals[(a,"KVS_AO2")]} for a in (b["actor_a"],b["actor_b"])}

def extract_factors(c,b):
    if c.get("route_id")!=b["route_id"]: raise DesignInputError("route mismatch")
    if c.get("input_sha256")!=b["input_sha256"]: raise DesignInputError("input hash mismatch")
    if c.get("state")!=b["eligibility_state"]: raise DesignInputError("comparison not eligible")
    if c.get("calculation_release") is not True: raise DesignInputError("comparison release false")
    mode=b.get("extraction_mode")
    if mode=="COMPANY_ONLY_WITH_INHERITED_ACTOR_A": f=extract_company_only(c,b)
    elif mode=="FULL_DYAD_FOUR_ENTRY_CONSENSUS": f=extract_full(c,b)
    else: raise DesignInputError("unsupported extraction_mode")
    for a in (b["actor_a"],b["actor_b"]):
        if f[a]["POS"]<-10 or f[a]["POS"]>10: raise DesignInputError("POS out of range")
        if f[a]["KVS"]<0 or f[a]["KVS"]>10: raise DesignInputError("KVS out of range")
    return f

def calculate(factors,b,ra,rb,q):
    ra,rb,q=D(ra),D(rb),D(q)
    if min(ra,rb,q)<0 or max(ra,rb,q)>10: raise DesignInputError("weight out of range")
    W=Decimal(0); pos=Decimal(0); neg=Decimal(0); trace=[]
    for actor,r in ((b["actor_a"],ra),(b["actor_b"],rb)):
        x=factors[actor]["POS"]; k=factors[actor]["KVS"]; w=r*k
        W+=w; pos+=Decimal(10)*w*max(x,Decimal(0)); neg+=Decimal(10)*w*max(-x,Decimal(0))
        trace.append({"actor_id":actor,"POS":q8(x),"KVS":q8(k),"RGU":q8(r),"effective_weight":q8(w)})
    if W==0:
        return {"status":"NOT_COMPUTABLE","W":"0.00000000","P":None,"N":None,"A":None,"B":None,"Pol":None,"single_ptn_uno_field":None,"q":q8(q),"trace":trace}
    P=pos/W; N=neg/W; pol=Decimal(2)*min(P,N)
    return {"status":"COMPLETE","W":q8(W),"P":q8(P),"N":q8(N),"A":q8(P+N),"B":q8(P-N),"Pol":q8(pol),"single_ptn_uno_field":None if q==0 else q8(pol),"q":q8(q),"trace":trace}

def scen(sid,fam,f,b,ra,rb,q):
    return {"scenario_id":sid,"family":fam,"weights":{"RGU":{b["actor_a"]:str(ra),b["actor_b"]:str(rb)},"KVPTN":{b["ptn_id"]:str(q)}},"result":calculate(f,b,ra,rb,q)}

def run(c,grid,bindings):
    validate_grid(grid)
    route=c.get("route_id")
    try:
        b=get_binding(bindings,route); f=extract_factors(c,b)
    except DesignInputError as exc:
        return {"route_id":route,"design_id":grid.get("design_id"),"state":"NOT_COMPUTABLE","reason":str(exc),"calculation_release":False,"historical_snapshot":"NOT_ESTABLISHED","historical_area_UNO":"NOT_COMPUTED"}
    bl=grid["baseline"]
    baseline=scen("BASELINE_EQUAL_POSITIVE","BASELINE",f,b,bl["r_actor_a"],bl["r_actor_b"],bl["q"])
    main=[scen(x["scenario_id"],"RGU_ONLY",f,b,x["r_actor_a"],x["r_actor_b"],"1") for x in grid["positive_rgu_scenarios"]]
    qc=[scen("Q_SCALE_"+q.replace(".","_"),"KVPTN_POSITIVE_SCALE_INVARIANCE",f,b,"1","1",q) for q in grid["positive_q_scale_checks"]]
    qpol={x["result"]["Pol"] for x in qc}
    stress=[scen(x["scenario_id"],"ZERO_WEIGHT_COVERAGE_STRESS",f,b,x["r_actor_a"],x["r_actor_b"],x["q"]) for x in grid["zero_weight_stress"]]
    pols=[Decimal(x["result"]["Pol"]) for x in main if x["result"]["Pol"] is not None]
    return {"route_id":route,"input_sha256":b["input_sha256"],"design_id":DESIGN_ID,"state":"COMPUTED_READ_ONLY_RESEARCH_SCENARIOS","actor_binding":{"actor_a":b["actor_a"],"actor_b":b["actor_b"],"ptn_id":b["ptn_id"]},"factor_record":{a:{"POS_AO2":int(v["POS"]),"KVS_AO2":int(v["KVS"])} for a,v in f.items()},"baseline":baseline,"positive_RGU_scenarios":main,"positive_q_invariance":{"passed":len(qpol)==1,"values_checked":grid["positive_q_scale_checks"],"observed_Pol_values":sorted(qpol),"interpretation":"Expected one-PTN q-scale invariance; not substantive KVPTN sensitivity."},"zero_weight_stress":stress,"envelope":{"Pol_min":q8(min(pols)),"Pol_max":q8(max(pols)),"baseline_Pol":baseline["result"]["Pol"],"robustness_label":"NOT_ASSIGNED_BY_PROTOCOL"},"calculation_release":True,"metric_label":"SINGLE_PTN_PAIR_DYAD_SCENARIO_NOT_AREA_UNO","historical_snapshot":"NOT_ESTABLISHED","historical_area_UNO":"NOT_COMPUTED","human_validation":"NOT_PERFORMED","predictive_validation":"NOT_CLAIMED"}

def cmp_company(b,pos=5,kvs=5):
    return {"route_id":b["route_id"],"input_sha256":b["input_sha256"],"state":b["eligibility_state"],"inherited_worker_record":{"actor_id":b["actor_a"],"POS_AO2":-5,"KVS_AO2":5},"company_entries":[{"factor":"POS_AO2","triage":"CONSENSUS_NUMERIC","ai1_value":pos,"ai2_value":pos},{"factor":"KVS_AO2","triage":"CONSENSUS_NUMERIC","ai1_value":kvs,"ai2_value":kvs}],"calculation_release":True}

def cmp_full(b,a_pos=-5,a_kvs=5,b_pos=5,b_kvs=5):
    rows=[]
    for actor,pos,kvs in ((b["actor_a"],a_pos,a_kvs),(b["actor_b"],b_pos,b_kvs)):
        rows += [{"actor_id":actor,"factor":"POS_AO2","triage":"CONSENSUS_NUMERIC","ai1_value":pos,"ai2_value":pos},{"actor_id":actor,"factor":"KVS_AO2","triage":"CONSENSUS_NUMERIC","ai1_value":kvs,"ai2_value":kvs}]
    return {"route_id":b["route_id"],"input_sha256":b["input_sha256"],"state":b["eligibility_state"],"entries":rows,"calculation_release":True}

def self_test(grid,bindings):
    validate_grid(grid); L={x["route_id"]:x for x in bindings["lanes"]}; n=0
    for route in ("AI_ONLY_DYAD_KBM_E02_V100","AI_ONLY_PAIR_KBM_E05_V100"):
        out=run(cmp_company(L[route]),grid,bindings); assert out["state"]=="COMPUTED_READ_ONLY_RESEARCH_SCENARIOS"; n+=1
    for route in ("AI_ONLY_DYAD_OMG_NOV24_V100","AI_ONLY_DYAD_D25_E02_V100"):
        out=run(cmp_full(L[route]),grid,bindings); assert out["baseline"]["result"]["Pol"]=="50.00000000"; n+=1
    out=run(cmp_company(L["AI_ONLY_DYAD_KBM_E02_V100"]),grid,bindings)
    assert out["envelope"]["Pol_min"]=="9.09090909" and out["envelope"]["Pol_max"]=="50.00000000"; n+=1
    assert out["positive_q_invariance"]["passed"] is True; n+=1
    az=next(x for x in out["zero_weight_stress"] if x["scenario_id"]=="R_ACTOR_A_ZERO"); assert az["result"]["Pol"]=="0.00000000"; n+=1
    zz=next(x for x in out["zero_weight_stress"] if x["scenario_id"]=="R_ALL_ZERO"); assert zz["result"]["status"]=="NOT_COMPUTABLE"; n+=1
    b=L["AI_ONLY_PAIR_KBM_E05_V100"]; out8=run(cmp_company(b,5,8),grid,bindings); assert out8["baseline"]["result"]["Pol"]=="38.46153846"; n+=1
    bad=cmp_full(L["AI_ONLY_DYAD_D25_E02_V100"]); bad["state"]="HOLD_FACTOR_INCOMPLETE"; bad["calculation_release"]=False; assert run(bad,grid,bindings)["state"]=="NOT_COMPUTABLE"; n+=1
    bad2=cmp_full(L["AI_ONLY_DYAD_D25_E02_V100"]); bad2["input_sha256"]="0"*64; assert run(bad2,grid,bindings)["state"]=="NOT_COMPUTABLE"; n+=1
    return {"self_test":"PASS","cases":n}

def main():
    p=argparse.ArgumentParser();p.add_argument("--comparison");p.add_argument("--grid",required=True);p.add_argument("--bindings",required=True);p.add_argument("--out");p.add_argument("--self-test",action="store_true");a=p.parse_args()
    grid=load(a.grid);bindings=load(a.bindings)
    if a.self_test: print(json.dumps(self_test(grid,bindings))); return
    if not(a.comparison and a.out): p.error("--comparison and --out required unless --self-test")
    result=run(load(a.comparison),grid,bindings);Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps({"state":result["state"],"route_id":result.get("route_id")}))
if __name__=="__main__":main()
