"""Replay native integration traces at authored budgets and stage acceptance."""

import argparse
from bisect import bisect_left
from pathlib import Path
import subprocess

import c91_integration_diagnosis as integration

c74, c77 = integration.c74, integration.c77
BASE = c74.ROOT / "artifacts/research_decisions/20261119-c95-foreign-dispatch-followup-v1"
PROTOCOL = Path(__file__).with_name("C96_INTEGRATION_AUTHOR_BUDGET_BOUNDARY_PROTOCOL.md")
MODES = ("original", "least_calls")
LEVELS = range(5)


def freeze():
    cases = c74.read(BASE / "FREEZE.json")["cases"]
    files = [Path(__file__), PROTOCOL, BASE / "FREEZE.json", BASE / "RESULT.json",
             Path(c74.__file__), Path(c77.__file__), c77.MANIFEST]
    for row in cases:
        root = BASE / row["input"]["id"]
        files.extend(root / name for name in
                     ("INITIAL.json", "ADMISSION.json", "reference/CHECKPOINT.json"))
        for mode in MODES:
            for arm in integration.ARMS:
                files.extend(root / mode / arm / name
                             for name in ("actions.jsonl", "LEDGER.json", "RESULT.json"))
    return dict(source_commit=c74.PIN, inputs={p.relative_to(c74.ROOT).as_posix(): c74.sha(p)
                                              for p in files},
                cutoff_fractions_eighths=list(LEVELS), api_usd=0, model_calls=0)


def terminal(score, runtime, initial, confirmation):
    assessed = score(runtime, initial)
    missing = {error["source_id"] for error in assessed["errors"] if "source_id" in error}
    completed = sorted(set(initial["sources"]) - missing)
    assert len(completed) == assessed["completed_work_packages"]
    published = bool(runtime.p["publication"]) and {"code": "PUBLICATION"} not in assessed["errors"]
    return dict(completed=completed, published=published, confirmed=published and confirmation,
                native_task_success=assessed["task_success"])


def replay(output, source, definition, mode, arm, focus, runtime_type, score):
    root = source / mode / arm
    events = c74.read_log(root / "actions.jsonl")
    billed = c74.read(root / "LEDGER.json")
    observed = c74.read(root / "RESULT.json")
    initial = c74.read(source / "INITIAL.json")
    admission = c74.read(source / "ADMISSION.json")
    pivot = admission["pivot"]
    assert len(billed) == len(events) + pivot == observed["actual_calls"]
    assert [row["index"] for row in billed] == list(range(1, len(billed) + 1))
    spending = []
    used = 0
    for row in billed:
        used += row["debit"]
        assert row["used"] == used
        spending.append(used)
    assert used == observed["charged"]
    budgets = {i: definition["reference_calls"] + (i * definition["business_calls"] + 7) // 8
               for i in LEVELS}
    cutoffs = {i: min(len(billed), bisect_left(spending, budget) + 1)
               for i, budget in budgets.items()}
    assert all(cut > pivot for cut in cutoffs.values())

    output.mkdir(parents=True)
    c74.write(output / "project.json", c74.read(source / "reference/CHECKPOINT.json"))
    runtime = runtime_type(output, persist=False, record_calls=False)
    stamps = {}
    checkpoints = {}
    confirmation = False
    stage = initial["sources"][focus]["stage"]
    made = None
    for index, call in enumerate(events, pivot + 1):
        tool, args = call["skill_id"], call["arguments"]
        outcome = runtime.call(tool, args)
        assert outcome == call["result"], (mode, arm, index, tool)
        detail = dict(actual_call=index, charged=spending[index - 1])
        if tool == "execute_step" and args.get("skill_id") == "aggregate-source":
            if outcome.get("source_id") == focus and made is None:
                assert outcome["ok"] and outcome["current"]
                made = outcome["id"]
                stamps["first_output"] = detail
        if tool == "execute_step" and args.get("skill_id") == "close-stage":
            if outcome["stage"] == stage and made in outcome["output_ids"] and "first_accepted" not in stamps:
                status = terminal(score, runtime, initial, confirmation)
                assert focus in status["completed"] and outcome["current"]
                stamps["first_accepted"] = detail
        if runtime.p["publication"] and "publication" not in stamps:
            status = terminal(score, runtime, initial, confirmation)
            assert status["published"]
            stamps["publication"] = detail
        if tool == "read_project" and outcome.get("publication"):
            confirmation = True
            stamps.setdefault("confirmation", detail)
        for level in LEVELS:
            if index != cutoffs[level]:
                continue
            following = events[index - pivot] if index < len(billed) else None
            checkpoints[level] = dict(terminal(score, runtime, initial, confirmation),
                                      budget=budgets[level], executed=index, charged=detail["charged"],
                                      level=f"{level}/8", next_tool=following["skill_id"] if following else None)
    assert len(checkpoints) == 5 and set(stamps) == {"first_output", "first_accepted", "publication", "confirmation"}
    end = checkpoints[4]
    assert end["completed"] == observed["completed_ids"]
    assert end["published"] == observed["published"] and end["confirmed"] == observed["final_confirmation"]
    c74.write(output / "RESULT.json", dict(focus=focus, stage=stage, milestones=stamps,
                                         cutoffs=[checkpoints[i] for i in LEVELS]))
    return dict(case=definition["id"], mode=mode, arm=arm, target=focus, stage=stage,
                milestones=stamps, cutoffs=[checkpoints[i] for i in LEVELS])


def run(output):
    _, runtime, _, score = c77.native()
    routes = {row["case"]: row["first_order_change"]["archive"]["target"]
              for row in c74.read(BASE / "RESULT.json")["rows"] if row["mode"] == "least_calls"}
    report = []
    for row in c74.read(BASE / "FREEZE.json")["cases"]:
        definition = row["input"]
        case = definition["id"]
        for mode in MODES:
            for arm in integration.ARMS:
                report.append(replay(output / case / mode / arm, BASE / case, definition,
                                     mode, arm, routes[case], runtime, score))
        print(case, "replayed both controllers and all five arms", flush=True)
    c74.write(output / "RESULT.json", dict(runs=report, model_calls=0, api_usd=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "run"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    git = ["git", "-C", c74.SOURCE]
    assert subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() == c74.PIN
    assert not subprocess.check_output(git + ["status", "--porcelain", "--untracked-files=no"])
    inputs = freeze()
    seal = args.out / "FREEZE.json"
    if args.stage == "freeze":
        args.out.mkdir()
        c74.write(seal, inputs)
        return
    assert c74.read(seal) == inputs
    run(args.out)


if __name__ == "__main__":
    main()

