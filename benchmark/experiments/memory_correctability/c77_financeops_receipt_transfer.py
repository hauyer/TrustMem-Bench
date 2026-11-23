"""Cross-stage receipt intervention on a frozen external benchmark's native tools."""
from collections import Counter
from copy import deepcopy
import argparse
import json
from pathlib import Path
import subprocess
import time

import c74_skillhorizon_native_budget as c74

HERE=Path(__file__).resolve()
MANIFEST=c74.SOURCE/"manifests/FinanceOps.json"
OUT=c74.ROOT/"artifacts/research_decisions/20261119-c77-financeops-receipt-transfer-v1"
PROTOCOL=HERE.with_name("C77_FINANCEOPS_RECEIPT_TRANSFER_PROTOCOL.md")
ARMS=("keep","remove","sham","refund")
WRITE={"execute_step","run_skill_script"}
ROUTING_METADATA={"id","stage","kind","invoice_sources"}


class BudgetStop(ValueError):
    pass


def cases():
    rows=c74.read(MANIFEST)["tasks"]
    seen=set()
    result=[]
    for x in rows:
        if x["band"]=="64k" and x["family"]=="receivables_reconciliation" and x["variant"] not in seen:
            result.append(x)
            seen.add(x["variant"])
    assert len(result)==3
    return result


def manifest_inputs():
    return {"pin":c74.PIN,"manifest_sha":c74.sha(MANIFEST),"protocol_sha":c74.sha(PROTOCOL),
            "script_sha":c74.sha(HERE),"shared_code_sha":c74.sha(Path(c74.__file__)),
            "cases":cases(),"budget_modes":["official_default","reference_prefix"],
            "arms":ARMS,"routing_metadata_kept_on_receipt_removal":sorted(ROUTING_METADATA),
            "model_calls_cap":0,"usd_cap":0}


def native():
    import sys
    sys.path.insert(0,str(c74.SOURCE/"src"))
    from skillhorizon.financeops.construction import make_project
    from skillhorizon.financeops.runtime import Runtime
    from skillhorizon.financeops.witness import Witness
    from skillhorizon.dataflow_v5.verification import score
    return make_project,Runtime,Witness,score


