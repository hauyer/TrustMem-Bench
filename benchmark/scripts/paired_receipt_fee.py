"""Recount the post hoc receipt/fee comparison from primary P4 runs and P3 counts."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def episode(run, report, case, arm):
    key = f"{case['case_id']}/native__{arm}/EPISODE.json"
    raw = (run / key).read_bytes()
    if hashlib.sha256(raw).hexdigest() != report["episode_hashes"][key]:
        raise ValueError(f"Frozen episode digest differs for {key}")
    ep = json.loads(raw)
    if (ep["case_id"], ep["arm"], ep["status"], ep["grade_valid"]) != (case["case_id"], arm, "ok", True):
        raise ValueError(f"Ineligible endpoint for {key}")
    if len(set(ep["completed"])) != ep["completed_count"]:
        raise ValueError(f"Completion identity/count discrepancy for {key}")
    return ep


def summarize(report_path, runs):
    report = json.loads(report_path.read_bytes())
    run = runs / report_path.stem
    cases = [c for c in report["cases"] if c["release_status"] == "released"]
    expected = {(w, f"{w}-T{d}") for w in ("forms", "medical_appointment") for d in range(11, 17)}
    if len(cases) != len(expected) or {(c["workflow"], c["case_id"]) for c in cases} != expected:
        raise ValueError(f"Opening roster mismatch in {run.name}")
    counts = Counter()
    workflow = {}
    for case in cases:
        adds = workflow.setdefault(case["workflow"], Counter())
        repeats = [arm for arm in case["arms"] if arm.startswith("keep_r")]
        if len(repeats) < 2:
            raise ValueError("Missing retention repeat")
        raw = {arm: episode(run, report, case, arm) for arm in [*repeats, "sham", "remove", "archive"]}
        sets = {arm: set(ep["completed"]) for arm, ep in raw.items()}
        keep, remove, archive = (sets[arm] for arm in ("keep_r0", "remove", "archive"))
        stable = all(sets[arm] == keep for arm in [*repeats, "sham"])
        if stable != (case["controls"] == "stable"):
            raise ValueError(f"Control classification differs for {case['case_id']}")
        adds.update(openings=1, keep=len(keep), remove=len(remove), archive=len(archive),
                    requests=raw["remove"]["total_targets"], lookup_openings=int(raw["archive"]["archive_lookups"] > 0),
                    archive_remove_sets_differ=int(archive != remove))
        if case["fee_status"] != "verified":
            continue
        counts["fee_verified"] += 1
        fee = set(episode(run, report, case, "fee_only")["completed"])
        outside = (fee - remove) - set(raw["remove"]["direct_targets"])
        if outside != set(case["fee"]["outside_added"]) or len(fee)-len(remove) != case["fee"]["net"]:
            raise ValueError(f"Fee adjudication differs for {case['case_id']}")
        if stable:
            counts.update(eligible=1, keep_equals_fee=int(keep == fee), keep_equals_remove=int(keep == remove),
                          null_with_outside_addition=int(keep == remove and bool(outside)),
                          null_with_outside_addition_and_net_gain=int(keep == remove and bool(outside) and len(fee) > len(remove)))
    return dict(slot=report["slot"], model=report["model"], **counts), workflow


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", type=Path, required=True, help="Directory of the three signed-off main per-model scoring reports")
    ap.add_argument("--runs", type=Path, required=True, help="Permitted original p4_runs directory")
    ap.add_argument("--p3-table", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    with args.p3_table.open(encoding="utf-8", newline="") as source:
        p3 = next(r for r in csv.DictReader(source) if r["cohort"] == "all_five")
    n = int(p3["charge_eligible"])
    if int(p3["fee_matches_archive"]) != n or p3["keep_equals_archive"] != p3["eligible"]:
        raise ValueError("P3 aggregate no longer implies the required identity comparisons")
    paired = [dict(slot="P3", model="Fixed controllers", fee_verified=n, eligible=n, keep_equals_fee=n,
                   keep_equals_remove=n-int(p3["changes_with_charge"]), null_with_outside_addition=0,
                   null_with_outside_addition_and_net_gain=0)]
    archive = []
    for slot in "ABC":
        report, = args.scores.glob(f"slot{slot}_*_main.json")
        row, workflows = summarize(report, args.runs)
        if row["slot"] != slot:
            raise ValueError(f"Model slot mismatch for {report}")
        paired.append(row)
        archive.extend(dict(slot=slot, workflow=name, **counts) for name, counts in sorted(workflows.items()))
    args.out.mkdir(exist_ok=True, parents=True)
    write_csv(args.out / "RECEIPT_FEE_PAIRED.csv", paired)
    write_csv(args.out / "ARCHIVE_THREE_ARMS.csv", archive)


if __name__ == "__main__":
    main()
