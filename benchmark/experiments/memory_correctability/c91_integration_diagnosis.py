"""Replay a native identity-mapping receipt under fixed FinanceOps budgets."""
import argparse
from copy import deepcopy
import csv
import json
from pathlib import Path
import subprocess

import c77_financeops_receipt_transfer as c77
from c77_financeops_receipt_transfer import c74


SCRIPT = Path(__file__).resolve()
PROTOCOL = SCRIPT.with_name("C91_INTEGRATION_DIAGNOSIS_PROTOCOL.md")
ARMS = ("remove", "keep", "sham", "archive", "refund")
MODES = ("official_default", "reference_prefix")
FIELDS = ("case", "mode", "arm", "cap", "charged", "actual_calls", "added_native_read",
          "old_mapping_equal", "archive_reads", "other_completed", "other_targets",
          "packages", "total_packages", "published", "final_confirmation", "stopped")


def freeze():
    cases = [row for row in c74.read(c77.MANIFEST)["tasks"]
             if row["family"] == "heterogeneous_integration"
             and row["variant"] == "conflict_and_late_correction"
             and row["band"] in ("128k", "256k")]
    assert len(cases) == 7
    return {
        "pin": c74.PIN, "cases": cases, "arms": list(ARMS), "modes": list(MODES),
        "input_sha": {path.name: c74.sha(path) for path in
                      (SCRIPT, PROTOCOL, c77.MANIFEST, Path(c77.__file__), Path(c74.__file__))},
        "model_call_limit": 0, "api_usd_limit": 0,
    }


def mappings(event):
    response = event["result"]
    if not response["ok"] or event["arguments"].get("collection") != "sources":
        return {}
    if event["skill_id"] == "search_objects":
        objects = (entry.get("decision_metadata", {}) for entry in response["items"])
    elif event["skill_id"] == "read_object":
        objects = (response["object"],)
    else:
        return {}
    return {item["id"]: item["identity_maps"] for item in objects if "identity_maps" in item}


def execute(folder, native, initial, cap, *, prefix=(), checkpoint=None, selection=None, arm="keep"):
    _, Runtime, Witness, score = native
    folder.mkdir(parents=True)
    c74.write(folder / "project.json", initial if checkpoint is None else checkpoint)
    env = Runtime(folder, persist=False, record_calls=True)
    tape, ledger, uses, consumer = [], [], [], []
    mapping_indices = {}
    charged = 0
    boundary = None
    refresh = None
    archive_reads = []
    edit_key = selection["sham" if arm == "sham" else "target"] if selection else None

    def invoke(name, arguments):
        nonlocal charged, boundary, refresh
        if charged >= cap:
            raise c77.BudgetStop(name)
        index = len(tape) + 1
        observed = index <= len(prefix)
        if observed:
            prior = prefix[index - 1]
            assert (name, arguments) == (prior["skill_id"], prior["arguments"])
            value = prior["result"]
        else:
            value = env.call(name, arguments)
        event = dict(skill_id=name, arguments=deepcopy(arguments), result=deepcopy(value))
        tape.append(event)
        found = mappings(event)
        mapping_indices.update({key: index for key in found})
        debit = 1
        if not observed and arm in ("remove", "refund") and refresh is None:
            if name == "read_object" and edit_key in found:
                old_map = mappings(prefix[selection["old_index"] - 1])[edit_key]
                equivalent = found[edit_key] == old_map
                if equivalent and arm == "refund":
                    debit = 0
                refresh = dict(index=index, old_mapping_equal=equivalent, charge=debit)
        charged += debit
        ledger.append(dict(index=index, debit=debit, used=charged, remaining=cap - charged))
        if boundary is None and value.get("notices"):
            assert name == "execute_step" and arguments["skill_id"] == "close-stage"
            boundary = dict(index=index, stage=arguments["arguments"]["stage"], notices=value["notices"])
            if not prefix:
                c74.write(folder / "CHECKPOINT.json", env.p)
            else:
                assert index == len(prefix)
                if arm != "keep":
                    assert mapping_indices[edit_key] == selection["sham_index" if arm == "sham" else "old_index"]
                    assert "identity_maps" in controller.sources[edit_key]
                    entry = dict(controller.sources[edit_key])
                    del entry["identity_maps"]
                    controller.sources[edit_key] = entry
        return value

    class Observer(Witness):
        def solve(self, key, refresh=False):
            consumer.append(key)
            try:
                return super().solve(key, refresh)
            finally:
                assert consumer.pop() == key

        def source(self, key, refresh=False):
            before = len(tape)
            cached = self.sources.get(key, {})
            if key == edit_key and cached and "identity_maps" not in cached and not refresh:
                if arm == "archive":
                    original = mappings(prefix[selection["old_index"] - 1])[key]
                    self.sources[key] = {**cached, "identity_maps": original}
                    archive_reads.append(dict(key=key, payload_bytes=len(
                        json.dumps(original, ensure_ascii=False).encode("utf-8"))))
                else:
                    refresh = True
            result = super().source(key, refresh)
            uses.append(dict(at=len(tape), before=before, target=consumer[-1] if consumer else None,
                             key=key, origin=mapping_indices.get(key)))
            return result

    controller = Observer(invoke)
    stopped = None
    try:
        controller.run()
    except c77.BudgetStop as error:
        stopped = str(error)
    env.save()
    assert c74.read_log(folder / "actions.jsonl") == tape[len(prefix):]
    status = score(env, initial)
    missing = {error["source_id"] for error in status["errors"] if "source_id" in error}
    completed = sorted(set(initial["sources"]) - missing)
    published = bool(env.p["publication"]) and {"code": "PUBLICATION"} not in status["errors"]
    assert len(completed) == status["completed_work_packages"]
    result = dict(cap=cap, charged=charged, actual_calls=len(tape), completed_ids=completed,
                  native_score=status, published=published, boundary=boundary,
                  business_calls=sum(row["skill_id"] in c77.WRITE for row in tape),
                  archive_reads=archive_reads, extra_read=refresh, stopped_before=stopped,
                  final_confirmation=published and tape[-1]["skill_id"] == "read_project")
    c74.write(folder / "RESULT.json", result)
    c74.write(folder / "USES.json", uses)
    c74.write(folder / "LEDGER.json", ledger)
    return result


