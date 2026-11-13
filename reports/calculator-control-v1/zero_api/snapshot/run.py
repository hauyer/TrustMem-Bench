"""Frozen paired snapshots with or without a source-free arithmetic action."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT=Path.cwd()
HERE=Path(__file__).resolve().parent
REPO=ROOT/"github-release/TrustMem-Bench"
PARENT=ROOT/"artifacts/research_decisions/20261113-native-mem0-reader-v1"
sys.path.insert(0,str(HERE if (HERE/"trustmem_runtime").is_dir() else REPO))
from trustmem_runtime.calculator import quality_check
from trustmem_runtime.data import canonical, scan
from trustmem_runtime.evidence import calculate
from trustmem_runtime.grading import reference
from trustmem_runtime.run import read_case
from trustmem_runtime.tool_cache import ToolCache

EXTRA="""
The allowed-action list above is extended by this optional ordinary arithmetic action:
{"action":"quality_check","selected_correct":integer,"selected_total":integer,
 "threshold_numerator":integer,"threshold_denominator":integer}.
This tool compares the supplied share to the supplied threshold exactly, with a nonempty selected
population required. It does not read notes, sources or hidden facts, and does not bind the supplied
numbers to evidence. Copy or derive only quantities justified by the shown current-source notes.
The requested threshold still comes from the current task. You may use a sound lower/upper count bound
when it suffices for this task, but the calculator does not prove that the bound is appropriate.
A tool action consumes one of the same two action slots; after its result, submit the actual gate.
The existing query, submit and abstain actions and backend cache remain available unchanged.
"""


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_system():
    tree=ast.parse((PARENT/"snapshot/run.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id=="READER_SYSTEM" for t in n.targets))


def prepare(output,preflight=None):
    output.mkdir(parents=True)
    snap=output/"snapshot"
    snap.mkdir()
    for name in ("run.py","read_cache.py"):
        shutil.copyfile(HERE/name,snap/name)
    shutil.copytree(REPO/"trustmem_runtime",snap/"trustmem_runtime",ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(REPO/"examples/metered_deepseek.py",snap/"metered_deepseek.py")
    shutil.copyfile(HERE/"PROTOCOL.md",output/"PROTOCOL.md")
    original=load(PARENT/"cases/quality.case.json")
    (output/"cases").mkdir()
    for path in (PARENT/"cases").glob("quality*.*"):
        shutil.copyfile(path,output/"cases"/path.name)
    records=[]
    paths=[output/"PROTOCOL.md",PARENT/"models/results.json",PARENT/"snapshot/run.py",*snap.rglob("*.py"),*list((output/"cases").glob("*"))]
    for backend in ("mem0","verbatim"):
        events=load(PARENT/f"models/{backend}/events.json")
        assert len(events)==6
        previous={}
        provenance={}
        for index,entry in enumerate(original["tasks"]):
            source=PARENT/f"models/{backend}/s{index:02}/t0-input.json"
            target=output/"inputs"/f"{backend}-s{index:02}.json"
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source,target)
            payload=load(target)
            assert payload["tool_trace"]==[] and payload["remaining_actions"]==2
            assert payload["current_source_id"]==entry["source_id"] and payload["task"]==entry["request"]
            records.append(dict(id=f"{backend}-s{index:02}",backend=backend,index=index,
                payload=target.relative_to(output).as_posix(),source_id=entry["source_id"],
                cache_receipts=list(previous.values()),cache_provenance=list(provenance.values())))
            paths += [source,target]
            for turn,step in enumerate(events[index]["tool_trace"]):
                if step["action"]["action"]=="query":
                    receipt=step["result"]["receipt"]
                    previous[receipt["source_id"]]=receipt
                    provenance[receipt["source_id"]]=dict(backend=backend,earlier_session=index,turn=turn,
                        event_file=f"{PARENT.relative_to(ROOT).as_posix()}/models/{backend}/events.json")
        paths.append(PARENT/f"models/{backend}/events.json")
    dump(output/"states.json",records)
    paths.append(output/"states.json")
    system=extract_system()
    rng=random.Random(2026111315)
    order=list(range(12))
    rng.shuffle(order)
    schedule=[]
    for index in order:
        arms=["control","calculator"]
        rng.shuffle(arms)
        schedule.extend(dict(state=records[index]["id"],arm=arm) for arm in arms)
    dump(output/"schedule.json",schedule)
    paths.append(output/"schedule.json")
    if preflight:
        tested=load(preflight/"preflight/results.json")
        assert tested["status"]=="complete" and tested["scripted_deliveries"]==24 and tested["calculator_exhaustion"]==8190
        shutil.copyfile(preflight/"preflight/results.json",output/"prepaid-preflight.json")
        paths += [preflight/"preflight/results.json",preflight/"freeze.json",output/"prepaid-preflight.json"]
        for name in ("run.py","read_cache.py","trustmem_runtime/calculator.py","trustmem_runtime/data.py","trustmem_runtime/evidence.py"):
            assert sha(preflight/"snapshot"/name)==sha(snap/name),name
    dump(output/"freeze.json",dict(at=datetime.now(timezone.utc).isoformat(),stage="models" if preflight else "preflight",
        model_calls_cap=48 if preflight else 0,usd_cap=.05 if preflight else 0,max_tokens=768,thinking="disabled",
        system=system,extra_calculator_system=EXTRA,states=12,arms=2,max_actions=2,
        hashes={p.relative_to(ROOT).as_posix():sha(p) for p in paths}))


def verify(output):
    assert HERE==(output/"snapshot").resolve()
    for path,expected in load(output/"freeze.json")["hashes"].items():
        assert sha(ROOT/path)==expected,path


def state_cache(folder,state):
    cache=ToolCache(folder/"tool-cache.sqlite")
    for receipt in state["cache_receipts"]:
        cache.put(receipt)
    return cache


def query(cache,case,state,task):
    receipt=cache.get(state["source_id"],"full",task["a"])
    hit=receipt is not None
    cost=dict(source_read_bytes=0,scan_seconds=0.0)
    if not hit:
        table,cost=scan(case["sources"][state["source_id"]])
        receipt=dict(kind="full",source_id=state["source_id"],table=table)
        cache.put(receipt)
    return dict(receipt=receipt,value=calculate([receipt],task,state["source_id"]),backend_cache_hit=hit),cost


def preflight(output):
    from decimal import Decimal,localcontext
    verify(output)
    target=output/"preflight"
    target.mkdir()
    checks=0
    for total in range(13):
        for correct in range(total+1):
            for den in range(1,13):
                for num in range(den+1):
                    with localcontext() as context:
                        context.prec=80
                        truth=int(total>0 and Decimal(correct)*den>=Decimal(total)*num)
                    result=quality_check(selected_correct=correct,selected_total=total,
                        threshold_numerator=num,threshold_denominator=den)
                    assert result["value"]==truth and result["source_access"] is False
                    checks+=1
    assert checks==8190
    assert quality_check(selected_correct=99*10**100-1,selected_total=100*10**100,threshold_numerator=99,threshold_denominator=100)["value"]==0
    assert quality_check(selected_correct=99*10**100,selected_total=100*10**100,threshold_numerator=99,threshold_denominator=100)["value"]==1
    invalid=0
    for values in ((True,80,99,100),(81,80,99,100),(0,0,1,0),(-1,80,9,10)):
        try:
            quality_check(**dict(zip(("selected_correct","selected_total","threshold_numerator","threshold_denominator"),values)))
        except ValueError:
            invalid+=1
    assert invalid==4
    states={s["id"]:s for s in load(output/"states.json")}
    case=read_case(output/"cases/quality.case.json")
    results=[]
    for item in load(output/"schedule.json"):
        state=states[item["state"]]
        folder=target/f"{state['id']}-{item['arm']}"
        folder.mkdir()
        cache=state_cache(folder,state)
        payload=load(output/state["payload"])
        result,cost=query(cache,case,state,payload["task"])
        dump(folder/"tool.json",dict(result=result,cost=cost))
        # An explicit scripted submission; no model was queried.
        dump(folder/"delivery.json",dict(action="submit",value=result["value"],scripted=True))
        child=subprocess.run([sys.executable,"-B","-X","utf8",str(HERE/"read_cache.py"),str(folder/"tool-cache.sqlite")],
            capture_output=True,text=True,check=True,encoding="utf-8")
        restored=json.loads(child.stdout)
        assert any(r["source_id"]==state["source_id"] for r in restored["receipts"])
        dump(folder/"readback.json",restored)
        results.append(dict(state=state["id"],arm=item["arm"],value=result["value"],
            source_read_bytes=cost["source_read_bytes"],index=state["index"],new_process_read=True))
    # Reference runs independently, only after all scripted actions.
    gold=reference(case)
    assert all(r["value"]==gold[r["index"]] for r in results)
    dump(target/"actions.json",results)
    dump(target/"results.json",dict(status="complete",calculator_exhaustion=checks,invalid_inputs_rejected=invalid,
        large_integer_boundaries=2,scripted_deliveries=24,new_process_cache_reads=24,
        source_read_bytes=sum(r["source_read_bytes"] for r in results),external_model_calls=0,usd=0,
        scope="All planned snapshot branches, scripted query/delivery and real SQLite readback; not model outcomes."))
    print(json.dumps(load(target/"results.json")))


def model(output):
    verify(output)
    frozen=load(output/"freeze.json")
    assert frozen["stage"]=="models" and load(output/"prepaid-preflight.json")["status"]=="complete"
    target=output/"models"
    target.mkdir()
    (target/"api").mkdir()
    for line in (ROOT/".env.local").read_text(encoding="utf-8-sig").splitlines():
        name,sep,value=line.strip().partition("=")
        if sep and name=="DEEPSEEK_API_KEY":
            os.environ.setdefault(name,value.strip().strip('"').strip("'"))
    from metered_deepseek import DeepSeekClient
    metrics={}
    client=DeepSeekClient(target/"api",metrics,max_usd=frozen["usd_cap"],max_tokens=frozen["max_tokens"],thinking="disabled")
    case=read_case(output/"cases/quality.case.json")
    states={s["id"]:s for s in load(output/"states.json")}
    results=[]
    stopped=None
    calls=0
    for item in load(output/"schedule.json"):
        state=states[item["state"]]
        folder=target/f"{state['id']}-{item['arm']}"
        folder.mkdir()
        cache=state_cache(folder,state)
        original=load(output/state["payload"])
        payload=json.loads(json.dumps(original))
        system=frozen["system"]+(frozen["extra_calculator_system"] if item["arm"]=="calculator" else "")
        event=dict(state=state["id"],backend=state["backend"],index=state["index"],arm=item["arm"],
            source_id=state["source_id"],status="unfinished",query_calls=0,calculator_calls=0,
            calculator_errors=0,source_read_bytes=0,trace=[],initial_cache_receipts=len(state["cache_receipts"]),
            native_text_support="unassessed")
        try:
            for turn in range(2):
                if calls>=48:
                    raise RuntimeError("Frozen call cap reached")
                dump(folder/f"t{turn}-input.json",payload)
                calls+=1
                response=client.complete(system,payload,f"{calls:03}-{state['id']}-{item['arm']}-t{turn}")
                dump(folder/f"t{turn}-response.json",response)
                action=response.get("action")
                if action=="submit":
                    if type(response.get("value")) is not int or response["value"] not in (0,1):
                        raise ValueError("Invalid submitted gate")
                    event.update(status="submitted",value=response["value"],citations=response.get("citations",[]))
                    dump(folder/"delivery.json",response)
                    break
                if action=="abstain":
                    event["status"]="abstained"
                    break
                if action=="query":
                    event["query_calls"]+=1
                    result,cost=query(cache,case,state,payload["task"])
                    event["source_read_bytes"]+=cost["source_read_bytes"]
                elif action=="quality_check" and item["arm"]=="calculator":
                    event["calculator_calls"]+=1
                    try:
                        args={key:response[key] for key in ("selected_correct","selected_total","threshold_numerator","threshold_denominator")}
                        result=quality_check(**args)
                    except (ValueError,KeyError) as error:
                        result=dict(error=str(error),source_access=False)
                        event["calculator_errors"]+=1
                else:
                    raise ValueError("Unknown or unavailable action")
                step=dict(action=response,result=result)
                event["trace"].append(step)
                payload["tool_trace"].append(step)
                payload["remaining_actions"]=1-turn
        except Exception as error:
            event.update(status="interface_or_api_failure",error_type=type(error).__name__)
            stopped=dict(state=state["id"],arm=item["arm"],type=type(error).__name__,calls=calls)
            dump(target/"failure.json",stopped)
        dump(folder/"event.json",event)
        results.append(event)
        dump(target/"raw-results.json",results)
        dump(target/"metrics.json",metrics)
        if stopped:
            break
    gold=reference(case)
    for event in results:
        event["correct"]=event["status"]=="submitted" and event["value"]==gold[event["index"]]
        event["wrong"]=event["status"]=="submitted" and not event["correct"]
        valid=[s["result"] for s in event["trace"] if s["action"]["action"]=="quality_check" and "value" in s["result"]]
        event["submission_agrees_with_calculator"]=event["value"]==valid[-1]["value"] if valid and event["status"]=="submitted" else None
    by_arm={}
    for arm in ("control","calculator"):
        rows=[r for r in results if r["arm"]==arm]
        by_arm[arm]=dict(planned=12,executed=len(rows),correct=sum(r["correct"] for r in rows),
            wrong=sum(r["wrong"] for r in rows),abstained=sum(r["status"]=="abstained" for r in rows),
            unfinished=sum(r["status"] not in ("submitted","abstained") for r in rows),not_run=12-len(rows),
            query_calls=sum(r["query_calls"] for r in rows),calculator_calls=sum(r["calculator_calls"] for r in rows),
            calculator_errors=sum(r["calculator_errors"] for r in rows),source_read_bytes=sum(r["source_read_bytes"] for r in rows))
    paired=[]
    for state in states:
        rows={r["arm"]:r for r in results if r["state"]==state}
        if len(rows)==2:
            paired.append(dict(state=state,control_correct=rows["control"]["correct"],
                calculator_correct=rows["calculator"]["correct"],
                delta_correct=int(rows["calculator"]["correct"])-int(rows["control"]["correct"]),
                delta_query=rows["calculator"]["query_calls"]-rows["control"]["query_calls"]))
    dump(target/"reference-after-policy.json",gold)
    dump(target/"results.json",results)
    dump(target/"summary.json",dict(status="stopped" if stopped else "complete",calls=calls,arms=by_arm,
        paired=paired,primary_unit="Paired fixed states from one authored two-version history; not independent histories or a longitudinal policy rerun."))
    dump(target/"metrics.json",metrics)
    print(json.dumps(dict(summary=by_arm,calls=calls,metrics=metrics)))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","preflight","model"))
    parser.add_argument("output",type=Path)
    parser.add_argument("--preflight",type=Path)
    args=parser.parse_args()
    if args.mode=="prepare":
        prepare(args.output.resolve(),args.preflight.resolve() if args.preflight else None)
    else:
        {"preflight":preflight,"model":model}[args.mode](args.output.resolve())
