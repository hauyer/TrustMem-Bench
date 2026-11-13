"""Continue only unrun positions, retaining the model's task-local format failure."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
OLD=ROOT/"artifacts/research_decisions/20261113-confirmation-pilot-v3"
OUT=ROOT/"artifacts/research_decisions/20261113-confirmation-pilot-v4"
load=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def prepare():
    result=load(OLD/"models/results.json")
    assert result["executed_tasks"]==7 and result["calls"]==14
    event=load(OLD/"models/g00-coverage/free/s06/event.json")
    raw=load(OLD/"models/g00-coverage/free/s06/t0-response.json")
    assert event["status"]=="interface_failure" and raw==dict(type="query",scope="full")
    for p,h in load(OLD/"freeze.json")["hashes"].items():assert sha(ROOT/p)==h,p
    OUT.mkdir(exist_ok=False);shutil.copytree(OLD/"snapshot",OUT/"snapshot",ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(Path(__file__),OUT/"snapshot/resume_models.py")
    for name in ("cases.json","PROTOCOL.md","RESOURCE_ADMISSION.md","resource-admission.json","engineering-checks.json"):
        shutil.copyfile(OLD/name,OUT/name)
    shutil.copyfile(HERE/"CONTINUATION.md",OUT/"CONTINUATION.md")
    for name in ("preflight","native-smoke"):
        (OUT/name).mkdir();shutil.copyfile(OLD/name/"results.json",OUT/name/"results.json")
    paths=[*list((OUT/"snapshot").rglob("*.py")),OUT/"PROTOCOL.md",OUT/"CONTINUATION.md",OLD/"models/results.json"]
    paths += [p for p in (OLD/"models/g00-coverage").rglob("*") if p.is_file()]
    hashes=load(OLD/"freeze.json")["hashes"].copy()
    hashes.update({p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    (OUT/"freeze.json").write_text(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),hashes=hashes,parent=OLD.relative_to(ROOT).as_posix()),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    cfg=load(OLD/"paid-admission.json");cfg.update(calls_cap=585,usd_cap=2.90,freeze_sha256=sha(OUT/"freeze.json"),resume_parent=OLD.relative_to(ROOT).as_posix(),prior_processed_positions=7,prior_api_requests=15,prior_reserved_and_estimated_usd=.089909688)
    (OUT/"paid-admission.json").write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(continuation=str(OUT.relative_to(ROOT)),prior_positions_kept=7,positions_to_run=41,new_calls_cap=585,new_usd_cap=2.90)))


def run():
    assert HERE==(OUT/"snapshot").resolve()
    spec=importlib.util.spec_from_file_location("frozen_pilot_engine",HERE/"run.py");e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
    e.verify(OUT);cfg=load(OUT/"paid-admission.json")
    target=OUT/"models";target.mkdir(exist_ok=False);(target/"api").mkdir()
    for folder in (OLD/"models").glob("g*-*"):
        if folder.is_dir():shutil.copytree(folder,target/folder.name)
    e.dump(target/"execution-start.json",dict(at=datetime.now(timezone.utc).isoformat(),admission_sha256=sha(OUT/"paid-admission.json"),parent_processed_positions=7,new_positions_only=True))
    for line in (ROOT/".env.local").read_text(encoding="utf-8-sig").splitlines():
        name,sep,value=line.strip().partition("=")
        if sep and name=="DEEPSEEK_API_KEY":os.environ.setdefault(name,value.strip().strip('"').strip("'"))
    from metered_deepseek import DeepSeekClient
    metrics={};client=DeepSeekClient(target/"api",metrics,max_usd=cfg["usd_cap"],max_tokens=cfg["max_tokens"],thinking="disabled")
    counter=dict(calls=0,cap=cfg["calls_cap"]);completed=[];failure=None
    try:
        for gi,item in enumerate(cfg["schedule"]):
            record=item["case"];backend=item["backend"];case=e.read_case(ROOT/record["path"])
            folder=target/f"g{gi:02}-{backend}";folder.mkdir(exist_ok=True);initial=folder/"initial";initial.mkdir(exist_ok=True)
            table,cost=e.scan(case["sources"][case["initial_source"]]);summary=e.history(table,case["mechanism"],case["initial_source"])
            full=dict(kind="full",source_id=case["initial_source"],table=table);counter["branch"]=folder.name
            store=initial/("store" if backend=="mem0" else "memory.sqlite")
            if (initial/"response.json").exists():
                response=load(initial/"response.json")
            else:
                payload=dict(phase="bootstrap",historical_summary=summary,capture_full_available=True,historical_full_payload_bytes=len(e.canonical(full).encode()),authorized_archive_available=True,future_tasks_visible=False)
                e.dump(initial/"input.json",payload);response=client.complete(e.BOOTSTRAP,payload,e.next_call_id(counter,"bootstrap"));e.dump(initial/"response.json",response)
                if response.get("action") not in ("start","capture_full"):raise ValueError("Invalid bootstrap action")
                for receipt in [summary]+([full] if response["action"]=="capture_full" else []):
                    if backend=="mem0":e.native_store_save(store,receipt,client,counter)
                    else:e.save_plain(store,receipt,backend=="coverage")
            for mode in item["modes"]:
                branch=folder/mode;branch.mkdir(exist_ok=True);state=branch/("store" if backend=="mem0" else "memory.sqlite")
                if not state.exists():
                    if backend=="mem0":shutil.copytree(store,state)
                    else:shutil.copyfile(store,state)
                archive=e.ObservationArchive(branch/"archive");archive.put(full)
                cache_path=branch/"cache.sqlite"
                if cache_path.exists():
                    cache=object.__new__(e.ToolCache);cache.path=cache_path;cache.read_payload_bytes=0;cache.written_payload_bytes=0;cache.hits=0;cache.misses=0
                else:cache=e.ToolCache(cache_path)
                tools=e.CaseTools(case["sources"],cache,archive);counter["branch"]=folder.name+"-"+mode
                events=load(branch/"events.json") if (branch/"events.json").exists() else []
                start=len(events)
                for index in range(start,len(case["tasks"])):
                    entry=case["tasks"][index];notes=e.read_notes(state,branch/f"s{index:02}-read.json",backend)
                    def reader(system,payload):return client.complete(system,payload,e.next_call_id(counter,"reader"))
                    def save(receipt):
                        return e.native_store_save(state,receipt,client,counter) if backend=="mem0" else e.save_plain(state,receipt,backend=="coverage")
                    event=e.run_session(task=entry["request"],source_id=entry["source_id"],notes=notes,respond=reader,tools=tools,output=branch/f"s{index:02}",save=save,max_actions=4,mode=mode,session_id=f"s{index:02}")
                    events.append(event);e.dump(branch/"events.json",events)
                    e.dump(target/"progress.json",dict(group=gi,backend=backend,mode=mode,completed_in_stream=len(events),new_calls=counter["calls"],metrics=metrics))
                    print(json.dumps(dict(group=gi,backend=backend,mode=mode,task=index,status=event["status"],new_calls=counter["calls"])),flush=True)
                    decoded=(branch/f"s{index:02}"/f"t{event['actual_invocations']-1}-response.json").exists()
                    if event["status"]=="tool_failure" or (event["status"]=="interface_failure" and not decoded):raise RuntimeError("Transport/JSON/writer failure; stop continuation")
                completed.append(dict(group=gi,backend=backend,mode=mode,case=record["id"],path=branch.relative_to(OUT).as_posix(),events=len(events),bootstrap=response["action"],resumed_positions=start,common_history_scan=cost))
    except Exception as error:
        failure=dict(type=type(error).__name__,message=str(error)[:200],new_calls=counter["calls"]);e.dump(target/"failure.json",failure)
    # Cache the independent grading inputs only after all acting has stopped.
    truth_cache={};table_cache={};original_reference=e.reference;original_scan=e.scan
    def reference(case):
        if case["id"] not in truth_cache:truth_cache[case["id"]]=original_reference(case)
        return truth_cache[case["id"]]
    def scan(source,*args,**kwargs):
        if args or kwargs:return original_scan(source,*args,**kwargs)
        key=source["sha256"]
        if key not in table_cache:table_cache[key]=original_scan(source)
        return table_cache[key]
    e.reference=reference;e.scan=scan;scored=[]
    for gi,item in enumerate(cfg["schedule"]):
        case=e.read_case(ROOT/item["case"]["path"]);folder=target/f"g{gi:02}-{item['backend']}"
        for mode in item["modes"]:
            branch=folder/mode
            if (branch/"events.json").exists():scored.append(dict(group=gi,backend=item["backend"],mode=mode,case=item["case"]["id"],score=e.score_stream(case,branch,load(branch/"events.json"))))
    e.verify(OUT)
    result=dict(parent_planned_streams=12,parent_planned_positions=96,eligible_streams=6,eligible_positions=48,
        resource_excluded_positions=48,completed_streams=len(completed),completed=completed,scored=scored,
        executed_tasks=sum(s["score"]["executed"] for s in scored),prior_positions=7,new_api_requests=metrics["external_model_calls"],
        calls=counter["calls"],metrics=metrics,failure=failure,parent_api_requests=15,parent_reserved_and_estimated_usd=.089909688,
        scope="one public-history adaptive development continuation; task-local errors retained, no retry")
    e.dump(target/"results.json",result);e.dump(target/"metrics.json",metrics)
    print(json.dumps({k:v for k,v in result.items() if k not in ("completed","scored")}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage",choices=("prepare","run"));args=p.parse_args()
    {"prepare":prepare,"run":run}[args.stage]()