def admit(folder, case, result):
    event = result["boundary"]
    if (result["actual_calls"], result["business_calls"]) != (case["reference_calls"], case["business_calls"]):
        return {"reason": "official reference call counts differ"}
    if not result["native_score"]["task_success"] or not event:
        return {"reason": "reference unsuccessful or no native notice"}
    pivot = event["index"]
    affected = {notice["source_id"] for notice in event["notices"]}
    events = c74.read_log(folder / "actions.jsonl")
    uses = c74.read(folder / "USES.json")
    next_stage = event["stage"] + 1
    stage_sources = {}
    mapped_before = {}
    for i, row in enumerate(events, 1):
        if i <= pivot:
            mapped_before.update({key: i for key in mappings(row)})
        if i > pivot and row["skill_id"] == "search_objects" and row["arguments"]["stage"] == next_stage:
            stage_sources.update({entry["id"]: entry["decision_metadata"]["identity_source_id"]
                                  for entry in row["result"]["items"] if entry["stage"] == next_stage})
    eligible = {target: key for target, key in stage_sources.items() if {target, key}.isdisjoint(affected)}
    order = [row["arguments"]["arguments"]["source_id"] for row in events[pivot:]
             if row["arguments"].get("skill_id") == "normalize-source"
             and row["arguments"]["arguments"]["source_id"] in eligible]
    subsequent = [row for row in uses if row["before"] >= pivot]
    used_after = {row["key"] for row in subsequent}
    shams = sorted(set(mapped_before) - affected - used_after)
    if not shams:
        return {"reason": "no unused old identity receipt for sham"}
    for position, target in enumerate(order):
        key = eligible[target]
        first = next((row for row in subsequent if row["key"] == key), None)
        other = [peer for peer in order[position + 1:] if eligible[peer] != key]
        if (first and other and first["target"] == target and first["at"] == first["before"]
                and (first["origin"] or pivot + 1) <= pivot):
            return dict(target=key, consumer=target, old_index=first["origin"],
                        sham=shams[0], sham_index=mapped_before[shams[0]], other_targets=other, pivot=pivot)
    return {"reason": "no earlier reused mapping with a later unaffected distinct identity source"}


def diagnosis(result, selection):
    missing = sorted(set(selection["other_targets"]) - set(result["completed_ids"]))
    stopped = result["stopped_before"]
    if not missing and result["published"]:
        label = "confirmation_only" if stopped == "read_project" else "no_business_loss"
    else:
        label = "business_incomplete_attribution_unresolved"
    return dict(exhaustion_alert=bool(stopped and result["charged"] == result["cap"]),
                inspection_label=label, missing_other_ids=missing, stop_before=stopped)


def cap_for(case, mode):
    return c74.budget(case) if mode == MODES[0] else case["reference_calls"]


def run_reference(output, spec, native):
    for case in spec["cases"]:
        root = output / case["id"]
        root.mkdir()
        world = native[0](**case["parameters"])
        world["task_id"] += "-" + case["id"]
        assert world["task_id"] == case["task_id"]
        c74.write(root / "INITIAL.json", world)
        folder = root / "reference"
        result = execute(folder, native, world, c74.budget(case))
        selection = admit(folder, case, result)
        c74.write(root / "ADMISSION.json", selection)
        print(case["id"], result["actual_calls"], selection.get("reason", "admitted"), flush=True)


