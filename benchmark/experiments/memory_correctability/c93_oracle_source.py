"""Acquire the pinned Oracle Clinical One case without its reference answers."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

import c68_admit_workflow as upstream


OUT = upstream.RUNS / "20261119-c93-native-oracle-source-v1"
SOURCE = OUT / "source/rescopebench"
CASE = "cases/oracle_clinical_one_data_collection"


def main():
    upstream.SOURCE = SOURCE
    OUT.mkdir()
    data = (upstream.C59 / "PINNED_MANIFEST.json").read_bytes()
    pin = json.loads((upstream.C59 / "CASES_PIN.json").read_bytes())
    assert upstream.sha(data) == pin["manifest_sha256"]
    files = {path: entry for path, entry in json.loads(data)["files"].items()
             if path == "cases/__init__.py" or path.startswith(CASE + "/")
             and not path.endswith("/data/reference.json")}
    assert len(files) > 0 and sum(entry["bytes"] for entry in files.values()) < 20 * 1024 * 1024
    upstream.write_new(OUT / "DATA_FREEZE.json", dict(pin=pin, files=files, model_calls_cap=0, usd_cap=0))
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda item: upstream.fetch(item, pin, "resolve"), files.items()))
    upstream.write_new(OUT / "ACQUISITION.json", rows)
    assert all(row["verified"] for row in rows), [row["name"] for row in rows if not row["verified"]]
    manifest = json.loads((SOURCE / CASE / "case-manifest.json").read_bytes())
    shared = {}
    for name in ("__init__.py", *manifest["shared_sources"]):
        body = subprocess.check_output(["git", "-C", str(upstream.GIT), "show",
                                        f"{upstream.CODE_REVISION}:rescopebench/{name}"])
        if name != "__init__.py":
            assert upstream.sha(body) == manifest["shared_sources"][name]
        path = SOURCE / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(body)
        shared[name] = upstream.sha(body)
    upstream.write_new(OUT / "SOURCE_FREEZE.json", dict(files=files, shared=shared,
                                                       code=upstream.CODE_REVISION, pin=pin))
    print(f"{len(files)} case files and {len(shared)} shared files verified")


if __name__ == "__main__":
    main()
