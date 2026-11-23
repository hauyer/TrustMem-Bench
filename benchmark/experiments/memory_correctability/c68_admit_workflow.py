"""Stage immutable inputs for the workflow qualification and subsequent replay."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "artifacts/research_decisions"
C59 = RUNS / "20261118-c59-rescope-admission-v1"
GIT = RUNS / "20261118-c60-rescope-public-cold-start-v1/upstream-git"
OUT = RUNS / "20261119-c68-unseen-workflow-admission-v1"
SOURCE = OUT / "source/rescopebench"
WORKFLOWS = ("cinema", "carbon_credits", "event_ticketing")
CODE_REVISION = "4780ba60e61b8dd41e86a370560ca72de3e9ed61"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def fetch(item, pin, route):
    name, expected = item
    path = SOURCE / name
    path.parent.mkdir(exist_ok=True, parents=True)
    if path.exists():
        process = None
    else:
        url = f"https://huggingface.co/datasets/{pin['repo_id']}/{route}/{pin['revision']}/{name}"
        process = subprocess.run([
            "curl.exe", "--fail", "--location", "--silent", "--show-error", "--max-time", "30",
            "--connect-timeout", "7", "--retry", "3", "--retry-delay", "1",
            "--max-filesize", str(expected["bytes"]), "--output", str(path), url,
        ], capture_output=True, text=True)
    body = path.read_bytes() if path.exists() else b""
    exit_code = 0 if process is None else process.returncode
    return {
        "name": name, "bytes": len(body), "sha256": sha(body), "exit": exit_code,
        "mode": "existing" if process is None else route,
        "stderr": "" if process is None else process.stderr.strip(),
        "verified": exit_code == 0 and len(body) == expected["bytes"] and sha(body) == expected["sha256"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("metadata", *WORKFLOWS))
    parser.add_argument("--retry-label", help="Retry missing inputs under a separate download log")
    parser.add_argument("--route", choices=("resolve", "raw"), default="resolve")
    args = parser.parse_args()
    pin = json.loads((C59 / "CASES_PIN.json").read_bytes())
    manifest = (C59 / "PINNED_MANIFEST.json").read_bytes()
    assert sha(manifest) == pin["manifest_sha256"]
    files = json.loads(manifest)["files"]
    if args.retry_label:
        prior = json.loads((OUT / f"FREEZE_{args.stage}.json").read_bytes())
        assert prior["data_pin"] == pin, prior["data_pin"]
        chosen, shared, cap = prior["files"], prior["shared_sha256"], prior["maximum_source_bytes"]
        assert all(files[name] == row for name, row in chosen.items())
    elif args.stage == "metadata":
        chosen = {name: row for name, row in files.items()
                  if name.split("/")[1] in WORKFLOWS
                  and (name.endswith(("/case-manifest.json", "/spec.py")) or "/data/public/tasks/" in name)}
        cap = 4 * 1024 * 1024
        shared = {}
    else:
        chosen = {name: row for name, row in files.items() if name == "cases/__init__.py"
                  or name.startswith(f"cases/{args.stage}/") and not name.endswith("/data/reference.json")}
        cap = 20 * 1024 * 1024
        recorded = json.loads((SOURCE / f"cases/{args.stage}/case-manifest.json").read_bytes())["shared_sources"]
        git_head = subprocess.check_output(["git", "-C", str(GIT), "rev-parse", "HEAD"], text=True).strip()
        assert git_head == CODE_REVISION
        shared = {}
        for name in ("__init__.py", *recorded):
            body = subprocess.check_output(["git", "-C", str(GIT), "show", f"{CODE_REVISION}:rescopebench/{name}"])
            assert name == "__init__.py" or sha(body) == recorded[name], name
            path = SOURCE / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(body)
            shared[name] = sha(body)
    assert chosen and sum(row["bytes"] for row in chosen.values()) <= cap
    OUT.mkdir(exist_ok=True, parents=True)
    freeze = {
        "data_pin": pin, "code_revision": CODE_REVISION, "files": chosen, "shared_sha256": shared,
        "protocol_sha256": sha(Path(__file__).with_name("C68_UNSEEN_WORKFLOW_ADMISSION.md").read_bytes()),
        "runner_sha256": sha(Path(__file__).read_bytes()),
        "maximum_source_bytes": cap, "maximum_model_calls": 0, "maximum_usd": 0,
    }
    stage_id = args.stage if not args.retry_label else f"{args.stage}_{args.retry_label}"
    write_new(OUT / f"FREEZE_{stage_id}.json", freeze)
    priority = {"driver.py", "runtime.py", "contract.json", "formal-binding.json"}
    ordered = sorted(chosen.items(), key=lambda item: (Path(item[0]).name not in priority, item[0]))
    with ThreadPoolExecutor(max_workers=3) as executor:
        records = list(executor.map(lambda item: fetch(item, pin, args.route), ordered))
    write_new(OUT / f"ACQUISITION_{stage_id}.json", records)
    errors = [row for row in records if not row["verified"]]
    if errors:
        raise SystemExit(f"Checks failed for {errors}")
    print(f"{args.stage}: {len(records)} pinned files verified")


if __name__ == "__main__":
    main()