def run_arms(output, spec, native, *, controls):
    diagnostics = {}
    for case in spec["cases"]:
        root = output / case["id"]
        selection = c74.read(root / "ADMISSION.json")
        if "reason" in selection:
            continue
        source = root / "reference"
        world = c74.read(root / "INITIAL.json")
        prefix = c74.read_log(source / "actions.jsonl")[:selection["pivot"]]
        checkpoint = c74.read(source / "CHECKPOINT.json")
        for mode in MODES:
            for arm in (ARMS[1:] if controls else ARMS[:1]):
                folder = root / mode / arm
                result = execute(folder, native, world, cap_for(case, mode), prefix=prefix,
                                 checkpoint=checkpoint, selection=selection, arm=arm)
                if not controls:
                    diagnostics[folder.relative_to(output).as_posix()] = dict(
                        result_sha=c74.sha(folder / "RESULT.json"),
                        trace_sha=c74.sha(folder / "actions.jsonl"),
                        diagnosis=diagnosis(result, selection))
                print(case["id"], mode, arm, result["charged"], result["stopped_before"], flush=True)
    if not controls:
        c74.write(output / "DIAGNOSIS_BEFORE_CONTROLS.json", diagnostics)


def summarize(output, spec):
    frozen = c74.read(output / "DIAGNOSIS_BEFORE_CONTROLS.json")
    table = []
    admission = []
    effects = []
    for case in spec["cases"]:
        root = output / case["id"]
        selection = c74.read(root / "ADMISSION.json")
        admission.append(dict(case=case["id"], **selection))
        if "reason" in selection:
            continue
        for mode in MODES:
            group = root / mode
            results = {arm: c74.read(group / arm / "RESULT.json") for arm in ARMS}
            logs = {arm: c74.read_log(group / arm / "actions.jsonl") for arm in ARMS}
            remove = results["remove"]
            ref = frozen[(group / "remove").relative_to(output).as_posix()]
            assert ref["result_sha"] == c74.sha(group / "remove/RESULT.json")
            assert ref["trace_sha"] == c74.sha(group / "remove/actions.jsonl")
            assert logs["keep"] == logs["sham"] == logs["archive"]
            assert results["keep"]["completed_ids"] == results["sham"]["completed_ids"] == results["archive"]["completed_ids"]
            assert len(results["archive"]["archive_reads"]) == 1
            refund = results["refund"]
            matched_prefix = None
            if refund["extra_read"]:
                index = refund["extra_read"]["index"] - selection["pivot"]
                matched_prefix = logs["remove"][:index] == logs["refund"][:index]
                assert matched_prefix and remove["extra_read"]["old_mapping_equal"] == refund["extra_read"]["old_mapping_equal"]
            other = set(selection["other_targets"])
            missed = other - set(remove["completed_ids"])
            recovered = missed & set(refund["completed_ids"])
            effects.append(dict(case=case["id"], mode=mode, diagnosis=ref["diagnosis"],
                                same_prefix_and_native_response_through_refresh=matched_prefix,
                                refunded=bool(refund["extra_read"] and refund["extra_read"]["charge"] == 0),
                                refund_other_gains=sorted(recovered),
                                refund_all_gains=sorted(set(refund["completed_ids"]) - set(remove["completed_ids"])),
                                refund_all_losses=sorted(set(remove["completed_ids"]) - set(refund["completed_ids"])),
                                refund_publication_gain=refund["published"] and not remove["published"],
                                refund_confirmation_gain=refund["final_confirmation"] and not remove["final_confirmation"]))
            for arm, result in results.items():
                reading = result["extra_read"]
                table.append(dict(case=case["id"], mode=mode, arm=arm, cap=result["cap"], charged=result["charged"],
                                  actual_calls=result["actual_calls"], added_native_read=bool(reading),
                                  old_mapping_equal=reading["old_mapping_equal"] if reading else "",
                                  archive_reads=len(result["archive_reads"]), other_targets=len(other),
                                  other_completed=len(other & set(result["completed_ids"])),
                                  packages=len(result["completed_ids"]), total_packages=result["native_score"]["total_work_packages"],
                                  published=result["published"], final_confirmation=result["final_confirmation"],
                                  stopped=result["stopped_before"] or ""))
    with (output / "MAIN_TABLE.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(table)
    c74.write(output / "AUDIT.json", dict(admission=admission, effects=effects,
                                        comparisons=len(effects), model_calls=0, api_usd=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "reference", "diagnose", "compare", "summarize"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    assert subprocess.check_output(["git", "-C", str(c74.SOURCE), "rev-parse", "HEAD"], text=True).strip() == c74.PIN
    assert not subprocess.check_output(["git", "-C", str(c74.SOURCE), "status", "--porcelain", "--untracked-files=no"])
    spec = freeze()
    if args.stage == "freeze":
        args.out.mkdir()
        c74.write(args.out / "FREEZE.json", spec)
        return
    assert c74.read(args.out / "FREEZE.json") == spec
    if args.stage == "summarize":
        summarize(args.out, spec)
    elif args.stage == "reference":
        run_reference(args.out, spec, c77.native())
    else:
        if args.stage == "compare":
            assert (args.out / "DIAGNOSIS_BEFORE_CONTROLS.json").is_file()
        run_arms(args.out, spec, c77.native(), controls=args.stage == "compare")


if __name__ == "__main__":
    main()
