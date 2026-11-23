"""Test receipt-aware dispatch within the unchanged native integration quota."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

import c91_integration_diagnosis as integration

c74, c77 = integration.c74, integration.c77
PROTOCOL = Path(__file__).with_name("C94_INTEGRATION_DISPATCH_PROTOCOL.md")
MODES = ("original", "least_calls")


def freeze():
    cases = [case for case in c74.read(c77.MANIFEST)["tasks"]
             if (case["family"], case["variant"], case["band"]) ==
             ("heterogeneous_integration", "conflict_and_late_correction", "64k")]
    if len(cases) != 3:
        raise ValueError("The frozen manifest must contain exactly three eligible input candidates")
    return {"pin": c74.PIN, "cases": [{"input": case, "default_call_cap": c74.budget(case)}
                                      for case in cases],
            "arms": list(integration.ARMS), "controllers": list(MODES),
            "sha256": {p.name: c74.sha(p) for p in (Path(__file__), PROTOCOL, c77.MANIFEST,
                                                 Path(c74.__file__), Path(c77.__file__),
                                                 Path(integration.__file__))},
            "model_calls_cap": 0, "api_usd_cap": 0}


def dispatch_witness(author, mode, archived_key, decisions):
    class DispatchWitness(author):
        def expected_calls(self, key):
            source = self.sources.get(key, {})
            identity = source.get("identity_source_id")
            missing_source = not source
            missing_map = ("identity_maps" not in self.sources.get(identity, {})
                           and identity != archived_key)
            skill_documents = sum(name not in self.docs for name in
                                  ("normalize-source", "aggregate-source"))
            return 2 + missing_source + missing_map + skill_documents

        def run(self):
            project = self.call("read_project")
            changed = False
            for stage in range(1, project["stages"] + 1):
                pending = [row["id"] for row in self.inventory(stage) if row["stage"] == stage]
                while pending:
                    if changed:
                        quotes = {key: self.expected_calls(key) for key in pending}
                        key = min(pending, key=quotes.get) if mode == "least_calls" else pending[0]
                        decisions.append({"stage": stage, "after_calls": self.calls, "target": key,
                                          "visible_expected_calls": quotes})
                    else:
                        key = pending[0]
                    pending.remove(key)
                    self.solve(key)
                closed = self.close(stage)
                if not closed["notices"]:
                    continue
                changed = True
                affected = set()
                for notice in closed["notices"]:
                    source = self.source(notice["source_id"], True)
                    if notice["type"] == "identity_correction":
                        affected.update(key for key, cached in self.sources.items()
                                        if cached.get("identity_source_id") == source["id"]
                                        and self.identity_signatures.get(key) != self.identity_choice(
                                            cached, self.identity_accounts.get(key))[2])
                    else:
                        assert notice["type"] == "feed_correction", notice
                        affected.add(source["id"])
                earliest = min([stage, *(self.sources[key]["stage"] for key in affected)])
                for key in sorted(affected):
                    self.solve(key)
                    self.repairs += 1
                for earlier in range(earliest, stage + 1):
                    assert not self.close(earlier)["notices"]
            review = self.skill("review-release", close_ids=[self.closes[i]
                                                            for i in range(1, project["stages"] + 1)])
            self.skill("publish-release", review_id=review["id"])
            self.call("read_project")

    return DispatchWitness


def play(root, native, case_row, mode, arm):
    selection = c74.read(root / "ADMISSION.json")
    reference = root / "reference"
    prefix = c74.read_log(reference / "actions.jsonl")[:selection["pivot"]]
    decisions = []
    archived = selection["target"] if arm == "archive" else None
    adapted = (native[0], native[1], dispatch_witness(native[2], mode, archived, decisions), native[3])
    folder = root / mode / arm
    result = integration.execute(folder, adapted, c74.read(root / "INITIAL.json"),
                                 case_row["default_call_cap"], prefix=prefix,
                                 checkpoint=c74.read(reference / "CHECKPOINT.json"),
                                 selection=selection, arm=arm)
    ledger = c74.read(folder / "LEDGER.json")
    for decision in decisions:
        decision["remaining"] = ledger[decision["after_calls"] - 1]["remaining"]
    c74.write(folder / "DISPATCH.json", decisions)
    return result


def observe(output, rows, native):
    diagnoses = {}
    for row in rows:
        case = row["input"]["id"]
        root = output / case
        selection = c74.read(root / "ADMISSION.json")
        if "reason" in selection:
            print(case, selection["reason"], flush=True)
            continue
        for mode in MODES:
            lost = play(root, native, row, mode, "remove")
            folder = root / mode / "remove"
            diagnoses[f"{case}/{mode}"] = {
                "sha256": {name: c74.sha(folder / name) for name in
                           ("RESULT.json", "DISPATCH.json", "actions.jsonl")},
                "diagnosis": integration.diagnosis(lost, selection),
                "completed_packages": len(lost["completed_ids"]),
                "published": lost["published"], "final_confirmation": lost["final_confirmation"],
                "stopped_before": lost["stopped_before"],
            }
            print(case, mode, "loss", lost["charged"], lost["stopped_before"], flush=True)
    c74.write(output / "LOSS_BEFORE_CONTROLS.json", diagnoses)


def compare(output, rows, native):
    frozen = c74.read(output / "LOSS_BEFORE_CONTROLS.json")
    report, excluded = [], []
    for row in rows:
        case = row["input"]["id"]
        root = output / case
        selection = c74.read(root / "ADMISSION.json")
        if "reason" in selection:
            excluded.append(dict(case=case, reason=selection["reason"]))
            continue
        for mode in MODES:
            folder = root / mode
            known = frozen[f"{case}/{mode}"]
            assert all(c74.sha(folder / "remove" / name) == digest
                       for name, digest in known["sha256"].items())
            loss = c74.read(folder / "remove/RESULT.json")
            controls = {arm: play(root, native, row, mode, arm) for arm in ("keep", "sham", "archive")}
            for name in ("keep", "sham"):
                assert c74.read_log(folder / name / "actions.jsonl") == c74.read_log(
                    folder / "archive/actions.jsonl")
                assert controls[name]["completed_ids"] == controls["archive"]["completed_ids"]
            read = loss["extra_read"]
            fee = None
            if read and read["old_mapping_equal"]:
                fee = play(root, native, row, mode, "refund")
                index = read["index"] - selection["pivot"]
                assert fee["extra_read"]["index"] == read["index"] and fee["extra_read"]["charge"] == 0
                assert c74.read_log(folder / "remove/actions.jsonl")[:index] == c74.read_log(
                    folder / "refund/actions.jsonl")[:index]
            before, after = (c74.read(folder / arm / "DISPATCH.json") for arm in ("remove", "archive"))
            first_change = next((dict(loss=x, archive=y) for x, y in zip(before, after)
                                 if x["target"] != y["target"]), None)
            first_before_charge = bool(first_change and
                                       (read is None or first_change["loss"]["after_calls"] < read["index"]))
            base, archived = set(loss["completed_ids"]), set(controls["archive"]["completed_ids"])
            report.append({"case": case, "mode": mode, "budget": row["default_call_cap"],
                           "receipt": selection["target"], "scope_consumer": selection["consumer"],
                           "first_order_change": first_change,
                           "first_order_change_before_reacquisition": first_before_charge,
                           "loss_reacquisition": read,
                           "gained": sorted(archived - base), "displaced": sorted(base - archived),
                           "loss_completed": len(base), "archive_completed": len(archived),
                           "total_targets": loss["native_score"]["total_work_packages"],
                           "loss_published": loss["published"],
                           "archive_published": controls["archive"]["published"],
                           "loss_confirmed": loss["final_confirmation"],
                           "archive_confirmed": controls["archive"]["final_confirmation"],
                           "loss_charged": loss["charged"], "archive_charged": controls["archive"]["charged"],
                           "fee_completed": len(fee["completed_ids"]) if fee else None,
                           "fee_confirmed": fee["final_confirmation"] if fee else None})
    c74.write(output / "RESULT.json", {"rows": report, "excluded": excluded, "api_usd": 0})
    print(json.dumps(Counter(row["mode"] for row in report if row["first_order_change"])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "reference", "observe", "compare"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(["git", "-C", c74.SOURCE, "rev-parse", "HEAD"],
                               text=True).strip() != c74.PIN:
        raise ValueError("Unexpected SkillHorizon revision")
    if subprocess.check_output(["git", "-C", c74.SOURCE, "status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("SkillHorizon tracked files are modified")
    spec = freeze()
    seal = args.out / "FREEZE.json"
    if args.stage == "freeze":
        args.out.mkdir()
        c74.write(seal, spec)
        return
    assert c74.read(seal) == spec
    native = c77.native()
    if args.stage == "reference":
        integration.run_reference(args.out, {"cases": [row["input"] for row in spec["cases"]]}, native)
    elif args.stage == "observe":
        observe(args.out, spec["cases"], native)
    else:
        compare(args.out, spec["cases"], native)


if __name__ == "__main__":
    main()

