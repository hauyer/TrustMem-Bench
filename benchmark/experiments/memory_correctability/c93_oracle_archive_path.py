"""Evaluate archived public record bindings in the pinned form-correction simulator."""

import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

from c93_oracle_source import OUT as SOURCE_RUN, SOURCE, CASE
from c68_admit_workflow import ROOT, sha, write_new


PROTOCOL = Path(__file__).with_name("C93_ORACLE_ARCHIVE_PATH_PROTOCOL.md")
CONTEXT = "get_correction_context"
POLICY = "get_correction_policy"
WRITE = "apply_form_correction"
BINDING = ("record_ref", "correction_handle", "visit_type", "binding_scope")
MODES = ("ordered", "low_cost")
WINDOW = range(11, 17)


def read(path):
    return json.loads(path.read_bytes())


def frozen():
    pin = read(SOURCE_RUN / "SOURCE_FREEZE.json")
    for name, spec in pin["files"].items():
        assert sha((SOURCE / name).read_bytes()) == spec["sha256"], name
    for name, digest in pin["shared"].items():
        assert sha((SOURCE / name).read_bytes()) == digest, name
    return dict(source_pin=pin["pin"], source_sha=sha((SOURCE_RUN / "SOURCE_FREEZE.json").read_bytes()),
                protocol_sha=sha(PROTOCOL.read_bytes()), runner_sha=sha(Path(__file__).read_bytes()),
                batches=list(WINDOW), modes=list(MODES), paid_model_calls=0, api_usd=0)


def episode(driver, runtime, world, task, memory, mode, refund=None):
    task_view = json.loads(task["query"])
    start = driver.begin(world, task)
    assert start["allowance"] == 17
    balance = 17
    log, decisions, terminals = [], [], {}
    cached = memory["bindings"]
    policies = memory["policies"]
    verified = memory["verified"]
    rejected = memory["rejected"]
    checked = set()
    hit = None

    def call(ref, tool, args):
        nonlocal balance, hit
        cost = runtime.DATA_TOOL_COSTS[tool]
        credit = (
            refund is not None and hit is None and tool == CONTEXT and ref == refund
        )
        if credit:
            assert cost == 5
            with patch.dict(runtime.DATA_TOOL_COSTS, {CONTEXT: 0}):
                response = driver.call(world, tool, args)
            hit = len(log) + 1
        else:
            response = driver.call(world, tool, args)
        charged = response["budget"]["charged"]
        assert charged == (0 if credit else cost)
        balance -= charged
        assert response["budget"]["remaining"] == balance
        log.append(dict(target=ref, tool=tool, arguments=args, result=response))
        return response["content"]

    def candidates(cell):
        return [p for p in policies.get(cell, []) if p not in rejected.get(cell, [])]

    def floor(target):
        binding = cached.get(target["record_ref"])
        if binding is None:
            return 7
        scope = binding["fields"]["visit_type"] + "|" + target["correction_class"]
        return 2 if candidates(scope) else 5

    def handle(target):
        ref, correction = target["record_ref"], target["correction_class"]
        if ref not in cached:
            ctx = call(ref, CONTEXT, {"record_ref": ref})
            if ctx["status"] != "success":
                return ctx["error_code"]
            stable = {key: ctx["data"][key] for key in BINDING}
            assert ctx["data"]["correction_handle_reusable_across_episodes"]
            cached[ref] = dict(fields=stable, session=task["position"], call=len(log))
        binding = cached[ref]["fields"]
        visit = binding["visit_type"]
        cell = visit + "|" + correction
        while balance >= 2:
            choices = candidates(cell)
            if not choices:
                if cell in checked or balance < 5:
                    return "unfunded_or_no_observed_policy"
                ctx = call(ref, POLICY, {"visit_type": visit, "correction_class": correction})
                assert ctx["status"] == "success"
                policies[cell] = [row["audit_profile_id"] for row in sorted(ctx["data"]["evidence"],
                                                                          key=lambda row: row["evidence_id"])]
                checked.add(cell)
                continue
            profile = verified.get(cell)
            profile = profile if profile in choices else choices[0]
            response = call(ref, WRITE, {"correction_handle": binding["correction_handle"],
                                         "correction_class": correction, "corrected_value": target["corrected_value"],
                                         "audit_profile_id": profile})
            if response["status"] == "success":
                verified[cell] = profile
                return "committed"
            if response["error_code"] != "CORRECTION_POLICY_MISMATCH":
                return response["error_code"]
            rejected.setdefault(cell, []).append(profile)
        return "unfunded_after_policy_or_read"

    pending = list(enumerate(task_view["targets"]))
    while pending:
        chosen = min(pending, key=lambda pair: (floor(pair[1]), pair[0])) if mode == "low_cost" else pending[0]
        _, target = chosen
        pending.remove(chosen)
        ref = target["record_ref"]
        amount = floor(target)
        start_index, entry_balance = len(log), balance
        status = "unfunded" if amount > balance else handle(target)
        decisions.append(dict(target=ref, balance=entry_balance, floor=amount, after_calls=start_index,
                              remaining=balance, status=status))
        terminals[ref] = status
    grade = driver.grade(world, task)
    assert grade["valid"]
    completed = [row["record_ref"] for row in grade["artifacts"] if row["complete"]]
    assert set(completed) == {key for key, status in terminals.items() if status == "committed"}
    result = dict(start=start, budget_used=17-balance, log=log, decisions=decisions, completed=completed,
                  grade=grade, refund_index=hit)
    return result, memory


