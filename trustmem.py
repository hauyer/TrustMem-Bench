"""Inspect the development task catalog; no benchmark execution is performed."""
import argparse
from collections import Counter
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "catalog.json"
FORBIDDEN = {"answer", "answers", "independent_expected", "expected", "gold", "scoring", "ordinary_coverage_check", "marginal_status", "marginal_bounds", "reference_action", "same_margins_witness", "scoring_path"}

def validate(catalog):
    records = catalog["tasks"]
    ids = set()
    groups = {}
    def check(value):
        if isinstance(value, dict):
            if FORBIDDEN.intersection(value):
                raise ValueError("scoring field in task catalog")
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
    for record in records:
        check(record)
        if record["id"] in ids:
            raise ValueError("duplicate task ID")
        ids.add(record["id"])
        group, family = record["archive_group"], record["history_family"]
        if group in groups and groups[group] != family:
            raise ValueError("archive group has multiple families")
        groups[group] = family
    return {"records": len(records), "source_families": len(set(groups.values())), "archive_groups": len(groups), "records_by_family": dict(Counter(r["history_family"] for r in records)), "independent_trajectory_count": None, "legacy_catalog_execution_available": False, "development_runtime_available": True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("task_id")
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    stats = validate(catalog)
    if args.command == "summary":
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        matches = [item for item in catalog["tasks"] if item["id"] == args.task_id]
        if not matches:
            parser.error("unknown task ID")
        print(json.dumps(matches[0], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
