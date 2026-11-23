"""Independently re-adjudicate Table 7 from per-arm completed request-set identities.

The default run checks the 90 published model x opening rows across P4 and P4b.
Use --summary-only with a CSV of the same schema to summarize other cohorts.
Encoding:
  - Per-opening local request aliases (q1, q2, ...) are consistent across arms
    and models within the same (workflow, opening).
  - '{}' denotes a completed run that delivered zero requests.
  - 'NA' denotes an unavailable arm or repeat (e.g., no sham key, no third keep
    repeat in P4 medical_appointment, or no qualifying same-value fee reread).
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def parse_set(cell: str):
    if cell == "NA":
        return None
    if cell == "{}":
        return frozenset()
    return frozenset(cell.split())


def verify(csv_path: Path, *, check_published: bool = True) -> dict:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if check_published and len(rows) != 90:
        raise ValueError(f"Expected 90 rows, found {len(rows)}")

    table7 = defaultdict(Counter)
    matched_openings = set()
    matched_diff_openings = set()
    by_workflow_matched = defaultdict(Counter)
    seen = set()

    for idx, row in enumerate(rows, 1):
        key = (row["phase"], row["model"], row["workflow"], int(row["opening"]))
        if key in seen:
            raise ValueError(f"Row {idx}: duplicate model-opening key {key}")
        seen.add(key)
        k0 = parse_set(row["keep_r0"])
        k1 = parse_set(row["keep_r1"])
        k2 = parse_set(row["keep_r2"])
        sham = parse_set(row["sham"])
        rm = parse_set(row["remove"])
        fee = parse_set(row["fee_only"])
        direct = parse_set(row["direct_scope"])
        verified_fee = int(row["verified_fee"])

        keep_reps = [s for s in (k0, k1, k2) if s is not None]
        keep_stable = (k0 is not None and len(keep_reps) >= 2 and all(s == k0 for s in keep_reps))
        sham_available = (sham is not None)
        sham_matches = (sham_available and sham == k0)

        if verified_fee != 1 or not keep_stable or rm is None or fee is None:
            control_group = "excluded"
        elif sham_available:
            control_group = "sham_matched" if sham_matches else "excluded"
        else:
            control_group = "no_sham"

        if row["control_group"] != control_group:
            raise AssertionError(f"Row {idx}: control_group={row['control_group']} != derived {control_group}")

        if control_group == "excluded":
            if row["observed_relation"] != "NA":
                raise AssertionError(f"Row {idx}: excluded row must have observed_relation=NA")
            continue

        if k0 == rm == fee:
            bucket, relation = "all_equal", "all_equal"
        elif k0 == fee and k0 != rm:
            bucket, relation = "both_same", "same_changed_set"
        elif fee == rm and k0 != rm:
            bucket, relation = "receipt_only", "receipt_only"
        elif k0 == rm and fee != rm:
            bucket = "fee_only"
            added_outside = (fee - rm) - direct
            displaced = rm - fee
            relation = "fee_only_outside_gain" if (added_outside and not displaced) else "fee_only_other"
        else:
            bucket, relation = "distinct", "three_distinct"

        if row["observed_relation"] != relation:
            raise AssertionError(f"Row {idx}: observed_relation={row['observed_relation']} != derived {relation}")

        cohort = (row["phase"], control_group)
        table7[cohort]["pairs"] += 1
        table7[cohort][bucket] += 1

        if control_group == "sham_matched":
            op = (row["workflow"], int(row["opening"]))
            matched_openings.add(op)
            by_workflow_matched[row["workflow"]]["pairs"] += 1
            if k0 != fee:
                matched_diff_openings.add(op)
                by_workflow_matched[row["workflow"]]["different"] += 1
            else:
                by_workflow_matched[row["workflow"]]["identical"] += 1

    columns = ("pairs", "all_equal", "both_same", "receipt_only", "fee_only", "distinct")
    cohort_counts = {
        f"{phase}_{group}": {name: counts[name] for name in columns}
        for (phase, group), counts in table7.items()
    }
    totals = Counter()
    for counts in by_workflow_matched.values():
        totals.update(counts)
    if check_published:
        expected = {
            "P4_sham_matched": {"pairs": 25, "all_equal": 11, "both_same": 0, "receipt_only": 3, "fee_only": 8, "distinct": 3},
            "P4b_sham_matched": {"pairs": 4, "all_equal": 2, "both_same": 0, "receipt_only": 2, "fee_only": 0, "distinct": 0},
            "P4b_no_sham": {"pairs": 14, "all_equal": 6, "both_same": 0, "receipt_only": 6, "fee_only": 1, "distinct": 1},
        }
        if cohort_counts != expected:
            raise ValueError(f"Computed Table 7 differs from the published counts: {cohort_counts}")
        observed = (totals["pairs"], totals["identical"], totals["different"],
                    len(matched_openings), len(matched_diff_openings))
        if observed != (29, 13, 16, 15, 10):
            raise ValueError(f"Computed matched-cohort totals differ from the publication: {observed}")

    return {
        "rows_verified": len(rows),
        "table7_native_cohorts": cohort_counts,
        "sham_matched_summary": {
            "pairs": totals["pairs"],
            "distinct_openings": len(matched_openings),
            "identical_keep_vs_fee": totals["identical"],
            "different_keep_vs_fee": totals["different"],
            "different_distinct_openings": len(matched_diff_openings),
            "by_workflow": {wf: dict(cnt) for wf, cnt in sorted(by_workflow_matched.items())},
        },
        "verdict": "PASS" if check_published else "SUMMARIZED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).resolve().parent / "NATIVE_REQUEST_SETS_REVIEW.csv",
        help="Path to NATIVE_REQUEST_SETS_REVIEW.csv",
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Check row labels and report observed counts without comparing with the published cohort.",
    )
    args = parser.parse_args()
    result = verify(args.csv, check_published=not args.summary_only)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
