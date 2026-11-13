"""Fair bootstrap/archive qualification and one bounded real public-data pilot."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT=Path.cwd();HERE=Path(__file__).resolve().parent;REPO=ROOT/"github-release/TrustMem-Bench"
sys.path.insert(0,str(HERE if (HERE/"trustmem_runtime").is_dir() else REPO))
from trustmem_runtime.reader import run_session,CaseTools,note_receipts
from trustmem_runtime.archive import ObservationArchive
from trustmem_runtime.data import canonical,scan,history
from trustmem_runtime.evidence import calculate
from trustmem_runtime.grading import reference
from trustmem_runtime.run import read_case
from trustmem_runtime.tool_cache import ToolCache
from trustmem_diagnostics.adapters import SQLiteMemory
from trustmem_diagnostics.authentication import assess_authenticated

CAND=ROOT/"artifacts/research_decisions/20261113-confirmation-selection-v1"
EMBED=ROOT/"memory-revocation-research/native-embedding-cache/models/models--qdrant--bge-small-en-v1.5-onnx-q/snapshots/aa8f8b060edb00e03bfdd08813a2949946c8ba55"
BOOTSTRAP="""Choose what to retain from the completed historical source scan before any future task is known.
Return exactly one JSON object: {"action":"start"} to retain the ordinary historical summary, or
{"action":"capture_full"} to additionally retain the full observation available from that same scan.
The complete old observation also remains in an authorized archive, accessible in later sessions
by recover(archive_id). Archive retrieval and memory transport/storage have explicit costs.
No future task is visible. Full retention need not scan the source again. Do not return other text."""


def load(p):return json.loads(p.read_bytes())


def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);snap=out/"snapshot";snap.mkdir()
    for name in ("trustmem_runtime","trustmem_diagnostics"):
        shutil.copytree(REPO/name,snap/name,ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(HERE/"run.py",snap/"run.py")
    shutil.copyfile(REPO/"examples/metered_deepseek.py",snap/"metered_deepseek.py")
    shutil.copyfile(HERE/"PROTOCOL.md",out/"PROTOCOL.md")
    candidate=load(CAND/"case-admission.json")
    paths=[out/"PROTOCOL.md",*snap.rglob("*.py"),CAND/"case-admission.json",*list((REPO/"tests").glob("test_archive_authentication.py"))]
    records=[]
    for index,(name,digest) in enumerate(candidate["cases"].items()):
        path=ROOT/name;assert sha(path)==digest
        case=read_case(path);paths.append(path)
        paths += [Path(s["path"]) for s in case["sources"].values()]
        records.append(dict(index=index,path=name,id=case["id"],mechanism=case["mechanism"],public="public-cases" in path.parts))
    dump(out/"cases.json",records);paths.append(out/"cases.json")
    env=ROOT/"memory-revocation-research/.venv-mem0-probe/Lib/site-packages"
    paths += [env/n for n in ("mem0/memory/main.py","mem0/configs/prompts.py","mem0/memory/utils.py")]
    paths += [p for p in EMBED.rglob("*") if p.is_file()]
    dump(out/"freeze.json",dict(at=datetime.now(timezone.utc).isoformat(),phase="zero-api-qualification",model_calls_cap=0,usd_cap=0,
        hashes={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))},records=records))
    print(json.dumps(dict(prepared=str(out.relative_to(ROOT)),cases=len(records),api_calls=0)),flush=True)


def verify(out):
    assert HERE==(out/"snapshot").resolve(),"Use the frozen snapshot"
    for p,h in load(out/"freeze.json")["hashes"].items():assert sha(ROOT/p)==h,p


def save_plain(path,receipt,coverage=False):
    store=SQLiteMemory(path)
    if coverage:
        for row in store.search(""):
            for obj in note_receipts(row.text):
                if obj["source_id"]==receipt["source_id"]:
                    if obj["kind"]=="full":return dict(retained=row.id)
                    if receipt["kind"]=="full":store.delete(row.id)
    row=store.add(canonical(receipt));return dict(id=row.id,revision=row.revision)


def read_notes(path,target,backend):
    child=subprocess.run([sys.executable,"-B","-X","utf8",str(HERE/"run.py"),"read","--output",str(path),"--backend",backend],
        capture_output=True,text=True,encoding="utf-8",check=False)
    dump(target,dict(returncode=child.returncode,stdout=child.stdout,stderr=child.stderr))
    if child.returncode:raise RuntimeError("Native/local fresh-process read failed")
    return json.loads(child.stdout)


def exact_reader(system,p):
    trace=p["tool_trace"]
    if not trace:
        receipts=[r for note in p["retrieved_notes"] for r in note_receipts(note["memory"])]
        value=calculate(receipts,p["task"],p["current_source_id"])
        if value is not None:return dict(action="submit",value=value)
        old=next((r for r in p["archive_catalog"] if r["source_id"]==p["current_source_id"] and r["kind"]=="full"),None)
        return dict(action="recover",archive_id=old["id"]) if old else dict(action="query",scope="full")
    last=trace[-1]
    if last["action"]["action"] in ("query","recover"):
        return dict(action="save",receipt_id=last["result"]["receipt_id"])
    if last["action"]["action"]=="save":
        return dict(action="submit",value=trace[0]["result"]["value"])
    raise ValueError("Unexpected ordinary-policy state")


def score_stream(case,folder,events):
    truth=reference(case)
    tables={sid:scan(source)[0] for sid,source in case["sources"].items()}
    rows=[]
    for index,event in enumerate(events):
        inputs=[load(p) for p in sorted((folder/f"s{index:02}").glob("t*-input.json"))]
        authenticated=[]
        for payload in inputs:
            receipts=[r for note in payload["retrieved_notes"] for r in note_receipts(note["memory"])]
            receipts += [s["result"]["receipt"] for s in payload["tool_trace"] if "receipt" in s.get("result",{})]
            authenticated.append(assess_authenticated(receipts=receipts,tables=tables,task=payload["task"],source_id=payload["current_source_id"],unassessed_text=bool(payload["retrieved_notes"])))
        expected=truth[index]
        row=dict(index=index,status=event["status"],value=event["value"],expected=expected,
            correct=event["status"]=="submitted" and event["value"]==expected,
            wrong=event["status"]=="submitted" and event["value"]!=expected,
            authentication=authenticated,source_read_bytes=event["source_read_bytes"],archive_read_payload_bytes=event["archive_read_payload_bytes"])
        rows.append(row)
    result=dict(planned=len(case["tasks"]),executed=len(events),not_run=len(case["tasks"])-len(events),
        correct=sum(r["correct"] for r in rows),wrong=sum(r["wrong"] for r in rows),
        unfinished=sum(r["status"] not in ("submitted","abstained") for r in rows),abstained=sum(r["status"]=="abstained" for r in rows),
        source_read_bytes=sum(e["source_read_bytes"] for e in events),archive_read_payload_bytes=sum(e["archive_read_payload_bytes"] for e in events),rows=rows)
    dump(folder/"score.json",result);return result


def preflight(out):
    verify(out);target=out/"preflight";target.mkdir(exist_ok=False)
    rows=[]
    for record in load(out/"cases.json"):
        case=read_case(ROOT/record["path"])
        table,cost=scan(case["sources"][case["initial_source"]])
        initial=history(table,case["mechanism"],case["initial_source"])
        full=dict(kind="full",source_id=case["initial_source"],table=table)
        for policy in ("lazy","eager"):
            folder=target/f"c{record['index']:02}-{policy}";folder.mkdir()
            archive=ObservationArchive(folder/"archive");archive.put(full)
            path=folder/"memory.sqlite";save_plain(path,initial)
            if policy=="eager":save_plain(path,full)
            tools=CaseTools(case["sources"],ToolCache(folder/"tool-cache.sqlite"),archive)
            events=[]
            for index,entry in enumerate(case["tasks"]):
                notes=read_notes(path,folder/f"s{index:02}-read.json","verbatim")
                events.append(run_session(task=entry["request"],source_id=entry["source_id"],notes=notes,respond=exact_reader,
                    tools=tools,output=folder/f"s{index:02}",save=lambda r:save_plain(path,r),max_actions=4,mode="free",session_id=f"s{index:02}"))
            score=score_stream(case,folder,events)
            assert score["correct"]==8
            row=dict(case=record["id"],public=record["public"],policy=policy,correct=score["correct"],tasks=8,
                source_read_bytes=score["source_read_bytes"],archive_read_payload_bytes=score["archive_read_payload_bytes"],
                bootstrap_full_payload_bytes=len(canonical(full).encode()),bootstrap_summary_bytes=len(canonical(initial).encode()),
                constant_zero_correct=sum(r["expected"]==0 for r in score["rows"]),common_history_scan=cost)
            rows.append(row);print(json.dumps(row),flush=True)
    verify(out)
    dump(target/"results.json",dict(rows=rows,tasks=160,correct=160,api_calls=0,usd=0,scope="ordinary qualification on all10 frozen candidate histories; not model effects"))


def native_store_save(path,receipt,client=None,counter=None):
    from trustmem_diagnostics.native_mem0 import Mem0Store
    body=canonical(receipt)
    local=[]
    def transport(messages):
        if client is None:
            local.append(messages)
            if counter is not None:counter.append(dict(scripted=True,messages=messages))
            return json.dumps(dict(facts=[body])) if len(local)==1 else json.dumps(dict(memory=[dict(id="0",text=body,event="ADD")]))
    if client is not None:
        def transport(messages):return client.complete_messages(messages,next_call_id(counter,"writer"),return_raw=True)["choices"][0]["message"]["content"]
    store=Mem0Store(path,EMBED,transport)
    try:return store.add(body,infer=True,metadata=dict(stage="confirmation-pilot"))
    finally:store.close()


def next_call_id(counter,role):
    if counter["calls"]>=counter["cap"]:raise RuntimeError("Frozen API-call cap reached")
    counter["calls"]+=1
    return f"{counter['calls']:04}-{counter.get('branch','bootstrap')}-{role}"


def native_smoke(out):
    verify(out);target=out/"native-smoke";target.mkdir(exist_ok=False)
    from trustmem_runtime.fixtures import build
    build(target/"cases");case=read_case(target/"cases/quality.case.json")
    table,cost=scan(case["sources"][case["initial_source"]]);full=dict(kind="full",source_id=case["initial_source"],table=table)
    callbacks=[];store=target/"initial-store"
    native_store_save(store,full,counter=callbacks)
    outputs=[]
    for mode in ("free","tool_first"):
        folder=target/mode;folder.mkdir();shutil.copytree(store,folder/"store")
        archive=ObservationArchive(folder/"archive");ident=archive.put(full)
        notes=read_notes(folder/"store",folder/"read.json","mem0")
        actions=iter([dict(action="recover",archive_id=ident),dict(action="submit",value=0)])
        task=case["tasks"][1]
        event=run_session(task=task["request"],source_id=task["source_id"],notes=notes,respond=lambda *_:next(actions),
            tools=CaseTools(case["sources"],ToolCache(folder/"cache.sqlite"),archive),output=folder/"s00",max_actions=4,mode=mode)
        assert event["status"]=="submitted" and event["value"]==0 and event["source_read_bytes"]==0
        outputs.append(dict(mode=mode,source_read_bytes=0,archive_read_payload_bytes=event["archive_read_payload_bytes"]))
    verify(out);dump(target/"results.json",dict(qualified=True,scripted_native_writer_callbacks=len(callbacks),branches=outputs,api_calls=0,usd=0))


def admit(out):
    verify(out)
    assert load(out/"preflight/results.json")["correct"]==160
    assert load(out/"native-smoke/results.json")["qualified"]
    public=[r for r in load(out/"cases.json") if r["public"]];assert len(public)==2
    rng=random.Random(202611131624);schedule=[]
    for record in public:
        backends=["verbatim","coverage","mem0"];rng.shuffle(backends)
        for backend in backends:
            modes=["free","tool_first"];rng.shuffle(modes)
            schedule.append(dict(case=record,backend=backend,modes=modes))
    dump(out/"paid-admission.json",dict(at=datetime.now(timezone.utc).isoformat(),model="deepseek-flash",thinking="disabled",max_tokens=8192,
        calls_cap=600,usd_cap=3.0,normal_actions=4,planned_task_positions=96,planned_streams=12,schedule=schedule,
        qualification_sha256=sha(out/"preflight/results.json"),native_sha256=sha(out/"native-smoke/results.json"),freeze_sha256=sha(out/"freeze.json"),
        pricing_url="https://api-docs.deepseek.com/quick_start/pricing/",rates_usd_per_million=dict(cache_hit=.006,cache_miss=.30,output=1.20)))
    print(json.dumps(dict(admitted=True,task_positions=96,calls_cap=600,usd_cap=3.0)),flush=True)


def models(out):
    verify(out);cfg=load(out/"paid-admission.json")
    assert cfg["qualification_sha256"]==sha(out/"preflight/results.json") and cfg["native_sha256"]==sha(out/"native-smoke/results.json")
    target=out/"models";target.mkdir(exist_ok=False);(target/"api").mkdir()
    dump(target/"execution-start.json",dict(at=datetime.now(timezone.utc).isoformat(),paid_admission_sha256=sha(out/"paid-admission.json"),calls_cap=cfg["calls_cap"],usd_cap=cfg["usd_cap"]))
    for line in (ROOT/".env.local").read_text(encoding="utf-8-sig").splitlines():
        name,sep,value=line.strip().partition("=")
        if sep and name=="DEEPSEEK_API_KEY":os.environ.setdefault(name,value.strip().strip('"').strip("'"))
    from metered_deepseek import DeepSeekClient
    metrics={};client=DeepSeekClient(target/"api",metrics,max_usd=cfg["usd_cap"],max_tokens=cfg["max_tokens"],thinking="disabled")
    counter=dict(calls=0,cap=cfg["calls_cap"]);completed=[];failure=None
    try:
        for group_index,item in enumerate(cfg["schedule"]):
            record=item["case"];backend=item["backend"];case=read_case(ROOT/record["path"])
            folder=target/f"g{group_index:02}-{backend}";folder.mkdir();initial_folder=folder/"initial";initial_folder.mkdir()
            table,cost=scan(case["sources"][case["initial_source"]]);summary=history(table,case["mechanism"],case["initial_source"])
            full=dict(kind="full",source_id=case["initial_source"],table=table)
            counter["branch"]=folder.name
            payload=dict(phase="bootstrap",historical_summary=summary,capture_full_available=True,
                historical_full_payload_bytes=len(canonical(full).encode()),authorized_archive_available=True,future_tasks_visible=False)
            dump(initial_folder/"input.json",payload)
            response=client.complete(BOOTSTRAP,payload,next_call_id(counter,"bootstrap"));dump(initial_folder/"response.json",response)
            if response.get("action") not in ("start","capture_full"):raise ValueError("Invalid bootstrap action")
            store=initial_folder/("store" if backend=="mem0" else "memory.sqlite")
            selected=[summary]+([full] if response["action"]=="capture_full" else [])
            for receipt in selected:
                if backend=="mem0":native_store_save(store,receipt,client,counter)
                else:save_plain(store,receipt,backend=="coverage")
            for mode in item["modes"]:
                branch=folder/mode;branch.mkdir();state_path=branch/("store" if backend=="mem0" else "memory.sqlite")
                if backend=="mem0":shutil.copytree(store,state_path)
                else:shutil.copyfile(store,state_path)
                archive=ObservationArchive(branch/"archive");archive.put(full)
                tools=CaseTools(case["sources"],ToolCache(branch/"cache.sqlite"),archive)
                counter["branch"]=folder.name+"-"+mode;events=[]
                for index,entry in enumerate(case["tasks"]):
                    notes=read_notes(state_path,branch/f"s{index:02}-read.json",backend)
                    def reader(system,payload):return client.complete(system,payload,next_call_id(counter,"reader"))
                    def save(receipt):
                        if backend=="mem0":return native_store_save(state_path,receipt,client,counter)
                        return save_plain(state_path,receipt,backend=="coverage")
                    event=run_session(task=entry["request"],source_id=entry["source_id"],notes=notes,respond=reader,
                        tools=tools,output=branch/f"s{index:02}",save=save,max_actions=4,mode=mode,session_id=f"s{index:02}")
                    events.append(event);dump(branch/"events.json",events)
                    dump(target/"progress.json",dict(group=group_index,backend=backend,mode=mode,completed_in_stream=len(events),calls=counter["calls"],metrics=metrics))
                    print(json.dumps(dict(group=group_index,backend=backend,mode=mode,task=index,status=event["status"],calls=counter["calls"])),flush=True)
                    if event["status"] in ("interface_failure","tool_failure"):raise RuntimeError("Preserved reader/writer failure; stop batch")
                completed.append(dict(group=group_index,backend=backend,mode=mode,case=record["id"],path=branch.relative_to(out).as_posix(),events=len(events),bootstrap=response["action"],common_history_scan=cost))
    except Exception as error:
        failure=dict(type=type(error).__name__,message=str(error)[:200],calls=counter["calls"])
        dump(target/"failure.json",failure)
    # No gold was used during acting; score every stream that has recorded events now.
    scored=[]
    for group_index,item in enumerate(cfg["schedule"]):
        case=read_case(ROOT/item["case"]["path"]);folder=target/f"g{group_index:02}-{item['backend']}"
        for mode in item["modes"]:
            branch=folder/mode
            if (branch/"events.json").exists():
                score=score_stream(case,branch,load(branch/"events.json"))
                scored.append(dict(group=group_index,backend=item["backend"],mode=mode,case=item["case"]["id"],score=score))
    verify(out)
    result=dict(planned_streams=12,planned_task_positions=96,completed_streams=len(completed),
        executed_tasks=sum(s["score"]["executed"] for s in scored),completed=completed,scored=scored,failure=failure,
        calls=counter["calls"],metrics=metrics,scope="two public histories, one joint-count mechanism, bounded pilot only")
    dump(target/"results.json",result);dump(target/"metrics.json",metrics)
    print(json.dumps(dict(completed_streams=len(completed),executed_tasks=result["executed_tasks"],calls=counter["calls"],failure=failure,metrics=metrics)),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("stage",choices=("prepare","preflight","native","admit","models","read"));p.add_argument("--output",type=Path,required=True);p.add_argument("--backend",default="verbatim");a=p.parse_args()
    if a.stage=="read":
        if a.backend=="mem0":
            from trustmem_diagnostics.native_mem0 import Mem0Store
            store=Mem0Store(a.output,EMBED)
            try:notes=store.search("workflow verified source observations",limit=5)["results"]
            finally:store.close()
        else:notes=[dict(id=r.id,memory=r.text,revision=r.revision) for r in SQLiteMemory(a.output).search("")]
        print(json.dumps(notes));return
    {"prepare":prepare,"preflight":preflight,"native":native_smoke,"admit":admit,"models":models}[a.stage](a.output.resolve())


if __name__=="__main__":main()
