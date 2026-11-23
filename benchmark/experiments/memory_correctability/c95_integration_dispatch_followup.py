"""Apply the frozen C94 procedure to all three 512k histories."""

import argparse
from pathlib import Path
import subprocess

import c94_integration_dispatch as study

c74, c77 = study.c74, study.c77
PROTOCOL = Path(__file__).with_name("C95_INTEGRATION_DISPATCH_FOLLOWUP_PROTOCOL.md")


def freeze():
    spec = study.freeze()
    rows = [row for row in c74.read(c77.MANIFEST)["tasks"]
            if (row["family"], row["variant"], row["band"]) ==
            ("heterogeneous_integration", "conflict_and_late_correction", "512k")]
    assert len(rows) == 3 and all(row["parameters"]["stages"] == 16 for row in rows)
    spec["cases"] = [{"input": row, "default_call_cap": c74.budget(row)} for row in rows]
    spec["sha256"].update({file.name: c74.sha(file) for file in (Path(__file__), PROTOCOL)})
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "reference", "observe", "compare"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    spec = freeze()
    assert subprocess.check_output(["git", "-C", c74.SOURCE, "rev-parse", "HEAD"],
                                   text=True).strip() == c74.PIN
    assert not subprocess.check_output(["git", "-C", c74.SOURCE, "status", "--porcelain", "--untracked-files=no"])
    seal = args.out / "FREEZE.json"
    if args.stage == "freeze":
        args.out.mkdir()
        c74.write(seal, spec)
        return
    assert c74.read(seal) == spec
    native = c77.native()
    if args.stage == "reference":
        study.integration.run_reference(args.out, {"cases": [row["input"] for row in spec["cases"]]}, native)
    elif args.stage == "observe":
        study.observe(args.out, spec["cases"], native)
    else:
        study.compare(args.out, spec["cases"], native)


if __name__ == "__main__":
    main()

