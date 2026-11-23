"""Post hoc P4 audit from saved native episodes. No model or workflow calls."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from run_p4_modelscope_audit import build_cases
from trustmem_bench.eval_ext.native_audit import (
    _get_prior_receipt, _matches_focal_reread, load_opening_snapshot, load_rescopebench_driver,
    parse_task_targets, target_id_field,
)


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def target_resolver(workflow, targets, memory):
    """Every arm uses the same task roster and the same unambiguous historical binding."""
    identifiers = {t[target_id_field(workflow)] for t in targets}
    bindings = defaultdict(set)
    if workflow == "forms":
        for target, record in memory["bindings"].items():
            bindings[record["fields"]["correction_handle"]].add(target)
    elif workflow == "medical_appointment":
        for key, record in memory["receipts"].items():
            bindings[record["source_appointment_id"]].add(json.loads(key)[0])

    fields = {
        "get_correction_context": "record_ref",
        "get_patient_scheduling_context": "patient_id",
        "retry_api_call": "call_id",
    }
    handles = {"apply_form_correction": "correction_handle",
               "create_follow_up_appointment": "source_appointment_id"}

    def resolve(action):
        tool, args = action["tool"], action["arguments"]
        if tool in fields:
            target = args.get(fields[tool])
        elif tool in handles:
            candidates = bindings.get(args.get(handles[tool]), set())
            target = next(iter(candidates)) if len(candidates) == 1 else None
        else:
            return None
        return target if target in identifiers else None

    return resolve


def validated_trace(ep):
    """Cross-check the saved tool and turn ledgers, including their accounting."""
    rows = ep["native_log"]
    turns = [turn for turn in ep["turns"] if turn.get("native_call_index") is not None]
    if len(turns) != len(rows) or len(rows) != ep["native_calls"]:
        raise ValueError("native call and turn counts disagree")
    balance = ep["initial_budget"]
    verified = []
    for i, (row, turn) in enumerate(zip(rows, turns, strict=True), 1):
        charge = row["charged"]
        if (row["native_call_index"] != i or turn["native_call_index"] != i
                or row["tool"] != turn["tool_name"] or row["arguments"] != turn["arguments"]
                or row["balance_before"] != balance or type(charge) is not int or charge < 0
                or charge != turn["charged"] or row["remaining_budget"] != balance - charge
                or row["remaining_budget"] != turn["remaining_budget"]):
            raise ValueError(f"contradictory ledgers at native call {i}")
        balance -= charge
        verified.append(dict(tool=row["tool"], arguments=row["arguments"], response=turn["nonaccounting"],
                             charge=charge, before=row["balance_before"], after=balance))
    if balance != ep["remaining_budget"] or ep["initial_budget"] - balance != ep["budget_spent"]:
        raise ValueError("terminal balance mismatch")
    return verified


def designated(trace, case, prior):
    for index, row in enumerate(trace):
        if row["charge"] > 0 and _matches_focal_reread(
                case.workflow, row["tool"], row["arguments"], row["response"], case.focal_key, prior):
            return index
    return None


def compare_dispatch(keep, remove, resolve, keep_cutoff, remove_cutoff):
    """Verify the first differing raw decision after an identical, paid prefix."""
    left, right = keep[:keep_cutoff], remove[:remove_cutoff]
    seen = set()
    for i, (a, b) in enumerate(zip(left, right)):
        if a == b:
            seen.add(resolve(a))
            continue
        if (a["tool"], a["arguments"]) == (b["tool"], b["arguments"]) or a["before"] != b["before"]:
            return {"status": "response_or_balance_diverged_first"}
        x, y = resolve(a), resolve(b)
        if x is None or y is None:
            return {"status": "ambiguous_target"}
        if x == y or x in seen or y in seen:
            return {"status": "different_action_on_same_or_previously_seen_target"}
        # A different next target alone does not establish an inversion of two common targets.
        inversion = any(resolve(row) == y for row in left[i+1:]) and any(
            resolve(row) == x for row in right[i+1:])
        return dict(status="unique_target_divergence", call=i+1, balance=a["before"],
                    keep_target=x, remove_target=y, inversion_observed=inversion)
    return {"status": "same_observed_prefix" if len(left) == len(right) else "prefix_or_suffix_only"}


def verify_fee(remove, fee, k, control):
    if k is None or not isinstance(control, dict) or len(fee) <= k:
        return False
    a, b = remove[k], fee[k]
    return (remove[:k] == fee[:k] and a["charge"] > 0 and b["charge"] == 0
            and all(a[key] == b[key] for key in ("before", "tool", "arguments", "response"))
            and b["after"] == a["after"] + a["charge"]
            and control.get("waived_at_native_index") == k + 1
            and control.get("prefix_replayed_calls") == k + 1
            and control.get("waived_cost") == a["charge"] and control.get("nonaccounting_match") is True)


def changes(before, after, direct):
    added, displaced = after - before, before - after
    return dict(net=len(after)-len(before), added=sorted(added), displaced=sorted(displaced),
                outside_added=sorted(added-direct), outside_displaced=sorted(displaced-direct))


def score_case(case, targets, memory, episodes, repeats):
    ids = {t[target_id_field(case.workflow)] for t in targets}
    direct = set(case.direct_targets)
    resolve = target_resolver(case.workflow, targets, memory)
    prior = _get_prior_receipt(case.workflow, memory, case.focal_key)
    keeps = [f"keep_r{i}" for i in range(repeats)]
    expected = [*keeps, "remove", "sham", "fee_only"]
    if case.workflow in {"forms", "medical_appointment"}:
        expected.append("archive")
    states, errors, traces, done = {}, {}, {}, {}
    for arm in expected:
        ep = episodes.get(arm)
        if ep is None or ep.get("status") != "ok":
            states[arm] = "missing" if ep is None else ep.get("status", "missing_status")
            continue
        if (ep["case_id"] != case.case_id() or ep["arm"] != arm or ep["interface"] != "native_tool_calling"
                or ep["workflow"] != case.workflow or ep["day"] != case.day
                or set(ep["direct_targets"]) != direct or ep["focal_key"] != case.focal_key
                or ep["sham_key"] != case.sham_key):
            raise ValueError(f"episode identity differs at {case.case_id()}/{arm}")
        errors[arm] = dict(stop=ep["stop_reason"], parse_errors=ep["parse_errors"],
                           invalid_args=ep["invalid_arg_errors"], write_rejections=ep["write_rejections"])
        if ep.get("grade_valid") is not True:
            states[arm] = "invalid_grade"
            continue
        completed = set(ep["completed"])
        if (not completed <= ids or ep["completed_count"] != len(completed)
                or len(ep["completed"]) != len(completed) or ep["total_targets"] != len(ids)):
            raise ValueError(f"native target set mismatch at {case.case_id()}/{arm}")
        traces[arm] = validated_trace(ep)
        done[arm] = completed
        states[arm] = "valid"
    if len({episodes[arm]["initial_budget"] for arm in done}) > 1:
        raise ValueError(f"Branches do not share an opening budget at {case.case_id()}")
    row = dict(case_id=case.case_id(), workflow=case.workflow, release_status=case.upstream_release_status,
               arms=states, stop_and_errors=errors, total=None, controls=None,
               comparison_parse_errors=None,
               outside_change_with_stable_controls=None, dispatch=None,
               reorder_with_stable_controls=None, fee_status="missing_pair", fee=None)
    if "remove" not in done:
        return row
    k = designated(traces["remove"], case, prior)
    declared = episodes["remove"]["same_value_reread"]
    if (None if declared is None else declared["native_call_index"]) != (None if k is None else k+1):
        raise ValueError(f"designated charge and raw trace disagree at {case.case_id()}")
    if k is None:
        row["fee_status"] = "no_eligible_charge"
        if "fee_only" in done:
            raise ValueError("fee episode without eligible charge")
    elif "fee_only" not in done:
        row["fee_status"] = states["fee_only"]
    elif verify_fee(traces["remove"], traces["fee_only"], k, episodes["fee_only"]["fee_only_control"]):
        change = changes(done["remove"], done["fee_only"], direct)
        row.update(fee_status="verified", fee=dict(**change, net_decrease=change["net"] < 0,
                   equal_count_swap=change["net"] == 0 and bool(change["added"]),
                   outside_displacement=bool(change["outside_displaced"]), waived_call=k+1,
                   amount=traces["remove"][k]["charge"]))
    else:
        row["fee_status"] = "prefix_or_charge_mismatch"
    if keeps[0] not in done:
        return row
    reference = done[keeps[0]]
    change = changes(done["remove"], reference, direct)
    available = all(arm in done for arm in [*keeps, "sham"])
    stable = available and all(done[arm] == reference for arm in [*keeps, "sham"])
    row.update(total=change, controls="missing_or_invalid" if not available else "stable" if stable else "disagree")
    if available:
        row["comparison_parse_errors"] = sum(len(errors[arm]["parse_errors"]) for arm in [*keeps, "sham", "remove"])
    if stable:
        row["outside_change_with_stable_controls"] = bool(change["outside_added"] or change["outside_displaced"])
    def witness(arm):
        left = traces[arm]
        return compare_dispatch(left, traces["remove"], resolve, designated(left, case, prior), k)
    primary = witness(keeps[0])
    row["dispatch"] = primary
    if stable and primary["status"] == "unique_target_divergence":
        other_witnesses = [witness(arm) for arm in [*keeps[1:], "sham"]]
        row["reorder_with_stable_controls"] = primary["inversion_observed"] and all(
            w == primary for w in other_witnesses)
    return row


def summarize(rows):
    fees = [r["fee"] for r in rows if r["fee"] is not None]
    return dict(planned_cases=len(rows), valid_total_pairs=sum(r["total"] is not None for r in rows),
                control_status_counts=dict(Counter(r["controls"] or "missing_pair" for r in rows)),
                dispatch_status_counts=dict(Counter((r["dispatch"] or {}).get("status", "missing_pair") for r in rows)),
                fee_status_counts=dict(Counter(r["fee_status"] for r in rows)),
                arm_stop_counts=dict(Counter(v["stop"] for r in rows for v in r["stop_and_errors"].values())),
                valid_stable_controls=sum(r["controls"] == "stable" for r in rows),
                outside_changes_passing_controls=sum(r["outside_change_with_stable_controls"] is True for r in rows),
                outside_changes_passing_controls_without_parse_errors=sum(
                    r["outside_change_with_stable_controls"] is True and r["comparison_parse_errors"] == 0 for r in rows),
                witnessed_reorders_passing_controls=sum(r["reorder_with_stable_controls"] is True for r in rows),
                verified_fee_pairs=len(fees), fee_net_decreases=sum(f["net_decrease"] for f in fees),
                fee_equal_count_swaps=sum(f["equal_count_swap"] for f in fees),
                fee_outside_displacements=sum(f["outside_displacement"] for f in fees))


def audit_run(run_dir, config):
    mode = config["mode"]
    if mode not in {"qualify", "main_matrix"}:
        raise ValueError(f"Unrecognized P4 run mode {mode}")
    cases = build_cases("qualify" if mode == "qualify" else config["suite"])
    if not cases:
        raise ValueError("Empty P4 case roster")
    drivers, hashes, metadata_hashes, rows = {}, {}, {}, []
    original_path = run_dir / "CASE_SUMMARIES.json"
    original = {row["case_id"]: row for row in read(original_path)} if original_path.is_file() else {}
    for case in cases:
        if case.workflow not in drivers:
            drivers[case.workflow], _ = load_rescopebench_driver(case.workflow, case.source_root)
        targets = parse_task_targets(case.workflow, drivers[case.workflow].tasks[case.day-1])
        _, memory = load_opening_snapshot(case)
        episodes = {}
        for path in sorted((run_dir/case.case_id()).glob("native__*/EPISODE.json")):
            arm = path.parent.name.removeprefix("native__")
            hashes[path.relative_to(run_dir).as_posix()] = digest(path)
            episodes[arm] = read(path)
            meta_path = path.with_name("BRANCH_META.json")
            if meta_path.is_file():
                meta = read(meta_path)
                expected = {k: config[k] for k in (
                    "model", "temperature", "max_output_tokens", "extra_body", "endpoint_profile")}
                expected.update(case_id=case.case_id(), arm=arm, interface="native",
                                seed=config["base_seed"] + (int(arm[6:]) if arm.startswith("keep_r") else 0))
                if any(meta.get(k) != v for k, v in expected.items()):
                    raise ValueError(f"Branch metadata and run configuration differ at {case.case_id()}/{arm}")
                tape = path.with_name("model_calls.jsonl")
                if bool(meta["tape_exists"]) != tape.is_file() or (tape.is_file() and digest(tape) != meta["tape_sha256"]):
                    raise ValueError(f"Recorded model tape differs from branch metadata at {case.case_id()}/{arm}")
                metadata_hashes[meta_path.relative_to(run_dir).as_posix()] = digest(meta_path)
        repeats = 3 if mode == "main_matrix" and case.workflow == "forms" else 2
        row = score_case(case, targets, memory, episodes, repeats)
        old = original.get(case.case_id(), {})
        total = old.get("total_effect") or {}
        row["original_flags"] = {
            "pre_charge_dispatch_changed": total.get("pre_charge_dispatch_changed"),
            "signal_above_keep_and_sham_noise": total.get("signal_above_keep_and_sham_noise"),
            "direction_reversal": (old.get("fee_only_effect") or {}).get("direction_reversal"),
        }
        rows.append(row)
    return dict(schema="trustmem/p4-posthoc-review/v1", mode=mode, suite=config["suite"],
                slot=config["slot"], model=config["model"], config_sha256=digest(run_dir/"RUN_CONFIG.json"),
                original_summaries_sha256=digest(original_path) if original_path.is_file() else None,
                episode_hashes=hashes, branch_metadata_hashes=metadata_hashes,
                all_recorded_episodes_have_metadata=bool(hashes) and len(hashes) == len(metadata_hashes),
                cases=rows, all_cases=summarize(rows),
                released=summarize([r for r in rows if r["release_status"] == "released"]),
                candidate=summarize([r for r in rows if r["release_status"] != "released"]))


def verify_runner_bundle(path):
    """Compare the returned program and actual snapshot bytes with the local freeze."""
    local = read(Path(__file__).with_name("P4_MODELSCOPE_FREEZE.json"))
    expected = {"P4_MODELSCOPE_MULTIMODEL_AUDIT_PROTOCOL.md": local["protocol_sha256"]}
    for name, checksum in local["code_hashes"].items():
        member = f"trustmem_bench/{name}" if name.startswith("eval_ext/") else name
        expected[member] = checksum
    for case in build_cases("all"):
        for kind, opening in (("world", case.opening_world_path), ("memory", case.opening_memory_path)):
            if opening is None:
                continue
            checksum = local["opening_snapshot_hashes"][f"{case.case_id()}:{kind}"]
            if digest(opening) != checksum:
                raise ValueError(f"Local {kind} differs from the frozen opening of {case.case_id()}")
            folder = f"forms/T{case.day:02d}" if case.workflow == "forms" else "p3"
            expected[f"snapshots/{folder}/{opening.name}"] = checksum
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate members in supplied runner")
        for name, checksum in expected.items():
            if sha256(archive.read(name)).hexdigest() != checksum:
                raise ValueError(f"Returned bundle differs from the reviewed freeze: {name}")
        manifest = json.loads(archive.read("P4_MODELSCOPE_FREEZE.json"))
        for field in ("code_hashes", "protocol_sha256", "opening_snapshot_hashes"):
            if manifest[field] != local[field]:
                raise ValueError(f"Returned freeze manifest differs at {field}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-bundle", type=Path, help="Actual archived runner supplied with this run")
    parser.add_argument("--replay-report", type=Path, help="Existing frozen runner's REPLAY_VERIFICATION.json")
    args = parser.parse_args()
    report = audit_run(args.run_dir, read(args.run_dir/"RUN_CONFIG.json"))
    report["offline_replay_check"] = None
    if args.replay_report:
        replay = read(args.replay_report)
        checked = {}
        for entry in replay["rows"]:
            if entry["interface"] == "native":
                key = (entry["case_id"], entry["arm"])
                if key in checked:
                    raise ValueError(f"Duplicate native arm in replay report: {key}")
                checked[key] = entry
        for name in report["episode_hashes"]:
            ep = read(args.run_dir / name)
            check = checked.pop((ep["case_id"], ep["arm"]), {})
            if check.get("matched") is not True or ep["status"] != check.get("status"):
                raise ValueError(f"Missing or failed replay check for {name}")
            if ep["status"] == "ok" and any(
                    ep[k] != check[k] for k in ("completed", "budget_spent")):
                raise ValueError(f"Replay endpoints differ at {name}")
        if checked or replay.get("all_matched") is not True or not report["episode_hashes"]:
            raise ValueError("Replay report does not match this run")
        report["offline_replay_check"] = dict(sha256=digest(args.replay_report),
                                             recorded_native_branches=len(report["episode_hashes"]))
    report["supplied_runner_bundle_sha256"] = digest(args.run_bundle) if args.run_bundle else None
    if args.run_bundle:
        verify_runner_bundle(args.run_bundle)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report["all_cases"]))


if __name__ == "__main__":
    main()

