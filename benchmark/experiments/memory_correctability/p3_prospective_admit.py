"""Document static candidate screening, then qualify only with a cold prefix."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

from p3_prospective_audit_increment import HERE, ROOT, RUN, cold, read, sha, write


SCREEN = {
    "api_reliability": ("search_recovery_evidence", "failure_signal and operation_class are public before dispatch"),
    "backup_recovery": ("search_protection_policy_evidence", "service_tier and data_class are public; use returned routing epoch"),
    "emergency_response": (None, "All 64 request codes differ. Coordination-policy scope requires a new paid order read and is absent from public batch targets. May qualify under a common paid prefix in another protocol."),
    "k8s_operations": ("inspect_release_policy", "workload, change-window, placement, access and traffic classes public"),
    "medical_appointment": ("get_patient_scheduling_context", "public patient key; live availability is always searched"),
    "mes_order_closeout": (None, "The native budget has separate read units and mutation attempts; public targets already include order and inventory binding handles."),
    "railway_ticketing": ("list_stations", "public origin station name; live service and booking remain in the native quota"),
    "redcap": (None, "Separate read and mutation resources; the contract prices record discovery in read units and admits writes against their own attempt limit."),
    "robot": (None, "Native completion requires listed order by design. Dynamic low-cost priority is not a legal independent control under this contract."),
    "sap_s4hana": ("inspect_purchase_to_pay_route", "shared work units; reusable route selector scoped by purchase-order route, not the per-request receipt"),
    "supply_chain_finance": ("inspect_funding_authority", "shared finance work units; reusable action binding scoped to routing track and service band"),
}

PIN = "1749e7439fdafb75426d7bfecbd4b657509ebe1c"

SKILL_NATIVE = {
    "DocOps": "C_25_05_01", "FactoryOps": "C_50_05_01", "LogisticsOps": "C_09_01_35",
    "ResearchOps": "C_11_01_01", "SocialOps":"C_06_01_01",
}


def skill_audit():
    upstream=ROOT/"artifacts/research_decisions/20261119-c74-skillhorizon-native-v1/upstream"
    assert subprocess.check_output(["git","-C",str(upstream),"rev-parse","HEAD"],text=True).strip()==PIN
    rows=[]
    for path in sorted((upstream/"manifests").glob("*.json")):
        name=path.stem
        spec=read(path)
        family_counts={}
        for task in spec.get("tasks", []):
            family=task.get("family",task.get("environment","default"))
            family_counts[family]=family_counts.get(family,0)+1
        row=dict(manifest=path.name, sha256=sha(path), family_counts=family_counts,
                 task_count=len(spec.get("tasks",[])))
        if name in SKILL_NATIVE:
            resource=upstream/"assets/envs"/SKILL_NATIVE[name]
            assets_available=(resource/"data/database").is_dir() and (resource/"mcp_servers").is_dir()
            if assets_available:
                row.update(status="outside_rescope_sample", reason="Native external assets present; no qualified cross-session public receipt mapping for this frozen Rescope cohort.")
            else:
                row.update(status="no_local_native_runtime", reason="Native integration code exists. Its required external database and MCP support assets are absent from the pinned local checkout; upstream docs/RESOURCES.md says they are not publicly distributed.")
        else:
            row.update(status="no_qualified_cross_session_adapter", reason="Native simulator exists. Its manifest defines long-stage histories; this audit has no already validated new history with a public cross-session receipt key, local drift boundary and both policies under the same prior history. Known FinanceOps/dataflow and FieldOps comparisons stay in v3.")
        rows.append(row)
    return dict(pin=PIN,manifests=rows, local_dataflow_runtime=(upstream/"src/skillhorizon/dataflow_v5/runtime.py").is_file())


def admission(out, sources):
    file=out/"STATIC_ACQUISITION.json"
    downloads={row["name"]:row["sha256"] for row in read(file) if row["verified"]}
    rows=[]
    for workflow,(tool,reason) in sorted(SCREEN.items()):
        source=sources/"rescopebench/cases"/workflow
        status="static_candidate" if tool else "static_excluded"
        if workflow=="emergency_response":
            tree=ast.parse((source/"spec.py").read_text("utf8"))
            tasks=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id=="DATA_TASKS" for t in n.targets))
            requests=re.findall(r"ER-[A-F0-9]+","\n".join(t["query"] for t in tasks))
            assert len(requests)==len(set(requests))==64
        rows.append(dict(workflow=workflow,status=status,description=reason,
                         native_receipt_tool=tool,formal_binding=read(source/"formal-binding.json"),
                         sources={n:v for n,v in downloads.items() if n.startswith(f"cases/{workflow}/")}))
    selected=[]
    for row in rows:
        if row["status"]!="static_candidate":
            continue
        if len(selected)==5:
            row["status"]="beyond_lexicographic_limit"
            continue
        is_staged=(sources/"rescopebench/cases"/row["workflow"]/"data/private/initial.json").exists() or (
            sources/"rescopebench/cases"/row["workflow"]/"raw").is_dir()
        if not is_staged:
            raise RuntimeError("Native source not acquired for " + row["workflow"])
        report=cold(row["workflow"], sources)
        row["cold"]=report
        if report["later_public_scope_match_batches"]:
            row["status"]="admitted"
            selected.append(report)
        else:
            row["status"]="no_cold_receipt_match"
        print(row["workflow"],row["status"],flush=True)
    result=dict(selected=selected,rescope=rows,skillhorizon=skill_audit(),paid_model_calls=0,api_usd=0,
                selection_rule="First five cold-qualified, statically eligible native workflows by name; retain all later batches.")
    write(out/"ADMISSION_AUDIT.json",result)


if __name__=="__main__":
    import argparse
    cli=argparse.ArgumentParser()
    cli.add_argument("--out",type=Path,default=RUN)
    cli.add_argument("--sources",type=Path,default=RUN/"sources")
    args=cli.parse_args()
    sys.path.insert(0,str(args.sources.resolve()))
    admission(args.out,args.sources)