def acquisition(observed, focal, prior):
    matches = [(index, row) for index, row in enumerate(observed["log"], 1)
               if row["tool"] == CONTEXT and row["target"] == focal
               and row["result"]["content"]["status"] == "success"]
    if not matches:
        return None
    index, row = matches[0]
    projection = {key: row["result"]["content"]["data"][key] for key in BINDING}
    return index if projection == prior["fields"] else None


def diagnose(observation, index):
    if index is None:
        return None
    for step in observation["decisions"]:
        if step["after_calls"] >= index and step["status"] == "unfunded":
            return step["target"] if step["floor"] <= step["balance"] + 5 else None
    return None


def prepare(output, driver, runtime):
    world = driver.create_world()
    memory = {"bindings": {}, "policies": {}, "verified": {}, "rejected": {}}
    try:
        warm = []
        cases = []
        for task in driver.tasks:
            day = task["position"]
            if day in WINDOW:
                batch = output / f"T{day:02}"
                batch.mkdir()
                state = world.snapshot()
                write_new(batch / "OPENING.json", state)
                write_new(batch / "PUBLIC_MEMORY.json", memory)
                refs = [target["record_ref"] for target in json.loads(task["query"])["targets"]]
                focal = next((ref for ref in refs if ref in memory["bindings"]), None)
                sham = next(iter(sorted(set(memory["bindings"]) - set(refs))), None)
                reference = dict(day=day, focal=focal, sham=sham, targets=refs, modes={})
                if focal:
                    for mode in MODES:
                        absent = deepcopy(memory)
                        prior = absent["bindings"].pop(focal)
                        loss_world = driver.create_world()
                        try:
                            loss_world.restore(state)
                            observation, _ = episode(driver, runtime, loss_world, task, absent, mode)
                        finally:
                            loss_world.close()
                        read_index = acquisition(observation, focal, prior)
                        equal = next(((index, row["target"]) for index, row in enumerate(observation["log"], 1)
                                      if row["target"] != focal and row["tool"] == CONTEXT
                                      and row["result"]["content"]["status"] == "success"), None)
                        named = batch / f"LOSS_{mode}.json"
                        write_new(named, observation)
                        reference["modes"][mode] = dict(log_sha=sha(named.read_bytes()),
                                                        named_index=read_index, equal=equal,
                                                        predicted=diagnose(observation, read_index),
                                                        predicted_equal=diagnose(observation, equal[0] if equal else None))
                cases.append(reference)
            retained, memory = episode(driver, runtime, world, task, memory, "ordered")
            if day in WINDOW:
                write_new(batch / "CONTINUOUS_KEEP.json", retained)
            else:
                warm.append(retained)
        write_new(output / "WARM.json", warm)
        write_new(output / "DIAGNOSIS_BEFORE_CONTROLS.json", cases)
    finally:
        world.close()


