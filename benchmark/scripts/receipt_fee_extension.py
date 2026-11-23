"""Recount the two native-model cohorts from the original, hash-pinned result tapes."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
import tarfile

ARCHIVES = {
    "P4": "d86e8da54d101a1b8a88721285496fe7bb7bb45a4b34f4fe3df36c8de5f7ada6",
    "P4b": "f2347193cffaec118a6d68f5f3942ac75f097c4bfe088e82f07fb924b25015fd",
}
ROSTERS = {
    "P4": {"forms": range(11, 17), "medical_appointment": range(11, 17)},
    "P4b": {"backup_recovery": [5, 6, 8, 9, 10, 11, 12, 13, 14, 15], "railway_ticketing": range(9, 17)},
}


def completed(ep):
    if ep["status"] != "ok" or not ep["grade_valid"]:
        raise ValueError("Unavailable native grade")
    ids = set(ep["completed"])
    if len(ids) != ep["completed_count"] or len(ids) != len(ep["completed"]):
        raise ValueError("Ambiguous completed set")
    return ids


def count_case(phase, slot, arms):
    remove = arms["remove"]
    keep, loss, archive = (completed(arms[name]) for name in ("keep_r0", "remove", "archive"))
    repetitions = sorted(name for name in arms if name.startswith("keep_r"))
    expected = 2 if phase == "P4" and remove["workflow"] == "medical_appointment" else 3
    assert repetitions == [f"keep_r{i}" for i in range(expected)]
    stable = all(completed(arms[name]) == keep for name in repetitions)
    sham = arms["sham"]
    if sham["status"] == "ok":
        control = "matched" if completed(sham) == keep else "mismatched"
    elif sham["status"] == "ineligible_no_sham_key":
        control = "unavailable"
    else:
        raise ValueError(sham["status"])
    direct = set(remove["direct_targets"])
    fee = arms["fee_only"]
    row = dict(phase=phase, slot=slot, workflow=remove["workflow"], opening=remove["day"],
               keep_stable=int(stable), sham=control, requests=remove["total_targets"],
               keep_count=len(keep), remove_count=len(loss), archive_count=len(archive),
               archive_lookups=arms["archive"]["archive_lookups"], archive_matches_keep=int(archive == keep),
               outside_changed=int(bool((keep ^ loss) - direct)), direct_changed=int(bool((keep ^ loss) & direct)),
               fee_status=fee["status"], waived=0, fee_count="", cohort="excluded", pattern="", fee_net_down="")
    if fee["status"] == "ineligible_no_same_value_reread":
        return row
    relaxed = completed(fee)
    ctrl = fee["fee_only_control"]
    receipt = remove["same_value_reread"]
    at = ctrl["waived_at_native_index"]
    paid, waived = remove["native_log"][:at], fee["native_log"][:at]
    assert len(paid) == len(waived) == ctrl["prefix_replayed_calls"] == at == receipt["native_call_index"]
    assert ctrl["nonaccounting_match"] and receipt["cost"] == ctrl["waived_cost"] == paid[-1]["charged"] > 0
    assert waived[-1]["waived_charge"] and waived[-1]["charged"] == 0
    for a, b in zip(paid, waived):
        assert all(a[k] == b[k] for k in ("tool", "arguments", "status", "native_call_index"))
    if keep == relaxed:
        pattern = "all_equal" if keep == loss else "same_changed_set"
    elif relaxed == loss:
        pattern = "receipt_only"
    elif keep == loss:
        pattern = "fee_only_outside_gain" if len(relaxed) > len(loss) and (relaxed - loss) - direct else "fee_only_other"
    else:
        pattern = "three_distinct"
    cohort = "excluded"
    if stable and control == "matched":
        cohort = "sham_matched"
    elif stable and control == "unavailable":
        cohort = "no_sham"
    row.update(waived=ctrl["waived_cost"], fee_count=len(relaxed), cohort=cohort,
               pattern=pattern, fee_net_down=int(len(relaxed) < len(loss)))
    return row


def load_phase(phase, path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != ARCHIVES[phase]:
        raise ValueError(f"Unexpected archive for {phase}")
    cases = defaultdict(dict)
    with tarfile.open(path) as tape:
        for member in tape:
            parts = PurePosixPath(member.name).parts
            if len(parts) != 5 or parts[-1] != "EPISODE.json":
                continue
            _, run, case, branch, _ = parts
            if not run.endswith("_main") or not branch.startswith("native__"):
                continue
            if case.rsplit("-T", 1)[0] not in ROSTERS[phase]:
                continue
            slot = run.split("slot", 1)[1][0]
            if slot not in ("A", "B", "C"):
                continue
            key = branch.removeprefix("native__")
            ep = json.load(tape.extractfile(member))
            assert ep["case_id"] == case and ep["arm"] == key and key not in cases[slot,case]
            cases[slot,case][key] = ep
    expected = {(slot,f"{w}-T{i:02d}") for slot in "ABC" for w,days in ROSTERS[phase].items() for i in days}
    if cases.keys() != expected:
        raise ValueError(f"Frozen roster mismatch for {phase}")
    return [count_case(phase, slot, arms) for (slot,_),arms in sorted(cases.items())]


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["cohort"] != "excluded":
            groups[row["phase"],row["cohort"],row["slot"]].append(row)
    output = []
    for (phase,cohort,slot), items in sorted(groups.items()):
        counts = Counter(row["pattern"] for row in items)
        output.append(dict(phase=phase, cohort=cohort, slot=slot, eligible=len(items),
                           **{k:counts[k] for k in ("all_equal","same_changed_set","receipt_only",
                                                   "fee_only_outside_gain","fee_only_other","three_distinct")},
                           fee_net_down=sum(int(row["fee_net_down"]) for row in items)))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p4", type=Path, required=True)
    parser.add_argument("--p4b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = load_phase("P4", args.p4) + load_phase("P4b", args.p4b)
    args.out.mkdir(parents=True, exist_ok=True)
    write(args.out/"NATIVE_OPENINGS.csv", rows)
    write(args.out/"NATIVE_CONTROL_STRATA.csv", summarize(rows))


if __name__ == "__main__":
    main()

