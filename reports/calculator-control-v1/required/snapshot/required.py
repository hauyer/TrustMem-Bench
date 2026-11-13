"""Single ordinary instructed-use arm, preserving all original snapshot states."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT=Path.cwd()
HERE=Path(__file__).resolve().parent
PARENT=ROOT/"artifacts/research_decisions/20261113-same-evidence-calculator-reader-v1"
PREFLIGHT=ROOT/"artifacts/research_decisions/20261113-same-evidence-calculator-preflight-v1"
REQUIRED="""
Use this ordinary compute-before-submit policy for the first action: if shown current-source
notes determine the gate, call quality_check with the selected counts (or a sound decision-sufficient
bound) and the CURRENT TASK's threshold. If the shown notes do not determine the gate, call query.
Do not submit directly on the first action. On the second action submit your decision from the
tool result. You, not the calculator, must select the current source, derive the quantities and copy
the threshold. The calculator does not retrieve facts or validate that your inputs match evidence.
"""


def engine():
    spec=importlib.util.spec_from_file_location("frozen_calculator_engine",HERE/"engine.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(output):
    assert json.loads((PARENT/"models/summary.json").read_bytes())["status"]=="complete"
    assert json.loads((PREFLIGHT/"preflight/results.json").read_bytes())["status"]=="complete"
    output.mkdir(parents=True)
    shutil.copytree(PARENT/"snapshot",output/"snapshot")
    shutil.copyfile(PARENT/"snapshot/run.py",output/"snapshot/engine.py")
    shutil.copyfile(HERE/"required.py",output/"snapshot/required.py")
    shutil.copyfile(HERE/"REQUIRED_PROTOCOL.md",output/"PROTOCOL.md")
    for folder in ("inputs","cases"):
        shutil.copytree(PARENT/folder,output/folder)
    shutil.copyfile(PARENT/"states.json",output/"states.json")
    states=json.loads((output/"states.json").read_bytes())
    order=[s["id"] for s in states]
    random.Random(2026111316).shuffle(order)
    (output/"schedule.json").write_text(json.dumps(order,indent=2)+"\n",encoding="utf-8")
    parent=json.loads((PARENT/"freeze.json").read_bytes())
    files=[*list((output/"snapshot").rglob("*.py")),*list((output/"inputs").glob("*.json")),
        *list((output/"cases").glob("*")),output/"states.json",output/"schedule.json",output/"PROTOCOL.md",
        PARENT/"freeze.json",PARENT/"models/summary.json",PREFLIGHT/"preflight/results.json"]
    import hashlib
    cfg=dict(at=datetime.now(timezone.utc).isoformat(),arm="instructed_calculation",model_calls_cap=24,usd_cap=.025,
        max_tokens=768,thinking="disabled",system=parent["system"]+parent["extra_calculator_system"]+REQUIRED,
        adaptation_reason="Availability arm selected no calculator. This is a new ordinary-policy diagnostic, not a replacement or randomized cross-round causal claim.",
        hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (output/"freeze.json").write_text(json.dumps(cfg,indent=2)+"\n",encoding="utf-8")


def verify(output,e):
    assert HERE==(output/"snapshot").resolve()
    for name,identity in e.load(output/"freeze.json")["hashes"].items():
        assert e.sha(ROOT/name)==identity,name


def preflight(output):
    e=engine()
    verify(output,e)
    target=output/"preflight"
    target.mkdir()
    case=e.read_case(output/"cases/quality.case.json")
    states={s["id"]:s for s in e.load(output/"states.json")}
    results=[]
    for ident in e.load(output/"schedule.json"):
        state=states[ident]
        folder=target/ident
        folder.mkdir()
        cache=e.state_cache(folder,state)
        payload=e.load(output/state["payload"])
        obtained,cost=e.query(cache,case,state,payload["task"])
        task=payload["task"]
        table=obtained["receipt"]["table"]
        total=sum(w for cells in table.values() for b,w in cells.items() if int(b)>=task["cutoff"])
        correct=sum(w for b,w in table.get(task["a"],{}).items() if int(b)>=task["cutoff"])
        calculated=e.quality_check(selected_correct=correct,selected_total=total,
            threshold_numerator=task["numerator"],threshold_denominator=task["denominator"])
        assert calculated["value"]==obtained["value"]
        e.dump(folder/"delivery.json",dict(action="submit",value=calculated["value"],scripted=True))
        child=subprocess.run([sys.executable,"-B","-X","utf8",str(HERE/"read_cache.py"),str(folder/"tool-cache.sqlite")],
            check=True,capture_output=True,text=True,encoding="utf-8")
        restored=json.loads(child.stdout)
        assert any(r["source_id"]==state["source_id"] for r in restored["receipts"])
        results.append(dict(state=ident,index=state["index"],value=calculated["value"],cost=cost,
            new_process_read=True))
    gold=e.reference(case)
    assert all(r["value"]==gold[r["index"]] for r in results)
    e.dump(target/"results.json",dict(status="complete",scripted_deliveries=12,new_process_reads=12,
        zero_api=True,source_read_bytes=sum(r["cost"]["source_read_bytes"] for r in results),actions=results))
    print(json.dumps(dict(preflight="complete",scripted_deliveries=12,api_calls=0)))


def model(output):
    e=engine()
    verify(output,e)
    cfg=e.load(output/"freeze.json")
    preflight_path=output/"preflight/results.json"
    assert e.load(preflight_path)["status"]=="complete"
    target=output/"models"
    target.mkdir()
    e.dump(target/"paid-admission.json",dict(preflight_sha256=e.sha(preflight_path),freeze_sha256=e.sha(output/"freeze.json"),
        at=datetime.now(timezone.utc).isoformat(),model_calls_cap=24,usd_cap=.025))
    (target/"api").mkdir()
    for line in (ROOT/".env.local").read_text(encoding="utf-8-sig").splitlines():
        name,sep,value=line.strip().partition("=")
        if sep and name=="DEEPSEEK_API_KEY":
            os.environ.setdefault(name,value.strip().strip('"').strip("'"))
    from metered_deepseek import DeepSeekClient
    metrics={}
    client=DeepSeekClient(target/"api",metrics,max_usd=.025,max_tokens=768,thinking="disabled")
    case=e.read_case(output/"cases/quality.case.json")
    states={s["id"]:s for s in e.load(output/"states.json")}
    events=[]
    calls=0
    stopped=None
    for ident in e.load(output/"schedule.json"):
        state=states[ident]
        folder=target/ident
        folder.mkdir()
        cache=e.state_cache(folder,state)
        payload=e.load(output/state["payload"])
        event=dict(state=ident,backend=state["backend"],index=state["index"],status="unfinished",trace=[],
            query_calls=0,calculator_calls=0,calculator_errors=0,source_read_bytes=0,first_action=None,
            complies_with_first_tool_policy=None,native_text_support="unassessed")
        try:
            for turn in range(2):
                if calls>=24:
                    raise RuntimeError("Frozen call cap reached")
                e.dump(folder/f"t{turn}-input.json",payload)
                calls+=1
                response=client.complete(cfg["system"],payload,f"{calls:03}-{ident}-required-t{turn}")
                e.dump(folder/f"t{turn}-response.json",response)
                action=response.get("action")
                if turn==0:
                    event["first_action"]=action
                    event["complies_with_first_tool_policy"]=action in ("quality_check","query")
                if action=="submit":
                    if type(response.get("value")) is not int or response["value"] not in (0,1):
                        raise ValueError("Invalid submitted gate")
                    event.update(status="submitted",value=response["value"],citations=response.get("citations",[]))
                    e.dump(folder/"delivery.json",response)
                    break
                if action=="abstain":
                    event["status"]="abstained"
                    break
                if action=="query":
                    event["query_calls"]+=1
                    result,cost=e.query(cache,case,state,payload["task"])
                    event["source_read_bytes"]+=cost["source_read_bytes"]
                elif action=="quality_check":
                    event["calculator_calls"]+=1
                    try:
                        result=e.quality_check(**{key:response[key] for key in ("selected_correct","selected_total","threshold_numerator","threshold_denominator")})
                    except (ValueError,KeyError) as error:
                        result=dict(error=str(error),source_access=False)
                        event["calculator_errors"]+=1
                else:
                    raise ValueError("Unknown action")
                step=dict(action=response,result=result)
                event["trace"].append(step)
                payload["tool_trace"].append(step)
                payload["remaining_actions"]=1-turn
        except Exception as error:
            event.update(status="interface_or_api_failure",error_type=type(error).__name__)
            stopped=dict(state=ident,error_type=type(error).__name__,calls=calls)
            e.dump(target/"failure.json",stopped)
        events.append(event)
        e.dump(folder/"event.json",event)
        e.dump(target/"raw-results.json",events)
        e.dump(target/"metrics.json",metrics)
        if stopped:
            break
    gold=e.reference(case)
    for event in events:
        event["correct"]=event["status"]=="submitted" and event["value"]==gold[event["index"]]
        event["wrong"]=event["status"]=="submitted" and not event["correct"]
        valid=[s["result"] for s in event["trace"] if s["action"]["action"]=="quality_check" and "value" in s["result"]]
        event["submission_agrees_with_calculator"]=event["value"]==valid[-1]["value"] if valid and event["status"]=="submitted" else None
    e.dump(target/"reference-after-policy.json",gold)
    e.dump(target/"results.json",events)
    e.dump(target/"summary.json",dict(status="stopped" if stopped else "complete",planned=12,executed=len(events),
        not_run=12-len(events),calls=calls,correct=sum(r["correct"] for r in events),wrong=sum(r["wrong"] for r in events),
        query_calls=sum(r["query_calls"] for r in events),calculator_calls=sum(r["calculator_calls"] for r in events),
        calculator_errors=sum(r["calculator_errors"] for r in events),source_read_bytes=sum(r["source_read_bytes"] for r in events),
        first_tool_compliance=sum(r["complies_with_first_tool_policy"] is True for r in events),
        scope="Adaptive ordinary policy qualification on all original12 states; not a randomized cross-round causal estimate."))
    e.dump(target/"metrics.json",metrics)
    print(json.dumps(dict(summary=e.load(target/"summary.json"),metrics=metrics)))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","preflight","model"))
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    {"prepare":prepare,"preflight":preflight,"model":model}[args.mode](args.output.resolve())