def compare(output, driver, runtime):
    cases = read(output / "DIAGNOSIS_BEFORE_CONTROLS.json")
    report = []
    for case in cases:
        day, focal, sham = case["day"], case["focal"], case["sham"]
        if focal is None:
            report.append(dict(day=day, reason="no earlier live context receipt"))
            continue
        task = driver.tasks[day - 1]
        root = output / f"T{day:02}"
        snapshot = read(root / "OPENING.json")
        archive_file = root / "PUBLIC_MEMORY.json"
        original = read(archive_file)
        for mode, preset in case["modes"].items():
            loss_path = root / f"LOSS_{mode}.json"
            assert preset["log_sha"] == sha(loss_path.read_bytes())
            loss = read(loss_path)
            outcomes = {"loss": loss}
            arms = {"keep": (None, None), "archive": (focal, None)}
            if sham is not None:
                arms["sham"] = (sham, None)
            if preset["named_index"]:
                arms["waive_context"] = (focal, focal)
            if preset["equal"]:
                arms["equal"] = (focal, preset["equal"][1])
            for name, (remove, fee) in arms.items():
                memory = deepcopy(original)
                if remove:
                    del memory["bindings"][remove]
                if name == "archive":
                    memory["bindings"][focal] = read(archive_file)["bindings"][focal]
                world = driver.create_world()
                try:
                    world.restore(snapshot)
                    branch, _ = episode(driver, runtime, world, task, memory, mode, fee)
                finally:
                    world.close()
                if fee:
                    index = preset["named_index"] if name == "waive_context" else preset["equal"][0]
                    assert branch["refund_index"] == index
                    assert branch["log"][:index-1] == loss["log"][:index-1]
                    a, b = branch["log"][index-1], loss["log"][index-1]
                    assert a["result"]["content"] == b["result"]["content"]
                    assert a["result"]["budget"]["charged"] == 0 and b["result"]["budget"]["charged"] == 5
                outcomes[name] = branch
            assert outcomes["keep"] == outcomes["archive"]
            if "sham" in outcomes:
                assert outcomes["sham"] == outcomes["keep"]
            if mode == "ordered":
                assert outcomes["keep"] == read(root / "CONTINUOUS_KEEP.json")
            original_set = set(loss["completed"])
            comparison = {}
            for arm, value in outcomes.items():
                final = set(value["completed"])
                comparison[arm] = dict(completed=value["completed"], budget=value["budget_used"],
                                       gained=sorted(final - original_set), lost=sorted(original_set - final),
                                       outside_gains=sorted(final - original_set - {focal}),
                                       outside_losses=sorted(original_set - final - {focal}),
                                       productive_calls=len(value["log"]),
                                       rejected=sum(step["result"]["content"]["status"] != "success"
                                                    for step in value["log"]))
            report.append(dict(day=day, mode=mode, focal=focal, paired=bool(preset["named_index"]),
                               predicted=preset["predicted"], equal_predicted=preset["predicted_equal"],
                               arms=comparison))
            write_new(root / f"CONTROL_{mode}.json", outcomes)
    write_new(output / "RESULT.json", dict(cases=report, paid_model_calls=0, api_usd=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "observe", "compare"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    spec = frozen()
    if args.stage == "freeze":
        args.out.mkdir()
        write_new(args.out / "FREEZE.json", spec)
        return
    assert spec == read(args.out / "FREEZE.json")
    sys.path.insert(0, str(SOURCE.parent))
    driver = importlib.import_module("rescopebench." + CASE.replace("/", ".") + ".driver").Driver()
    runtime = importlib.import_module("rescopebench." + CASE.replace("/", ".") + ".runtime")
    assert len(driver.tasks) == 16 and driver.lifecycle_schedule["events"][0]["before_task"] == 11
    if args.stage == "observe":
        prepare(args.out, driver, runtime)
    else:
        assert (args.out / "DIAGNOSIS_BEFORE_CONTROLS.json").is_file()
        compare(args.out, driver, runtime)


if __name__ == "__main__":
    main()
