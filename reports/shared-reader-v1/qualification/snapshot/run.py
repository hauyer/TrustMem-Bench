"""Qualify a common reader across real local persistence and the native SDK."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path.cwd()
HERE=Path(__file__).resolve().parent
REPO=ROOT/"github-release/TrustMem-Bench"
sys.path.insert(0,str(HERE if (HERE/"trustmem_runtime").is_dir() else REPO))
from trustmem_runtime.reader import run_session,CaseTools,note_receipts
from trustmem_runtime.data import canonical,scan,history
from trustmem_runtime.fixtures import build
from trustmem_runtime.grading import reference
from trustmem_runtime.run import read_case
from trustmem_runtime.tool_cache import ToolCache
from trustmem_diagnostics.adapters import SQLiteMemory

EMBED=ROOT/"memory-revocation-research/native-embedding-cache/models/models--qdrant--bge-small-en-v1.5-onnx-q/snapshots/aa8f8b060edb00e03bfdd08813a2949946c8ba55"


def load(path):return json.loads(path.read_bytes())


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    snap=out/"snapshot";snap.mkdir()
    shutil.copyfile(HERE/"run.py",snap/"run.py")
    shutil.copyfile(HERE/"PROTOCOL.md",out/"PROTOCOL.md")
    for name in ("trustmem_runtime","trustmem_diagnostics"):
        shutil.copytree(REPO/name,snap/name,ignore=shutil.ignore_patterns("__pycache__"))
    build(out/"cases")
    paths=[out/"PROTOCOL.md",*snap.rglob("*.py"),*list((out/"cases").iterdir()),*list((REPO/"tests").glob("test_reader.py"))]
    native_env=ROOT/"memory-revocation-research/.venv-mem0-probe/Lib/site-packages"
    for name in ("mem0/memory/main.py","mem0/configs/prompts.py","mem0/memory/utils.py"):
        paths.append(native_env/name)
    paths.extend(p for p in EMBED.rglob("*") if p.is_file())
    dump(out/"freeze.json",dict(at=datetime.now(timezone.utc).isoformat(),model_calls_cap=0,usd_cap=0,
        reader_contract="native-reader-1",new_normal_actions=4,scripted_ordinary_tasks=64,scripted_native_tasks=6,
        hashes={p.relative_to(ROOT).as_posix():sha(p) for p in paths}))
    print(json.dumps(dict(prepared=str(out.relative_to(ROOT)),frozen_files=len(paths))))


def verify(out):
    assert HERE==(out/"snapshot").resolve(),"Run frozen snapshot"
    for name,value in load(out/"freeze.json")["hashes"].items():assert sha(ROOT/name)==value,name


def child_read(store,output,native=False,query=""):
    cmd=[sys.executable,"-B","-X","utf8",str(HERE/"run.py"),"read","--output",str(store)]
    if native:cmd += ["--native","--query",query]
    child=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",check=False)
    dump(output,dict(command=cmd,returncode=child.returncode,stdout=child.stdout,stderr=child.stderr))
    if child.returncode:raise RuntimeError("Fresh-process retrieval failed")
    return json.loads(child.stdout)


def ordinary_save(path,receipt,coverage=False):
    store=SQLiteMemory(path)
    if coverage:
        old=store.search("")
        # A current-source full observation dominates weaker same-source objects.
        same=[r for r in old for obj in note_receipts(r.text) if obj["source_id"]==receipt["source_id"] and obj["kind"]=="full"]
        if same:return dict(retained_existing_full=same[0].id)
        if receipt["kind"]=="full":
            for obj in old:
                parsed=note_receipts(obj.text)
                if parsed and all(r["source_id"]==receipt["source_id"] for r in parsed):store.delete(obj.id)
    record=store.add(canonical(receipt))
    return dict(id=record.id,revision=record.revision)


def scripted_reader(system,payload):
    trace=payload["tool_trace"]
    if not trace:return dict(action="calculate",evidence=[n["id"] for n in payload["retrieved_notes"]])
    last=trace[-1]
    if last["action"]["action"]=="calculate":
        if last["result"].get("value") is not None:return dict(action="submit",value=last["result"]["value"])
        return dict(action="query",scope="full")
    if last["action"]["action"]=="query":return dict(action="save",receipt_id=last["result"]["receipt_id"])
    if last["action"]["action"]=="save":
        query=next(s for s in trace if s["action"]["action"]=="query")
        return dict(action="submit",value=query["result"]["value"])
    raise ValueError("Unexpected scripted-reader state")


def ordinary(out):
    verify(out);target=out/"ordinary";target.mkdir(exist_ok=False)
    runs=[]
    for mechanism in ("cross","threshold","range","quality"):
        case=read_case(out/f"cases/{mechanism}.case.json")
        table,cost=scan(case["sources"][case["initial_source"]])
        initial=history(table,mechanism,case["initial_source"])
        for backend in ("verbatim","coverage"):
            folder=target/f"{mechanism}-{backend}";folder.mkdir()
            path=folder/"memory.sqlite"
            ordinary_save(path,initial,backend=="coverage")
            tools=CaseTools(case["sources"],ToolCache(folder/"tool-cache.sqlite"))
            events=[]
            for index,entry in enumerate(case["tasks"]):
                notes=child_read(path,folder/f"s{index:02}-read.json")
                event=run_session(task=entry["request"],source_id=entry["source_id"],notes=notes,respond=scripted_reader,
                    tools=tools,output=folder/f"s{index:02}",save=lambda r:ordinary_save(path,r,backend=="coverage"),
                    max_actions=4,mode="tool_first",session_id=f"s{index:02}")
                events.append(event)
            truth=reference(case)
            for index,event in enumerate(events):event["correct"]=event["status"]=="submitted" and event["value"]==truth[index]
            assert all(e["correct"] for e in events)
            row=dict(mechanism=mechanism,backend=backend,tasks=len(events),correct=sum(e["correct"] for e in events),
                fresh_process_reads=len(events),query_calls=sum(e["query_calls"] for e in events),
                actual_saves=sum(e["save_calls"] for e in events),source_read_bytes=sum(e["source_read_bytes"] for e in events),
                common_history_scan=cost,cache_hits=tools.cache.hits,cache_misses=tools.cache.misses,events=events)
            runs.append(row);dump(folder/"results.json",row)
            print(json.dumps({k:v for k,v in row.items() if k not in ("events","common_history_scan")}),flush=True)
    verify(out)
    result=dict(runs=runs,tasks=64,correct=64,new_process_reads=64,api_calls=0,usd=0,
        scope="scripted qualification on old engineering fixtures; no model effect or independent histories")
    dump(target/"results.json",result)


def native(out):
    verify(out);target=out/"native";target.mkdir(exist_ok=False)
    from trustmem_diagnostics.native_mem0 import Mem0Store
    from importlib.metadata import version
    case=read_case(out/"cases/quality.case.json")
    table,cost=scan(case["sources"][case["initial_source"]])
    initial=history(table,"quality",case["initial_source"])
    store_path=target/"store";calls=[]
    def save(receipt):
        body=canonical(receipt);local=[]
        def writer(messages):
            local.append(messages);calls.append(dict(messages=messages,scripted=True))
            if len(local)==1:return json.dumps(dict(facts=[body]))
            if len(local)==2:return json.dumps(dict(memory=[dict(id="0",text=body,event="ADD")]))
            raise RuntimeError("Unexpected native writer callback count")
        store=Mem0Store(store_path,EMBED,writer)
        try:result=store.add(body,infer=True,metadata=dict(stage="shared-reader-scripted-preflight"))
        finally:store.close()
        assert len(local)==2
        return result
    save(initial)
    tools=CaseTools(case["sources"],ToolCache(target/"tool-cache.sqlite"))
    events=[]
    for index in (0,1,2,4,5,7):
        entry=case["tasks"][index]
        notes=child_read(store_path,target/f"s{index:02}-read.json",native=True,query="quality workflow source "+entry["source_id"])
        event=run_session(task=entry["request"],source_id=entry["source_id"],notes=notes,respond=scripted_reader,
            tools=tools,output=target/f"s{index:02}",save=save,max_actions=4,mode="tool_first",session_id=f"s{index:02}")
        event["case_index"]=index;events.append(event)
        dump(target/"progress.json",dict(completed=len(events),scripted_writer_callbacks=len(calls)))
        print(json.dumps(dict(native_completed=len(events),case_index=index,status=event["status"])),flush=True)
    truth=reference(case)
    for event in events:event["correct"]=event["status"]=="submitted" and event["value"]==truth[event["case_index"]]
    assert all(e["correct"] for e in events)
    verify(out)
    dump(target/"writer-callbacks.json",calls)
    dump(target/"results.json",dict(tasks=6,correct=6,new_process_native_searches=6,
        scripted_writer_callbacks=len(calls),infer_true=True,api_calls=0,usd=0,common_history_scan=cost,
        source_read_bytes=sum(e["source_read_bytes"] for e in events),events=events,
        versions={k:version(k) for k in ("mem0ai","qdrant-client","fastembed","pydantic")},
        scope="actual native SDK with scripted writer/reader responses, not natural model behavior"))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("prepare","ordinary","native","read"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--native",action="store_true")
    parser.add_argument("--query",default="")
    args=parser.parse_args()
    if args.stage=="read":
        if args.native:
            from trustmem_diagnostics.native_mem0 import Mem0Store
            store=Mem0Store(args.output,EMBED)
            try:notes=store.search(args.query,limit=5)["results"]
            finally:store.close()
        else:
            notes=[dict(id=r.id,memory=r.text,revision=r.revision) for r in SQLiteMemory(args.output).search("")]
        print(json.dumps(notes));return
    {"prepare":prepare,"ordinary":ordinary,"native":native}[args.stage](args.output.resolve())


if __name__=="__main__":main()
