"""Reproduce the combined v2/v3/v4 pilot analysis, preserving phase denominators."""
from collections import Counter,defaultdict
import json
from pathlib import Path

root=Path.cwd();base=root/"artifacts/research_decisions";out=base/"20261113-confirmation-pilot-v4"
load=lambda p:json.loads(p.read_bytes())
result=load(out/"models/results.json");rows=[]
for entry in result["scored"]:
    folder=out/"models"/f"g{entry['group']:02}-{entry['backend']}"/entry["mode"]
    events=load(folder/"events.json");score=entry["score"];failures=[]
    for event in events:
        if event["status"]=="interface_failure":
            p=folder/event["session_id"]/f"t{event['actual_invocations']-1}-response.json"
            failures.append(load(p) if p.exists() else dict(transport_or_json_failure=True))
    rows.append(dict(case=entry["case"],backend=entry["backend"],mode=entry["mode"],planned=8,executed=score["executed"],
        correct=score["correct"],wrong=score["wrong"],unfinished=score["unfinished"],abstained=score["abstained"],
        source_read_bytes=score["source_read_bytes"],archive_read_payload_bytes=score["archive_read_payload_bytes"],
        query_calls=sum(e["query_calls"] for e in events),recover_calls=sum(e["recover_calls"] for e in events),
        save_calls=sum(e["save_calls"] for e in events),input_payload_bytes=sum(e["observation_payload_bytes"] for e in events),
        interface_failures=len(failures),format_failure_responses=failures,
        final_support=dict(Counter(r["authentication"][-1]["support"]["status"] for r in score["rows"])),
        wrong_after_authenticated_support=sum(r["wrong"] and r["authentication"][-1]["support"]["status"]=="sufficient" for r in score["rows"]),
        invalid_final_receipt_occurrences=sum(r["authentication"][-1]["invalid_content"] for r in score["rows"]),
        bootstrap=next(r["bootstrap"] for r in result["completed"] if r["group"]==entry["group"] and r["mode"]==entry["mode"])))
ledger=[]
for version in ("v2","v3","v4"):
    path=base/f"20261113-confirmation-pilot-{version}/models/api/model_calls.jsonl"
    ledger.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
roles=defaultdict(lambda:dict(calls=0,input_tokens=0,output_tokens=0,estimated_peak_usd=0.0,usage_unknown=0))
for record in ledger:
    role=record["call_id"].rsplit("-",1)[-1];row=roles[role];row["calls"]+=1
    usage=record.get("response",{}).get("usage")
    if usage:row["input_tokens"]+=usage["prompt_tokens"];row["output_tokens"]+=usage["completion_tokens"]
    else:row["usage_unknown"]+=1
    row["estimated_peak_usd"]+=record.get("estimated_peak_usd",record["reserve_usd"])
summary=dict(parent_planned_positions=96,eligible_positions=48,resource_excluded_positions=48,
    executed_positions=sum(r["executed"] for r in rows),correct=sum(r["correct"] for r in rows),wrong=sum(r["wrong"] for r in rows),
    unfinished=sum(r["unfinished"] for r in rows),abstained=sum(r["abstained"] for r in rows),interface_failures=sum(r["interface_failures"] for r in rows),
    api_requests=len(ledger),received_model_responses=sum("response" in r for r in ledger),
    known_usage_requests=sum("usage" in r.get("response",{}) for r in ledger),unknown_usage_requests=sum("usage" not in r.get("response",{}) for r in ledger),
    estimated_peak_usd=sum(r["estimated_peak_usd"] for r in roles.values()),invoice_observed=False,roles=dict(roles),rows=rows,
    failure=result["failure"],histories=1,scope="adaptive development pilot; all first outputs and first7 positions retained, no per-state retries; format contract is underspecified for action field")
path=out/"analysis.json"
if path.exists():assert load(path)==summary,"Do not silently change previously reported analysis"
else:path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:v for k,v in summary.items() if k not in ("rows","roles")},ensure_ascii=False))
