"""Cross replay the witnessed task orders with and without an archived binding."""

import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

import c93_oracle_archive_path as study


CONTRACT = Path(__file__).with_name("C93B_ORACLE_ORDER_SWAP_PROTOCOL.md")
ORIGINAL = study.ROOT / "artifacts/research_decisions/20261119-c93-oracle-archive-path-v1"


def freeze():
    assert study.frozen() == study.read(ORIGINAL / "FREEZE.json")
    paths = [Path(study.__file__), Path(__file__), CONTRACT, ORIGINAL / "DIAGNOSIS_BEFORE_CONTROLS.json"]
    for day in study.WINDOW:
        batch = ORIGINAL / f"T{day:02}"
        paths.extend(batch / name for name in ("CONTROL_low_cost.json", "OPENING.json", "PUBLIC_MEMORY.json"))
    return dict(inputs={p.relative_to(study.ROOT).as_posix(): study.sha(p.read_bytes()) for p in paths},
                budget=17, model_calls=0, api_usd=0)


def run(output):
    sys.path.insert(0, str(study.SOURCE.parent))
    package = "rescopebench." + study.CASE.replace("/", ".")
    driver = importlib.import_module(package + ".driver").Driver()
    runtime = importlib.import_module(package + ".runtime")
    diagnostics = study.read(ORIGINAL / "DIAGNOSIS_BEFORE_CONTROLS.json")
    summaries = []
    for case in diagnostics:
        day, focal = case["day"], case["focal"]
        if focal is None:
            summaries.append(dict(day=day, reason="no binding"))
            continue
        batch = ORIGINAL / f"T{day:02}"
        observed = study.read(batch / "CONTROL_low_cost.json")
        params = driver.tasks[day - 1]
        task = json.loads(params["query"])
        public = {row["record_ref"]: row for row in task["targets"]}
        state = study.read(batch / "OPENING.json")
        original_memory = study.read(batch / "PUBLIC_MEMORY.json")
        outcomes = {}
        for order_origin in ("archive", "loss"):
            order = [row["target"] for row in observed[order_origin]["decisions"]]
            assert len(set(order)) == len(public) and set(order) == set(public)
            policy_input = {**params, "query": json.dumps({**task, "targets": [public[key] for key in order]})}
            for binding in ("archive", "loss"):
                memory = deepcopy(original_memory)
                if binding == "loss":
                    del memory["bindings"][focal]
                trial = driver.create_world()
                try:
                    trial.restore(state)
                    result, _ = study.episode(driver, runtime, trial, policy_input, memory, "ordered")
                    assert result["grade"] == driver.grade(trial, params)
                finally:
                    trial.close()
                if order_origin == binding:
                    assert result == observed[binding]
                outcomes[order_origin + "_order_" + binding] = result
        name = f"T{day:02}.json"
        study.write_new(output / name, outcomes)
        summaries.append(dict(day=day, focal=focal, arms={
            key: dict(targets=value["completed"], cost=value["budget_used"],
                      order=[decision["target"] for decision in value["decisions"]])
            for key, value in outcomes.items()}))
    study.write_new(output / "RESULT.json", summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "run"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    spec = freeze()
    if args.stage == "freeze":
        args.out.mkdir()
        study.write_new(args.out / "FREEZE.json", spec)
    else:
        assert spec == study.read(args.out / "FREEZE.json")
        run(args.out)


if __name__ == "__main__":
    main()
