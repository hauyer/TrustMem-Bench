"""Freeze a whole development suite before running its ordinary baselines."""
import argparse
import json
import shutil
from pathlib import Path
from .data import digest
from .run import run


def suite(cases, output, policies, tool_cache=False):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    cases = [Path(p).resolve() for p in cases]
    frozen = {"cases":{f"c{i:02}:{p.name}":digest(p) for i,p in enumerate(cases)},"policies":policies,
        "code":{p.name:digest(p) for p in Path(__file__).parent.glob("*.py")},"new_model_calls_cap":0,"new_api_usd_cap":0,
        "protocol_sha256":digest(Path(__file__).resolve().parents[1]/"docs/DEVELOPMENT_PROTOCOL.md"),
        "run_order":"case, then the listed policies; not a randomized timing comparison",
        "tool_cache_enabled":tool_cache}
    (output/"code_snapshot").mkdir()
    (output/"case_snapshot").mkdir()
    for i,path in enumerate(cases):
        shutil.copy2(path,output/"case_snapshot"/f"c{i:02}-{path.name}")
    for path in Path(__file__).parent.glob("*.py"):
        shutil.copy2(path,output/"code_snapshot"/path.name)
    shutil.copy2(Path(__file__).resolve().parents[1]/"docs/DEVELOPMENT_PROTOCOL.md",output/"PROTOCOL.md")
    if any(json.loads(p.read_text(encoding="utf-8"))["mechanism"] == "quality" for p in cases):
        quality_protocol = Path(__file__).resolve().parents[1]/"docs/QUALITY_GATE_PROTOCOL.md"
        frozen["quality_protocol_sha256"] = digest(quality_protocol)
        shutil.copy2(quality_protocol,output/"QUALITY_GATE_PROTOCOL.md")
    (output/"freeze.json").write_text(json.dumps(frozen,indent=2)+"\n",encoding="utf-8")
    results = []
    for index, case in enumerate(cases):
        for policy in policies:
            result = run(case,output/f"c{index:02}-{policy}",policy,tool_cache=tool_cache)
            summary = {k:v for k,v in result.items() if k not in ("events","bootstrap_process")}
            summary["result_sha256"] = digest(output/f"c{index:02}-{policy}"/"result.json")
            results.append(summary)
            (output/"progress.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
            print(json.dumps({"case":case.name,"policy":policy,"correct":result.get("correct"),"sessions":result.get("sessions"),"source_bytes":result.get("source_read_bytes_after_history")}),flush=True)
    assert frozen["code"] == {p.name:digest(p) for p in Path(__file__).parent.glob("*.py")}
    assert frozen["cases"] == {f"c{i:02}:{p.name}":digest(p) for i,p in enumerate(cases)}
    (output/"results.json").write_text(json.dumps({"runs":results,"new_model_calls":0,"new_api_usd":0,
        "scope":"Development calibration. Report streams separately; no independent-trajectory or method-advantage claim."},indent=2)+"\n",encoding="utf-8")
    from .reporting import write_report
    write_report(output)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases",nargs="+",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--policies",nargs="+",choices=["always_verify","lazy_group","lazy_full","eager_full"],default=["always_verify","lazy_group","lazy_full","eager_full"])
    p.add_argument("--tool-cache",action="store_true",help="Use the same ordinary backend cache for every compared policy")
    args = p.parse_args()
    suite(args.cases,args.output,args.policies,args.tool_cache)
