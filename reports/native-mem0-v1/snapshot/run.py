"""Native Mem0 qualification and bounded two-backend reader development trial."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
from time import perf_counter

ROOT = Path.cwd()
REPO = ROOT / "github-release/TrustMem-Bench"
HERE = Path(__file__).resolve().parent
EMBED = ROOT / "memory-revocation-research/native-embedding-cache/models/models--qdrant--bge-small-en-v1.5-onnx-q/snapshots/aa8f8b060edb00e03bfdd08813a2949946c8ba55"
sys.path.insert(0, str(HERE if (HERE / "trustmem_runtime").is_dir() else REPO))
from trustmem_diagnostics.native_mem0 import Mem0Store
from trustmem_runtime.data import canonical, digest, history, scan
from trustmem_runtime.grading import reference
from trustmem_runtime.run import read_case
from trustmem_runtime.tool_cache import ToolCache

READER_SYSTEM = """You continue a quality-review workflow using retrieved long-term notes and authorized tools.
Return exactly one JSON action: {"action":"submit","value":0 or 1,"citations":[native note IDs]},
or {"action":"query"}, or {"action":"abstain"}. Do not output any other shape.
Current source identity is authoritative. Notes about a different source may remain valid historical facts,
but do not establish the current gate. Relevant old notes can avoid an unnecessary query.
Every source is a complete nonnegative integer-weight table over group a and confidence integer b.
The task quality gate is 1 iff rows with b>=cutoff are nonempty and their share in group a is at least
numerator/denominator; otherwise 0. Old marginal totals may bound the selected numerator between
max(0,group_total+selected_total-total) and min(group_total,selected_total).
Query returns a complete current-source contingency observation and exact gate value; the common
backend may already have this from an earlier query, so a query invocation is distinct from a source scan.
You have at most two actions this session. Only notes actually shown below are available as memory.
You may submit directly when the notes are sufficient. If not, query; after receiving a query result,
submit your actual decision. A wrong value commits unchanged. No hidden reference feedback is shown."""


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(output):
    assert HERE == (output / "snapshot").resolve()
    for path, expected in load(output / "freeze.json")["hashes"].items():
        assert sha(ROOT / path) == expected, path


def prepare(output, smoke=None):
    output.mkdir(parents=True)
    snapshot = output / "snapshot"
    snapshot.mkdir()
    shutil.copyfile(HERE / "run.py", snapshot / "run.py")
    shutil.copytree(REPO / "trustmem_runtime", snapshot / "trustmem_runtime", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "trustmem_diagnostics", snapshot / "trustmem_diagnostics", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(REPO / "examples/metered_deepseek.py", snapshot / "metered_deepseek.py")
    shutil.copyfile(HERE / "PROTOCOL.md", output / "PROTOCOL.md")
    # Authored two-version engineering workload; not a natural external history.
    from trustmem_runtime.fixtures import build
    build(output / "cases")
    path = output / "cases/quality.case.json"
    case = load(path)
    case["tasks"] = [case["tasks"][i] for i in (0, 1, 2, 4, 5, 7)]
    case["tasks"][4]["request"]["numerator"] = 9
    case["tasks"][4]["request"]["denominator"] = 10
    case["id"] = "native-memory-quality-development"
    dump(path, case)
    files = [*snapshot.rglob("*.py"), output / "PROTOCOL.md", *list((output / "cases").glob("*"))]
    env = Path(sys.executable).parents[1] / "Lib/site-packages"
    for name in ("mem0/memory/main.py", "mem0/configs/prompts.py", "mem0/memory/utils.py"):
        files.append(env / name)
    files += sorted(p for p in EMBED.rglob("*") if p.is_file())
    if smoke is not None:
        assert load(smoke / "smoke/results.json")["status"] == "complete"
        files.append(smoke / "smoke/results.json")
        shutil.copyfile(smoke / "smoke/results.json", output / "prepaid-smoke.json")
    schedule = ["mem0", "verbatim"]
    random.Random(2026111314).shuffle(schedule)
    dump(output / "freeze.json", dict(at=datetime.now(timezone.utc).isoformat(), stage="models" if smoke else "smoke",
        model_calls_cap=48 if smoke else 0, usd_cap=.10 if smoke else 0, max_tokens=1536,
        thinking="disabled", schedule=schedule, case="cases/quality.case.json",
        reader_system=READER_SYSTEM, embedding_path=str(EMBED), retrieval_limit=5,
        versions={p:importlib.metadata.version(p) for p in ("mem0ai", "fastembed", "qdrant-client", "pydantic")},
        hashes={p.relative_to(ROOT).as_posix():sha(p) for p in files}))


def read_process(store_path, query, output):
    child = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "trustmem_diagnostics.native_mem0",
        "--store", str(store_path), "--embedding-path", str(EMBED), "--query", query, "--limit", "5"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        env={**os.environ, "PYTHONPATH":str(HERE), "MEM0_TELEMETRY":"False", "HF_HUB_OFFLINE":"1"})
    (output / "reader.stdout").write_text(child.stdout, encoding="utf-8")
    (output / "reader.stderr").write_text(child.stderr, encoding="utf-8")
    if child.returncode:
        raise RuntimeError("Fresh native read process failed; preserve stdout/stderr")
    return json.loads(child.stdout)


def smoke(output):
    verify(output)
    target = output / "smoke"
    target.mkdir()
    case = read_case(output / "cases/quality.case.json")
    identity = case["initial_source"]
    table, cost = scan(case["sources"][identity])
    observation = dict(source_id=identity, kind="full", table=table)
    body = canonical(observation)
    calls = []
    def scripted(messages):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(dict(facts=[body]))
        if len(calls) == 2:
            return json.dumps(dict(memory=[dict(id="0", text=body, event="ADD")]))
        raise RuntimeError("Scripted preflight permits exactly extraction and ADD")
    store_path = target / "store"
    store = Mem0Store(store_path, EMBED, scripted)
    try:
        result = store.add("I manage this quality workflow; retain its verified source observation. " + body)
        records = store.all()["results"]
        assert len(calls) == 2 and len(records) == 1 and records[0]["memory"] == body
        first = store.search("quality workflow confidence correct observations", 5)
        assert first["results"][0]["memory"] == body
        # Ordinary trusted structured preflight reader; no model behavior claim.
        from trustmem_runtime.evidence import calculate
        delivered = json.loads(first["results"][0]["memory"])
        values = {i:calculate([delivered],task["request"],identity) for i,task in enumerate(case["tasks"]) if task["source_id"]==identity}
        truth = reference(case)
        assert all(value==truth[i] for i,value in values.items())
        updated = canonical(dict(observation, preflight_marker="revision-2"))
        update_result = store.update(records[0]["id"], updated)
        dump(target / "operations.json", dict(add=result, search=first, update=update_result,
            scripted_calls=calls, actual_values=values, source_cost=cost, expected_after_update=updated))
    finally:
        store.close()
    restored = read_process(store_path, "quality workflow confidence correct observations", target)
    assert restored["search"]["results"][0]["memory"] == updated
    assert restored["inventory"]["results"][0]["id"] == records[0]["id"]
    dump(target / "results.json", dict(status="complete", external_model_calls=0, scripted_writer_calls=2,
        actual_task_checks=len(values), native_infer_true_add=True, native_search=True, native_update=True,
        qdrant_disk_reopened_new_process=True, same_object_id=True, telemetry=False,
        actual_memory_text_after_update=updated))
    print(json.dumps(load(target / "results.json")))


class Writer:
    def __init__(self, client, global_count):
        self.client, self.count = client, global_count
        self.stage = ""
    def __call__(self, messages):
        if self.count[0] >= 48:
            raise RuntimeError("Frozen model-call cap reached")
        self.count[0] += 1
        raw = self.client.complete_messages(messages, f"writer-{self.stage}-{self.count[0]:03}", return_raw=True)
        return raw["choices"][0]["message"]["content"]


def model(output):
    verify(output)
    cfg = load(output / "freeze.json")
    assert cfg["stage"] == "models" and (output / "prepaid-smoke.json").exists()
    target = output / "models"
    target.mkdir()
    (target / "api").mkdir()
    for line in (ROOT / ".env.local").read_text(encoding="utf-8-sig").splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name == "DEEPSEEK_API_KEY":
            os.environ.setdefault(name, value.strip().strip('"').strip("'"))
    from metered_deepseek import DeepSeekClient
    metrics, counter = {}, [0]
    client = DeepSeekClient(target / "api", metrics, max_usd=cfg["usd_cap"], max_tokens=cfg["max_tokens"], thinking="disabled")
    writer = Writer(client, counter)
    case = read_case(output / cfg["case"])
    initial = case["initial_source"]
    initial_table, initial_cost = scan(case["sources"][initial])
    initial_text = "I manage this quality-review workflow. Retain this verified historical summary for later requests, including its exact source identity. " + canonical(history(initial_table, "quality", initial))
    dump(target / "initial_experience.json", dict(text=initial_text, cost=initial_cost))
    results = []
    stopped = None
    for arm in cfg["schedule"]:
        folder = target / arm
        folder.mkdir()
        cache = ToolCache(folder / "tool-cache.sqlite")
        notes = []
        events = []
        def ingest(text, stage):
            if arm == "verbatim":
                notes.append(dict(id=f"note-{len(notes)}", memory=text))
                dump(folder / "notes.json", notes)
                return dict(event="append_verbatim", stored=len(notes))
            writer.stage = stage
            store = Mem0Store(folder / "native-store", EMBED, writer)
            try:
                operations = store.add(text, metadata=dict(bench_stage=stage))
                inventory = store.all()
                dump(folder / (stage + "-inventory.json"), inventory)
                return operations
            finally:
                store.close()
        try:
            dump(folder / "initial-write.json", ingest(initial_text, arm + "-initial"))
            for index, entry in enumerate(case["tasks"]):
                identity, request = entry["source_id"], entry["request"]
                session = folder / f"s{index:02}"
                session.mkdir()
                query = "quality-review workflow verified statistics for source " + identity + " " + canonical(request)
                if arm == "verbatim":
                    delivered = dict(results=notes.copy(), ordering="all original records")
                else:
                    # A fresh process opens disk state and calls actual native vector search.
                    restored = read_process(folder / "native-store", query, session)
                    delivered = restored["search"]
                    dump(session / "inventory-diagnostic-only.json", restored["inventory"])
                dump(session / "delivered.json", delivered)
                trace = []
                event = dict(session=index, source_id=identity, request=request, status="unfinished",
                    source_read_bytes=0, query_calls=0, native_text_support="unassessed",
                    delivered_note_ids=[r["id"] for r in delivered["results"]])
                acquired_text = None
                for turn in range(2):
                    if counter[0] >= cfg["model_calls_cap"]:
                        raise RuntimeError("Frozen global call cap reached")
                    payload = dict(current_source_id=identity, task=request, retrieved_notes=delivered["results"],
                        tool_trace=trace, remaining_actions=2-turn)
                    dump(session / f"t{turn}-input.json", payload)
                    counter[0] += 1
                    response = client.complete(READER_SYSTEM, payload, f"reader-{arm}-s{index:02}-t{turn}-{counter[0]:03}")
                    dump(session / f"t{turn}-response.json", response)
                    action = response.get("action")
                    if action == "submit":
                        if type(response.get("value")) is not int or response["value"] not in (0,1):
                            raise ValueError("Reader submitted an invalid gate type")
                        event.update(status="submitted", submitted_value=response["value"], citations=response.get("citations", []),
                                     current_tool_evidence=bool(trace))
                        dump(session / "delivery.json", response)
                        break
                    if action == "abstain":
                        event["status"] = "abstained"
                        break
                    if action != "query":
                        raise ValueError("Reader action schema outside frozen interface")
                    event["query_calls"] += 1
                    receipt = cache.get(identity, "full", request["a"])
                    hit = receipt is not None
                    if receipt is None:
                        table, cost = scan(case["sources"][identity])
                        event["source_read_bytes"] += cost["source_read_bytes"]
                        receipt = dict(kind="full", source_id=identity, table=table)
                        cache.put(receipt)
                    from trustmem_runtime.evidence import calculate
                    value = calculate([receipt], request, identity)
                    actual = dict(receipt=receipt, value=value, backend_cache_hit=hit)
                    trace.append(dict(action=response, result=actual))
                    acquired_text = "I verified this source observation with the authorized tool. Preserve the source identity and full values for future requests. " + canonical(receipt)
                event["tool_trace"] = trace
                dump(session / "event.json", event)
                events.append(event)
                dump(folder / "events.json", events)
                if acquired_text is not None:
                    dump(session / "native-ingestion-input.json", dict(text=acquired_text))
                    dump(session / "write-result.json", ingest(acquired_text, f"{arm}-s{index:02}"))
        except Exception as error:
            stopped = dict(arm=arm, error_type=type(error).__name__, completed_sessions=len(events),
                call_attempts=counter[0], remaining_policy="stop further paid calls; preserve all first responses")
            dump(target / "failure.json", stopped)
        results.append(dict(arm=arm, events=events, planned_sessions=len(case["tasks"]),
            not_run=len(case["tasks"])-len(events), backend_cache_hits=cache.hits, backend_cache_misses=cache.misses))
        dump(target / "raw-results.json", results)
        dump(target / "metrics.json", metrics)
        if stopped:
            break
    # Independent reference is read only after all policy execution has ended.
    truth = reference(case)
    for result in results:
        for event in result["events"]:
            event["correct"] = event["status"] == "submitted" and event["submitted_value"] == truth[event["session"]]
        result.update(correct=sum(e["correct"] for e in result["events"]),
            wrong=sum(e["status"]=="submitted" and not e["correct"] for e in result["events"]),
            query_calls=sum(e["query_calls"] for e in result["events"]), source_read_bytes=sum(e["source_read_bytes"] for e in result["events"]))
    dump(target / "reference-after-policy.json", truth)
    dump(target / "results.json", results)
    dump(target / "metrics.json", metrics)
    dump(target / "gate.json", dict(status="stopped" if stopped else "complete", call_attempts=counter[0],
        planned_arms=cfg["schedule"], executed_arms=[r["arm"] for r in results],
        scientific_scope="One authored two-version workload, six correlated sessions per arm; native writer and delivered search text preserved; semantic note support unassessed."))
    print(json.dumps(dict(status="stopped" if stopped else "complete", calls=counter[0], metrics=metrics,
        arms=[{k:r[k] for k in ("arm","correct","wrong","query_calls","source_read_bytes","not_run")} for r in results])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "smoke", "model"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--smoke", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.output.resolve(), args.smoke.resolve() if args.smoke else None)
    else:
        {"smoke":smoke, "model":model}[args.mode](args.output.resolve())
