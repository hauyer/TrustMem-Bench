"""Run the frozen FieldOps native-query budget qualification without a provider."""
import argparse
import asyncio
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "artifacts/research_decisions/20261119-c74-skillhorizon-native-v1/upstream"
PIN = "1749e7439fdafb75426d7bfecbd4b657509ebe1c"
Q_TOOLS = {"read_project", "read_artifact", "read_skill_file", "search_objects", "read_object"}
W_TOOLS = {"execute_step", "run_skill_script"}
ARMS = ("rescan", "scope_cache", "demand_cache")
CONTRACT = Path(__file__).with_name("C74_SKILLHORIZON_NATIVE_BUDGET_PROTOCOL.md")
MANIFEST = SOURCE / "manifests/FieldOps.json"
PROTOCOL = "skill_declaration_v1"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, val):
    path.write_text(json.dumps(val, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_log(path):
    if not path.exists():
        return []
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]


def hashes(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def chosen_cases():
    manifest = read(MANIFEST)["tasks"]
    rows = [r for label in ("normal", "recovery")
            for r in [x for x in manifest if x["band"] == "64k" and f"64k-{label}-" in x["id"]][:2]]
    assert len(rows) == 4
    return rows


def budget(row):
    return row["reference_calls"] + (row["business_calls"] + 1) // 2


def import_native():
    sys.path.insert(0, str(SOURCE / "src"))
    from skillhorizon.fieldops.tasks import initialize_operations
    from skillhorizon.fieldops.declaration_runtime import DeclarationOperationsRuntime
    from skillhorizon.fieldops.horizon_witness import HorizonWitness, ReferenceCallLimit, PublicBusinessRejection
    from skillhorizon.fieldops.cached_witness import CachedFieldWitness
    from skillhorizon.fieldops.demand_witness import DemandFieldWitness
    return initialize_operations, DeclarationOperationsRuntime, ReferenceCallLimit, PublicBusinessRejection, dict(
        zip(ARMS, (HorizonWitness, CachedFieldWitness, DemandFieldWitness)))


def run_case(out, row):
    init, runtime_cls, Limit, Rejection, classes = import_native()
    case = out / row["id"]
    case.mkdir()
    initial = case / "initial"
    params = dict(row["parameters"])
    wide_budget = params.pop("max_calls")
    assert params.pop("reference_policy") == "public_demand_cache_v2"
    init(initial, **params, skill_protocol=PROTOCOL)
    init_hash = hashes(initial)
    write(case / "INITIAL_SHA256.json", init_hash)

    def play(arm, regime, cap):
        started = time.monotonic()
        path = case / arm / regime
        shutil.copytree(initial, path)
        runtime = runtime_cls(path)
        assert hashes(path) == init_hash
        async def invoke(name, args):
            assert name in Q_TOOLS | W_TOOLS, name
            return runtime.call(name, args)
        player = classes[arm](invoke, skill_protocol=PROTOCOL, max_calls=cap)
        stop, error = "returned", None
        try:
            asyncio.run(player.run())
        except Limit as exc:
            stop, error = "limit", str(exc)
        except Rejection as exc:
            stop, error = "business_rejection", str(exc)
        except Exception as exc:
            import traceback
            stop, error = "runner_error", traceback.format_exc()
        score = runtime.score()
        actions = read_log(path / "model_skill_actions.jsonl")
        assert len(actions) == player.call_count, (len(actions), player.call_count, arm)
        assert [{k: r[k] for k in ("skill_id","arguments","result")} for r in actions] == player.calls
        assert len(actions) <= cap
        count = Counter(x["skill_id"] for x in actions)
        changed = [dict(action=i, stage=x["arguments"].get("skill_id"), notices=x["result"]["notices"])
                   for i,x in enumerate(actions, 1) if x["result"].get("notices")]
        keys = list(score["cases"])
        bcase = score["cases"]
        totals = {"success":score["success"],"termination_ready":score["termination_ready"],
                  "completed_cases":score["completed_cases"],"total_cases":score["total_cases"],
                  "missing_cases":[k for k in keys if not bcase[k]["success"]]}
        result = {"cap":cap,"spent":len(actions),"left":cap-len(actions),"stop":stop,"error":error,
                  "queries":sum(count[k] for k in Q_TOOLS),"writes":sum(count[k] for k in W_TOOLS),
                  "rejections":sum(not x["result"]["ok"] for x in actions),
                  "mutation_records":sum(x.get("node_id") is not None for x in actions),
                  "tool_counts":dict(count),"notices":changed,"score":totals,"wall_s":time.monotonic()-started}
        write(path / "C74_SCORE.json", score)
        write(path / "C74_RESULT.json", result)
        print(row["id"], arm, regime, result["spent"], result["score"]["completed_cases"],
              result["score"]["total_cases"], result["stop"], flush=True)
        return result, actions

    results = {}
    for arm in ARMS:
        result, log = play(arm, "native_budget", budget(row))
        results[arm] = {"native_budget":result}
        if not result["score"]["success"]:
            other, log2 = play(arm, "wide_reference", wide_budget)
            results[arm].update(wide_reference=other, prefix_equal=log == log2[:len(log)])
    assert hashes(initial) == init_hash
    combined = {"manifest_record":row,"budget":budget(row),"results":results}
    write(case/"RESULT.json", combined)
    return combined


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    actual = subprocess.check_output(["git","-C",str(SOURCE),"rev-parse","HEAD"], text=True).strip()
    tracked_changes = subprocess.check_output(["git","-C",str(SOURCE),"status","--porcelain","--untracked-files=no"],text=True)
    assert actual == PIN and not tracked_changes
    selected = chosen_cases()
    out = args.out.resolve()
    out.mkdir()
    write(out/"FREEZE.json", {"pin":PIN,"script_sha256":sha(Path(__file__)),"contract_sha256":sha(CONTRACT),
          "manifest_sha256":sha(MANIFEST),"cases":selected,"arms":ARMS,"python":sys.version,
          "budget_origin":"paper formula on published manifest counts","model_calls_cap":0,"api_usd_cap":0,
          "environment":"local scripted clients over pinned FieldOps declaration API and native score"})
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        handles = [ex.submit(run_case, out, row) for row in selected]
        results = [h.result() for h in handles]
    write(out/"RESULT.json", {"cases":results,"model_calls":0,"api_usd":0,"real_business_actions":0})


if __name__ == "__main__":
    main()
