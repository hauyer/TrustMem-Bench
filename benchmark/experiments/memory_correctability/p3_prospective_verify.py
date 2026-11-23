"""Validate the holdout boundary and compare independently generated evidence."""
import argparse
from pathlib import Path

from p3_prospective_audit_increment import read, sha, write


def lock(root, verify_only=False):
    observed = root/"OBSERVE_LOSS.json"
    diagnoses = root/"DIAGNOSIS_BEFORE_TRUTH.json"
    cohort = root/"COHORT_FREEZE.json"
    path = root/"PRE_TRUTH_LOCK.json"
    result = {x.name:sha(x) for x in (observed,diagnoses,cohort)}
    if verify_only:
        assert read(path)==result, "Inputs or blind predictions changed after locking"
        return
    assert not (root/"REPLAY").exists() and not (root/"RESULT.json").exists()
    keys = lambda row:(row["workflow"],row["day"],row["mode"])
    eligible={keys(row):row for row in read(observed) if row["status"]=="eligible"}
    pred=read(diagnoses)
    assert len(pred)==len(eligible) and {keys(row) for row in pred}==eligible.keys()
    for row in pred:
        questions=set(row["answers"])
        assert questions==({"total","fee"} if eligible[keys(row)]["same_value_read"] is not None else {"total"})
        assert all(set(v)=={"D0","D1","D2a","D2b"} for v in row["answers"].values())
    for row in eligible.values():
        cp=root/"CHECKPOINTS"/f"{row['workflow']}-T{row['day']:02}.json"
        assert sha(cp)==row["checkpoint_sha256"]
    write(path,result)


def reproduce(original, second):
    stable=("COHORT_FREEZE.json","ADMISSION_AUDIT.json","OBSERVE_LOSS.json","DIAGNOSIS_BEFORE_TRUTH.json",
            "PRE_TRUTH_LOCK.json","RESULT.json")
    lock(original, verify_only=True)
    lock(second, verify_only=True)
    def paths(root):
        return {p.relative_to(root).as_posix() for folder in ("CHECKPOINTS","REPLAY")
                for p in (root/folder).glob("*.json")} | set(stable)
    assert paths(original)==paths(second)
    checks=[name for name in sorted(paths(original)) if sha(original/name)!=sha(second/name)]
    def untimed(value):
        if isinstance(value,dict):
            return {k:untimed(v) for k,v in value.items() if "wall_ms" not in k and "ms_per" not in k}
        if isinstance(value,list):
            return [untimed(v) for v in value]
        return value
    matched_summary = untimed(read(original/"INCREMENT_SUMMARY.json")) == untimed(
        read(second/"INCREMENT_SUMMARY.json"))
    result=dict(files_compared=len(paths(original)),byte_identical=len(paths(original))-len(checks),
                deterministic_summary_match=matched_summary,
                mismatches=checks,timing_policy="Run-specific wall times remain in REPLAY_TIMINGS.json; byte check excludes them.",
                paid_model_calls=0,api_usd=0,passed=not checks and matched_summary)
    write(original/"REPRODUCTION.json",result)
    assert result["passed"], result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("root",type=Path)
    p.add_argument("--reproduction",type=Path)
    a=p.parse_args()
    if a.reproduction:
        reproduce(a.root,a.reproduction)
    else:
        lock(a.root)

