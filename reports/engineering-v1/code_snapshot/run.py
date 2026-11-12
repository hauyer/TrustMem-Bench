"""JSON subprocess agents, real persistent observations, and independent scoring."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from time import perf_counter
from .data import canonical, digest, history, scan
from .evidence import calculate
from .grading import reference


RULES = """All sources are immutable; current source identity is authoritative. Weights are integers (nonnegative for cross/threshold). A source is a complete weighted table over keys a,b. A marginal sums weights for a. A joint selects a,b. A threshold sums weights for a and integer b<=limit. A range sums weights for a and lo<=integer b<=hi. History is either complete marginals or the recorded interval sums. Observations can be combined only when they justify this request on this exact source. Tools: calculate(evidence:[IDs]) evaluates the request from cited observations, returning null if unsupported; query(scope:group|full) actually scans current source; save(receipt_id) retains an acquired observation for later sessions. submit(value:integer,evidence:[IDs]) commits a deliverable; abstain ends without delivery. Submit does not automatically correct or block errors. Each policy invocation is a new process. Only saved observations survive to the next task. At bootstrap, start retains the ordinary history; capture_full additionally stores the full table available from the shared historical source scan. The task stream is hidden until each task begins."""


def read_case(path):
    path = Path(path).resolve()
    case = json.loads(path.read_text(encoding="utf-8"))
    if case["mechanism"] not in ("cross","threshold","range"):
        raise ValueError("Unknown mechanism")
    for entry in case["tasks"]:
        task = entry["request"]
        if task["kind"] == "range" and not (1 <= task["lo"] <= task["hi"] <= 4):
            raise ValueError("Range requests must stay within the declared domain 1..4")
    for identity, source in case["sources"].items():
        source["nonnegative"] = case["mechanism"] != "range"
        source["path"] = str((path.parent / source["path"]).resolve())
        if identity != source["sha256"] or digest(source["path"]) != identity:
            raise ValueError("Source identity mismatch")
    return case


def invoke(command, observation, output, name):
    started = perf_counter()
    encoded = canonical(observation).encode("utf-8")
    (output / f"{name}.observation.json").write_bytes(encoded)
    try:
        response = subprocess.run(command, input=encoded+b"\n", capture_output=True, timeout=120, check=False)
        code, stdout, stderr = response.returncode, response.stdout, response.stderr
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = None, exc.stdout or b"", exc.stderr or b""
    (output / f"{name}.stdout").write_bytes(stdout)
    (output / f"{name}.stderr").write_bytes(stderr)
    process = {"command":command,"returncode":code,"seconds":perf_counter()-started,"input_bytes":len(encoded)}
    (output / f"{name}.process.json").write_text(json.dumps(process,indent=2),encoding="utf-8")
    if code != 0:
        return None, process
    try:
        action = json.loads(stdout)
        if not isinstance(action,dict) or not isinstance(action.get("action"),str):
            raise ValueError("Expected action object")
        return action, process
    except (ValueError,UnicodeError):
        return None, process


def run(case_path, output, policy="lazy_group", agent_command=None, steps=10):
    case = read_case(case_path)
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    command = agent_command or [sys.executable,"-B","-m","trustmem_runtime.agent",policy]
    # Before running a policy: bind inputs, case, commands and code; leave gold out.
    protocol = {"case_sha256":digest(case_path),"sources":{k:{"sha256":v["sha256"],"bytes":Path(v["path"]).stat().st_size} for k,v in case["sources"].items()},
        "steps_per_task":steps,"command":command,"policy":policy if agent_command is None else "external",
        "code":{p.name:digest(p) for p in Path(__file__).parent.glob("*.py")},"model_budget_authorized_by_this_runner":False}
    (output/"freeze.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
    initial = case["initial_source"]
    table, bootstrap_cost = scan(case["sources"][initial])
    old = history(table,case["mechanism"],initial)
    (output/"history.json").write_text(canonical(old),encoding="utf-8")
    database = output/"memory.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE memory(id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        db.commit()
    storage_written = 0
    def retain(receipt):
        nonlocal storage_written
        blob = canonical(receipt)
        key = "r-"+__import__("hashlib").sha256(blob.encode()).hexdigest()
        with closing(sqlite3.connect(database)) as db:
            exists = db.execute("SELECT 1 FROM memory WHERE id=?",(key,)).fetchone()
            if not exists:
                db.execute("INSERT INTO memory VALUES (?,?)",(key,blob))
                db.commit()
                storage_written += len(blob.encode())
        return key
    first = {"protocol":RULES,"phase":"bootstrap","history":old,"source_id":initial,
        "initial_full_capture_available":True,"trace":[],"memory":[]}
    action, bootstrap_process = invoke(command,first,output,"bootstrap")
    if action is None or action.get("action") not in ("start","capture_full"):
        failure = {"status":"BOOTSTRAP_FAILURE","case_id":case["id"],"model_calls_by_runner":0}
        (output/"result.json").write_text(json.dumps(failure,indent=2),encoding="utf-8")
        return failure
    if action["action"] == "capture_full":
        retain({"kind":"full","source_id":initial,"table":table})
    del table
    events = []
    for index, entry in enumerate(case["tasks"]):
        source_id, task = entry["source_id"], entry["request"]
        # SQLite is reopened; no transient query results survive across tasks.
        with closing(sqlite3.connect(database)) as db:
            memory = {key:json.loads(raw) for key,raw in db.execute("SELECT id,body FROM memory ORDER BY id")}
        transient, trace = {}, []
        source_bytes, source_seconds, calls, observation_bytes = 0, 0.0, 0, 0
        submitted, declared, status, support_value = None, [], "STEP_LIMIT", None
        before_written = storage_written
        for turn in range(steps):
            visible = {"protocol":RULES,"phase":"task","session_index":index,
                "source_id":source_id,"request":task,"history":old,
                "memory":[{"id":key,"source_id":v["source_id"],"kind":v["kind"],"scope_a":v.get("scope_a")} for key,v in memory.items()],
                "trace":trace,"steps_remaining":steps-turn}
            action, process = invoke(command,visible,output,f"s{index:02}-{turn:02}")
            calls += 1
            observation_bytes += process["input_bytes"]
            if action is None:
                status = "AGENT_FAILURE"
                break
            def resolve(ids):
                pool = {"history":old,**memory,**transient}
                if not isinstance(ids,list) or any(not isinstance(k,str) or k not in pool for k in ids):
                    raise ValueError("Unknown evidence IDs")
                return [pool[key] for key in ids]
            try:
                name = action["action"]
                if name == "query":
                    scope = action.get("scope")
                    if scope not in ("group","full"):
                        raise ValueError("scope must be group or full")
                    cells, cost = scan(case["sources"][source_id], task["a"] if scope=="group" else None)
                    source_bytes += cost["source_read_bytes"]
                    source_seconds += cost["scan_seconds"]
                    receipt = {"kind":scope,"source_id":source_id,"table":cells}
                    if scope == "group":
                        receipt["scope_a"] = task["a"]
                    key = f"observation-{index}-{turn}"
                    transient[key] = receipt
                    value = calculate([receipt],task,source_id)
                    result = {"receipt_id":key,"value":value,"evidence":[key],"source_read_bytes":cost["source_read_bytes"]}
                elif name == "calculate":
                    ids = action.get("evidence",[])
                    value = calculate(resolve(ids),task,source_id)
                    result = {"value":value,"evidence":ids}
                elif name == "save":
                    key = action.get("receipt_id")
                    if key not in transient:
                        raise ValueError("Only acquired observations can be saved")
                    saved = retain(transient[key])
                    memory[saved] = transient[key]
                    result = {"saved_id":saved}
                elif name == "submit":
                    submitted = action.get("value")
                    if type(submitted) is not int:
                        raise ValueError("Submission value must be an integer")
                    declared = action.get("evidence",[])
                    support_value = calculate(resolve(declared),task,source_id)
                    (output/f"s{index:02}.delivery.json").write_text(canonical({"value":submitted,"evidence":declared}),encoding="utf-8")
                    result = {"status":"COMMITTED"}
                    status = "SUBMITTED"
                elif name == "abstain":
                    result, status = {"status":"ABSTAINED"}, "ABSTAINED"
                else:
                    raise ValueError("Unknown action")
            except (ValueError,TypeError,KeyError) as exc:
                result = {"error":str(exc)}
            trace.append({"action":action,"result":result})
            if status in ("SUBMITTED","ABSTAINED"):
                break
        events.append({"session":index,"source_id":source_id,"request":task,"status":status,
            "submitted_value":submitted if status=="SUBMITTED" else None,"declared_evidence":declared,
            "declared_evidence_value":support_value,"source_read_bytes":source_bytes,"source_scan_seconds":source_seconds,
            "policy_invocations":calls,"policy_observation_bytes":observation_bytes,"memory_written_payload_bytes":storage_written-before_written,
            "cited_saved_evidence":status=="SUBMITTED" and any(k in memory for k in declared),"trace":trace})
    # Scoring runs only after every policy session has ended. Gold is never feedback.
    scoring_started = perf_counter()
    gold = reference(case)
    for event in events:
        expected = gold[event["session"]]
        event["correct"] = event["status"]=="SUBMITTED" and event["submitted_value"]==expected
        event["declared_evidence_sufficient"] = event["status"]=="SUBMITTED" and event["declared_evidence_value"] is not None
        event["unsupported_submission"] = event["status"]=="SUBMITTED" and not event["declared_evidence_sufficient"]
        event["supported_correct"] = event["correct"] and event["declared_evidence_sufficient"]
    result = {"status":"COMPLETED","case_id":case["id"],"history_group":case["history_group"],"split":case["split"],
        "mechanism":case["mechanism"],"policy":policy if agent_command is None else "external","sessions":len(events),
        "correct":sum(e["correct"] for e in events),"supported_correct":sum(e["supported_correct"] for e in events),
        "unsupported_submissions":sum(e["unsupported_submission"] for e in events),
        "abstentions":sum(e["status"]=="ABSTAINED" for e in events),
        "agent_failures":sum(e["status"]=="AGENT_FAILURE" for e in events),
        "source_read_bytes_after_history":sum(e["source_read_bytes"] for e in events),
        "shared_history_scan":bootstrap_cost,"memory_written_payload_bytes":storage_written,
        "sqlite_file_bytes":database.stat().st_size,"scoring_seconds":perf_counter()-scoring_started,
        "external_model_accounting":"External adapters must supply their own usage ledger; process invocations are not model calls.",
        "bootstrap_process":bootstrap_process,"events":events}
    (output/"scoring-only.json").write_text(json.dumps({"answers":gold},indent=2),encoding="utf-8")
    (output/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--policy",choices=["always_verify","lazy_group","lazy_full","eager_full"],default="lazy_group")
    parser.add_argument("--agent-config",help="JSON file with command: [executable, argument, ...]")
    parser.add_argument("--steps",type=int,default=10)
    args = parser.parse_args()
    command = json.loads(Path(args.agent_config).read_text(encoding="utf-8"))["command"] if args.agent_config else None
    if command is not None and (not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command)):
        parser.error("command must be a nonempty list of strings")
    result = run(args.case,args.output,args.policy,command,args.steps)
    print(json.dumps({k:v for k,v in result.items() if k not in ("events","bootstrap_process")},indent=2))
