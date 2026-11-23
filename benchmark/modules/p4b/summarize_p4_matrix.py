"""Aggregate multi-model P4 ModelScope runs into a master CSV and Markdown report."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def collect_runs(runs_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cfg_path in sorted(runs_root.glob("*/RUN_CONFIG.json")):
        run_dir = cfg_path.parent
        cfg = _load_json(cfg_path)
        agg = _load_json(run_dir / "AGGREGATE_REPORT.json")
        qual = _load_json(run_dir / "QUALIFICATION_VERDICT.json")
        replay = _load_json(run_dir.parent / f"{run_dir.name}_replay_check" / "REPLAY_VERIFICATION.json")
        if replay is None:
            replay = _load_json(run_dir / "REPLAY_VERIFICATION.json")
        rows.append(
            {
                "run_name": run_dir.name,
                "config": cfg,
                "aggregate": agg,
                "qualification": qual,
                "replay": replay,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    out_dir = args.out_dir or args.runs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = collect_runs(args.runs_dir)

    csv_fields = [
        "run_name",
        "mode",
        "slot",
        "model",
        "cohort",
        "workflows",
        "paired_cases",
        "keep_set_stable",
        "sham_matches_keep",
        "total_set_changed",
        "outside_changed",
        "pre_charge_dispatch_changed",
        "same_value_reread_triggered",
        "signal_above_noise",
        "missed_by_total_only",
        "missed_by_direct_only",
        "missed_by_both_counts",
        "fee_eligible",
        "fee_set_changed",
        "fee_outside_changed",
        "fee_direction_reversals",
        "fee_prefix_calls_saved",
        "archive_tested",
        "archive_used",
        "archive_matches_keep",
        "replay_all_matched",
        "qual_verdict",
    ]

    flat_rows: list[dict[str, Any]] = []
    md_lines = [
        "# P4 Multi-Model Native Tool-Calling Counterfactual Audit Summary",
        "",
        "| Run | Mode | Slot | Model | Cohort | Cases | Keep Stable | Sham=Keep | Total Chg | Outside Chg | Pre-Charge Reorder | Signal > Noise | Fee Eligible | Fee Outside Chg | Fee Reversals | Archive Used | Replay OK |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for item in runs:
        cfg = item["config"] or {}
        agg = item["aggregate"] or {}
        qual = item["qualification"] or {}
        replay = item["replay"] or {}
        replay_ok = replay.get("all_matched") if replay else None
        qual_verdict = qual.get("verdict", "")

        for cohort_key in ("released_only", "candidate_model_validation", "all_workflows"):
            block = agg.get(cohort_key)
            if not block or int(block.get("paired_cases", 0)) == 0:
                continue
            row = {
                "run_name": item["run_name"],
                "mode": cfg.get("mode", ""),
                "slot": cfg.get("slot", ""),
                "model": cfg.get("model", ""),
                "cohort": cohort_key,
                "workflows": ",".join(block.get("workflows", [])),
                "paired_cases": block["paired_cases"],
                "keep_set_stable": block["keep_set_stable"],
                "sham_matches_keep": block["sham_matches_keep"],
                "total_set_changed": block["total_set_changed"],
                "outside_changed": block["outside_changed"],
                "pre_charge_dispatch_changed": block["pre_charge_dispatch_changed"],
                "same_value_reread_triggered": block["same_value_reread_triggered"],
                "signal_above_noise": block["signal_above_keep_and_sham_noise"],
                "missed_by_total_only": block["missed_by_total_count_only"],
                "missed_by_direct_only": block["missed_by_direct_target_only"],
                "missed_by_both_counts": block["missed_by_both_counts"],
                "fee_eligible": block["fee_only_eligible"],
                "fee_set_changed": block["fee_only_set_changed"],
                "fee_outside_changed": block["fee_only_outside_changed"],
                "fee_direction_reversals": block["fee_only_direction_reversals"],
                "fee_prefix_calls_saved": block["fee_only_prefix_calls_saved"],
                "archive_tested": block["archive_tested"],
                "archive_used": block["archive_used"],
                "archive_matches_keep": block["archive_matches_keep_set"],
                "replay_all_matched": replay_ok,
                "qual_verdict": qual_verdict,
            }
            flat_rows.append(row)
            md_lines.append(
                f"| {row['run_name']} | {row['mode']} | {row['slot']} | {row['model']} | {cohort_key} | "
                f"{row['paired_cases']} | {row['keep_set_stable']} | {row['sham_matches_keep']} | "
                f"{row['total_set_changed']} | {row['outside_changed']} | {row['pre_charge_dispatch_changed']} | "
                f"{row['signal_above_noise']} | {row['fee_eligible']} | {row['fee_outside_changed']} | "
                f"{row['fee_direction_reversals']} | {row['archive_used']}/{row['archive_tested']} | {replay_ok} |"
            )

    # Append menu-vs-native section if present
    menu_rows = []
    for item in runs:
        agg = item["aggregate"] or {}
        comp = agg.get("interface_sensitivity_menu_vs_native") or []
        if comp:
            keep_same = sum(bool(x["keep_same_set"]) for x in comp)
            rem_same = sum(bool(x["remove_same_set"]) for x in comp)
            menu_rows.append((item["run_name"], (item["config"] or {}).get("model", ""), len(comp), keep_same, rem_same))

    if menu_rows:
        md_lines.extend(
            [
                "",
                "## Same-Exact-Weight Menu vs Native Interface Sensitivity (Forms)",
                "",
                "| Run | Model | Batches | Keep Same Set | Remove Same Set |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for name, model, n, ks, rs in menu_rows:
            md_lines.append(f"| {name} | {model} | {n} | {ks}/{n} | {rs}/{n} |")

    csv_path = out_dir / "P4_MASTER_TABLE.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(flat_rows)

    md_path = out_dir / "P4_MASTER_SUMMARY.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Wrote {csv_path} ({len(flat_rows)} rows) and {md_path}")


if __name__ == "__main__":
    main()
