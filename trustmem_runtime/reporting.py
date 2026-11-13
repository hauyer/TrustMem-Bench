"""Human-readable and row-level exports from completed, unchanged run results."""
import csv
import json
from pathlib import Path


def write_report(suite):
    suite = Path(suite)
    destinations = [suite/"SUMMARY.md",suite/"tasks.csv"]
    if any(path.exists() for path in destinations):
        raise FileExistsError("Do not overwrite an existing report")
    results = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(suite.glob("c*/result.json"))]
    if not results:
        raise ValueError("No completed run result files")
    lines = ["# Development benchmark results", "",
        "Each row is one complete correlated stream. No pooled independent-sample or novel-method claim.", "",
        "Source bytes below are post-history logical file reads. Initial history, identity checks, scoring, memory, transport and model costs remain separate in the original JSON. Missing metrics are unknown, not zero.", "",
        "| Case | Policy | Supported correct / planned | Wrong | Deferred | Unfinished | Unsupported submits | Evidence conflicts | Source bytes after history | Initial history bytes | Memory DB bytes | Backend DB bytes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    rows = []
    for result in results:
        unfinished = result.get("agent_failures",0)+result.get("step_limits",0)
        history_bytes = result.get("shared_history_scan",{}).get("source_read_bytes")
        values = [result["case_id"],result["policy"],f'{result["supported_correct"]}/{result["sessions"]}',
            result.get("incorrect_submissions"),result.get("abstentions"),unfinished,
            result.get("unsupported_submissions"),result.get("contradictory_submissions"),
            result.get("source_read_bytes_after_history"),history_bytes,result.get("sqlite_file_bytes"),
            result.get("tool_cache_sqlite_bytes")]
        lines.append("| "+" | ".join("unknown" if v is None else str(v) for v in values)+" |")
        for event in result["events"]:
            row = {key:result.get(key) for key in ("case_id","history_group","split","mechanism","policy")}
            row.update({key:event.get(key) for key in ("session","source_id","status","submitted_value","correct",
                "supported_correct","unsupported_submission","contradicts_declared_evidence",
                "source_read_bytes","policy_invocations","memory_written_payload_bytes","cited_saved_evidence")})
            row["request"] = json.dumps(event["request"],sort_keys=True,separators=(",",":"))
            rows.append(row)
    lines += ["", "External process invocations are not model calls. Raw `result.json`, per-task deliveries, observations and process traces remain the authority. Tool caches are common persistent state, not proof of explicit agent memory use.", ""]
    destinations[0].write_text("\n".join(lines),encoding="utf-8")
    with destinations[1].open("x",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