def execute(directory, rt_type, Parent, score, initial, *, cap, checkpoint=None,prefix=(),admission=None,arm=None):
    directory.mkdir()
    c74.write(directory/"project.json",initial if checkpoint is None else checkpoint)
    rt=rt_type(directory,persist=False,record_calls=True)
    # Funding and evidence choices come only from Witness + public tools.
    empty=set()
    flushed=None
    edits=[]
    watch=[]
    tape=[]
    budget=[]
    latest_reads={}
    seen_boundary=None
    decision_context=[]
    historic=len(prefix)
    charged=0
    refunded=False
    stopped=False
    rejected=None
    target=admission["target"] if admission else None
    sham=admission["sham"] if admission else None

    def payload(v):
        return (v["invoices"],v["versions"]["invoices"])

    def invoke(name,args):
        nonlocal charged,seen_boundary,refunded,flushed
        idx=len(tape)+1
        if charged>=cap:
            raise BudgetStop(name)
        charged+=1
        if idx<=historic:
            prev=prefix[idx-1]
            assert (prev["skill_id"],prev["arguments"])==(name,args)
            value=deepcopy(prev["result"])
        else:
            value=rt.call(name,args)
        event=dict(skill_id=name,arguments=deepcopy(args),result=deepcopy(value))
        tape.append(event)
        if name=="read_object" and args.get("collection")=="sources" and value["ok"]:
            key=args["object_id"]
            latest_reads[key]=idx
            if target and arm in ("refund","remove") and key==target and idx>historic and flushed is None:
                old=prefix[admission["receipt_index"]-1]["result"]["object"]
                new=value["object"]
                equal=payload(old)==payload(new)
                flushed=dict(index=idx,match_invoice_projection=equal,match_full_object=old==new)
                # A refunded query still went through the native public tool.
                if arm=="refund" and equal:
                    charged-=1
                    refunded=True
        charge=0 if refunded and flushed and flushed["index"]==idx else 1
        budget.append(dict(index=idx,charged=charge,used=charged,remaining=cap-charged))
        if value.get("notices") and seen_boundary is None:
            assert name=="execute_step" and args["skill_id"]=="close-stage"
            seen_boundary=dict(index=idx,stage=args["arguments"]["stage"],notices=deepcopy(value["notices"]))
            if not historic:
                c74.write(directory/"checkpoint.json",rt.p)
            else:
                assert idx==historic
                if arm!="keep":
                    key=sham if arm=="sham" else target
                    prior=person.sources[key]
                    # Drop substantive evidence only. Preserve identity/routing and insertion order:
                    # the native witness enumerates these keys for closures and change notices.
                    person.sources[key]={k:v for k,v in prior.items() if k in ROUTING_METADATA}
                    empty.add(key)
                    edits.append(dict(key=key,original_keys=sorted(prior),preserved_keys=sorted(person.sources[key])))
        return value

    class Observer(Parent):
        def solve(self,key,refresh=False):
            decision_context.append(key)
            try:
                return super().solve(key,refresh)
            finally:
                assert decision_context.pop()==key

        def source(self,key,refresh=False):
            before=len(tape)
            result=super().source(key,refresh or key in empty)
            empty.discard(key)
            watch.append(dict(at=len(tape),first_before=before,key=key,context=decision_context[-1] if decision_context else None,
                         native_read=len(tape)>before,observed_read_index=latest_reads.get(key)))
            return result

    person=Observer(invoke)
    try:
        person.run()
    except BudgetStop as e:
        stopped=True
        rejected=str(e)
    rt.save()
    result=score(rt,initial)
    full=c74.read_log(directory/"actions.jsonl")
    assert full==tape[historic:]
    assert charged==len(tape)-refunded and charged<=cap
    no_output={e["source_id"] for e in result["errors"] if "source_id" in e}
    completed=sorted(set(initial["sources"])-no_output)
    assert len(completed)==result["completed_work_packages"]
    if historic:
        assert tape[:historic]==list(prefix)
    c74.write(directory/"BUDGET.json",budget)
    c74.write(directory/"OBSERVATIONS.json",watch)
    if not historic:
        c74.write(directory/"BOUNDARY.json",seen_boundary)
    row=dict(cap=cap,raw_calls=len(tape),charged=charged,query_calls=sum(x["skill_id"] not in WRITE for x in tape),
          business_attempts=sum(x["skill_id"] in WRITE for x in tape),original_prefix_calls=historic,
          native_suffix_calls=len(full),error_count=sum(not x["result"]["ok"] for x in tape),budget_stopped=stopped,
          stop_before_tool=rejected,native_score=result,completed_source_ids=completed,
          publication_present=bool(rt.p["publication"]),first_change=seen_boundary,
          edits=edits,refunded=int(refunded),affected_read=flushed)
    c74.write(directory/"RESULT.json",row)
    return row,tape


def admit(directory,first,tape,row):
    change=first["first_change"]
    out={"id":row["id"],"budget_default":c74.budget(row),"budget_tight":row["reference_calls"],"admitted":False,
         "matches_published_reference":first["raw_calls"]==row["reference_calls"] and first["business_attempts"]==row["business_calls"],
         "reference_score":first["native_score"],"event":change}
    if not change or not out["matches_published_reference"] or not first["native_score"]["task_success"]:
        return {**out,"reason":"no native change, published count mismatch, or reference failed"}
    pivot=change["index"]
    affected={x["source_id"] for x in change["notices"]}
    next_period=change["stage"]+1
    reads=c74.read(directory/"OBSERVATIONS.json")
    native_prefix={r["key"]:r["observed_read_index"] for r in reads if r["at"]<=pivot and r["observed_read_index"]}
    after=reads_for=lambda k:[r for r in reads if r["at"]>pivot and r["key"]==k]
    post={r["key"] for r in reads if r["at"]>pivot}
    posted={x["result"]["source_id"]:i for i,x in enumerate(tape,1) if i>pivot
            and x["arguments"].get("skill_id")=="post-reconciliation" and x["result"]["ok"]}
    fresh={}
    for i,x in enumerate(tape,1):
        if i>pivot and x["skill_id"]=="read_object" and x["arguments"].get("collection")=="sources":
            data=x["result"]["object"]
            if data.get("kind")=="receivables" and data["stage"]==next_period and data["id"] in posted:
                fresh.setdefault(data["id"],(i,data))
    candidates=[]
    for target_request,(i,t) in fresh.items():
        for id in t["invoice_sources"]:
            first_use=next((a for a in reads if a["at"]>=i and a["at"]<posted[target_request]
                           and a["context"]==target_request and a["key"]==id),None)
            if not first_use or first_use["native_read"] or id in affected or id not in native_prefix:
                continue
            j=native_prefix[id]
            if first_use["observed_read_index"]!=j:
                continue
            record=tape[j-1]
            assert record["skill_id"]=="read_object" and record["arguments"]=={"collection":"sources","object_id":id}
            assert "invoices" in record["result"]["object"]
            peers=[k for k,(_,p) in fresh.items() if k!=target_request and k not in affected
                  and id not in p["invoice_sources"] and not set(p["invoice_sources"])&affected]
            if peers:
                candidates.append(dict(target=id,receipt_index=j,consumer=target_request,consumer_post=posted[target_request],
                    first_consumer_use=first_use["at"],other_targets=peers,matching_invoice_scope="invoices plus versions.invoices"))
    out.update(pivot=pivot,affected=sorted(affected),next_period=next_period,
               next_period_completed=len(fresh),candidate_count=len(candidates))
    if not candidates:
        return {**out,"reason":"no actual retained invoice and separate next-stage completed peer"}
    chosen=candidates[0]
    shams=sorted(set(native_prefix)-affected-post-{chosen["target"]})
    shams=[k for k in shams if "invoices" in tape[native_prefix[k]-1]["result"]["object"]]
    if not shams:
        return {**out,"reason":"no same type unused observed sham receipt"}
    return {**out,**chosen,"sham":shams[0],"sham_receipt_index":native_prefix[shams[0]],"admitted":True}


def reference(out):
    mk,rt,w,s=native()
    data=out/"REFERENCE"
    data.mkdir()
    for row in cases():
        t=time.perf_counter()
        d=data/row["id"]
        d.mkdir()
        initial=mk(**row["parameters"])
        initial["task_id"]+="-"+row["id"]
        assert initial["task_id"]==row["task_id"]
        c74.write(d/"INITIAL.json",initial)
        r,logs=execute(d/"run",rt,w,s,initial,cap=c74.budget(row))
        a=admit(d/"run",r,logs,row)
        c74.write(d/"ADMISSION.json",a)
        print(row["id"], r["raw_calls"],r["native_score"]["task_success"],a.get("admitted"),a.get("reason"),round(time.perf_counter()-t,2),flush=True)


def compare(out):
    mk,rt,w,s=native()
    root=out/"PAIR"
    root.mkdir()
    freeze={}
    for row in cases():
        d=out/"REFERENCE"/row["id"]
        freeze[row["id"]]={p.relative_to(d).as_posix():c74.sha(p) for p in
            (d/"INITIAL.json",d/"ADMISSION.json",d/"run/actions.jsonl",d/"run/RESULT.json") if p.exists()}
        if (d/"run/checkpoint.json").exists():
            freeze[row["id"]]["run/checkpoint.json"]=c74.sha(d/"run/checkpoint.json")
    c74.write(root/"FREEZE.json",dict(reference_sha=freeze,protocol=c74.sha(PROTOCOL),runner=c74.sha(HERE)))
    for row in cases():
        d=out/"REFERENCE"/row["id"]
        a=c74.read(d/"ADMISSION.json")
        if not a["admitted"]:
            continue
        logs=c74.read_log(d/"run/actions.jsonl")
        prefix=tuple(logs[:a["pivot"]])
        checkpoint=c74.read(d/"run/checkpoint.json")
        initial=c74.read(d/"INITIAL.json")
        dirs=root/row["id"]
        dirs.mkdir()
        for mode,cap in (("official_default",a["budget_default"]),("reference_prefix",a["budget_tight"])):
            common=dirs/mode
            common.mkdir()
            for arm in ARMS:
                r,tape=execute(common/arm,rt,w,s,initial,cap=cap,checkpoint=checkpoint,prefix=prefix,admission=a,arm=arm)
                if arm=="keep": assert tape==logs
                print(row["id"],mode,arm,r["charged"],r["native_score"]["completed_work_packages"],r["native_score"]["task_success"],flush=True)
    c74.write(root/"COMPLETED.json",dict(model_calls=0,api_usd=0))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=("freeze","reference","compare"))
    p.add_argument("--out",type=Path,default=OUT)
    a=p.parse_args()
    assert subprocess.check_output(["git","-C",str(c74.SOURCE),"rev-parse","HEAD"],text=True).strip()==c74.PIN
    assert not subprocess.check_output(["git","-C",str(c74.SOURCE),"status","--porcelain","--untracked-files=no"])
    if a.stage=="freeze":c74.write(a.out/"FREEZE.json",manifest_inputs())
    else:
        assert c74.read(a.out/"FREEZE.json")==json.loads(json.dumps(manifest_inputs()))
        (reference if a.stage=="reference" else compare)(a.out)
