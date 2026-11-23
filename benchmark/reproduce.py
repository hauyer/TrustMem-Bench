"""Verify TrustMem-Bench 1.0.0-rc7.3 and reconstruct pinned inputs without redistributing upstream files."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT / "experiments/memory_correctability"
ARTIFACTS = ROOT / "artifacts/research_decisions"
P3 = "20261120-p3-prospective-audit-increment-v1"
FORMS_SOURCE = "20261119-c93-native-oracle-source-v1"
FORMS = "20261119-c93-oracle-archive-path-v1"
C95 = "20261119-c95-foreign-dispatch-followup-v1"
C96 = "20261119-c96-author-budget-boundary-v1"
SKILL = ARTIFACTS / "20261119-c74-skillhorizon-native-v1/upstream"
SKILL_PIN = "1749e7439fdafb75426d7bfecbd4b657509ebe1c"


def read(path):
    return json.loads(path.read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def check(path, expected):
    if not path.is_file() or digest(path.read_bytes()) != expected:
        raise ValueError(f"Hash mismatch or missing file: {path}")


def execute(script, *args):
    subprocess.run([sys.executable, "-B", "-X", "utf8", str(EXPERIMENTS / script), *map(str,args)],
                   cwd=ROOT, check=True)


def require_clean_target(path):
    if path.exists():
        raise FileExistsError(f"Choose a new output directory: {path}")
    path.mkdir(parents=True)


def verify():
    lock = read(ROOT / "RELEASE_LOCK.json")
    for name, expected in lock["files"].items():
        check(ROOT / name, expected)
    with (ROOT/"tables/P3_NATIVE_CONTROLS.csv").open(encoding="utf-8", newline="") as f:
        rows = {row["cohort"]:row for row in csv.DictReader(f)}
    fields = ("eligible","archive_changed","charge_eligible","changes_with_charge",
              "changes_without_charge","order_cross_checked","order_interaction")
    individual = [row for key,row in rows.items() if key not in ("all_five","released_four")]
    for name in fields:
        assert sum(int(r[name]) for r in individual) == int(rows["all_five"][name]), name
        assert sum(int(r[name]) for r in individual if r["cohort"]!="api_reliability") == \
            int(rows["released_four"][name]), name
    with (ROOT/"tables/P4_NATIVE_MODELS.csv").open(encoding="utf-8", newline="") as f:
        p4 = [r for r in csv.DictReader(f) if r["cohort"]=="released" and r["slot"] in {"A","B","C"}]
    assert len(p4)==3 and all(int(r["paired_openings"])==12 for r in p4)
    for row in p4:
        assert int(row["strict_outside_changes"]) <= min(
            int(row["raw_outside_changes"]), int(row["agreeing_terminal_controls"]))
        assert int(row["fee_outside_additions"]) <= int(row["verified_fee_pairs"])
    with (ROOT/"tables/RECEIPT_FEE_PAIRED.csv").open(encoding="utf-8", newline="") as handle:
        paired = {row["slot"]: row for row in csv.DictReader(handle)}
    assert set(paired) == {"P3","A","B","C"}
    assert int(paired["P3"]["keep_equals_fee"]) == int(rows["all_five"]["fee_matches_archive"])
    with (ROOT/"tables/ARCHIVE_THREE_ARMS.csv").open(encoding="utf-8", newline="") as handle:
        archive = {(r["slot"], r["workflow"]): r for r in csv.DictReader(handle)}
    figures = read(ROOT/"tables/FIGURE_DATA.json")["p4"]
    for item in figures:
        slot = item["slot"]
        assert int(paired[slot]["fee_verified"]) == item["fee_eligible"]
        for arm in ("keep","remove","archive"):
            assert int(archive[slot,"forms"][arm]) == item["forms"][arm]
    sys.path.insert(0, str(ROOT/"scripts"))
    from receipt_fee_extension import summarize
    with (ROOT/"tables/NATIVE_OPENINGS.csv").open(encoding="utf-8", newline="") as f:
        native = list(csv.DictReader(f))
    with (ROOT/"tables/NATIVE_CONTROL_STRATA.csv").open(encoding="utf-8", newline="") as f:
        strata = list(csv.DictReader(f))
    assert len(native) == len({(r["phase"], r["slot"], r["workflow"], r["opening"]) for r in native}) == 90
    actual = [{k:str(v) for k,v in row.items()} for row in summarize(native)]
    assert actual == strata, "Control strata differ from opening-level measurements"
    fig_all = read(ROOT/"tables/FIGURE_DATA.json")
    if "forms_t14" in fig_all:
        t14_by_slot = {r["slot"]: r for r in native if r["phase"]=="P4" and r["workflow"]=="forms" and r["opening"]=="14"}
        slot_by_name = {"Llama-3.3-70B": "B", "Mistral-Small-24B": "C"}
        for item in fig_all["forms_t14"]["model_outcomes"]:
            row = t14_by_slot[slot_by_name[item["model"]]]
            assert (int(row["keep_count"]), int(row["remove_count"]), int(row["fee_count"])) == (
                item["keep"], item["remove"], item["fee_only"]
            )
    if "railway" in fig_all:
        slot_by_name = {"Qwen3-32B": "A", "Llama-3.3-70B": "B", "Mistral-Small-24B": "C"}
        for item in fig_all["railway"]:
            s = slot_by_name[item["name"]]
            rrows = [r for r in native if r["phase"]=="P4b" and r["workflow"]=="railway_ticketing" and r["slot"]==s]
            assert len(rrows) == 8
            for arm in ("keep", "remove", "archive"):
                assert sum(int(r[f"{arm}_count"]) for r in rrows) == item[arm]
    assert (ROOT/"tables/TABLE_NUMBER_MAP.csv").is_file()
    skill=read(ROOT/"tables/SKILLHORIZON_AGGREGATES.json")
    assert skill["histories"]==3 and skill["complete_packages_and_publication_cells"]==skill["arm_threshold_cells"]==150
    print(f"TrustMem-Bench 1.0.0-rc7.3 verified: {len(lock['files'])} files. P3, P4, P4b, Figure, and SkillHorizon checks passed.")


def checkout_skill(local):
    if not SKILL.exists():
        SKILL.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git","init","-q",str(SKILL)],check=True)
        git = ["git","-C",str(SKILL),"-c","core.autocrlf=false","-c","core.longpaths=true"]
        repo = str(local.resolve()) if local else "https://github.com/HKUST-KnowComp/SkillHorizon.git"
        subprocess.run([*git,"fetch","--quiet","--depth","1",repo,SKILL_PIN],check=True)
        subprocess.run([*git,"checkout","--quiet","--detach",SKILL_PIN],check=True)
    head=subprocess.check_output(["git","-C",str(SKILL),"rev-parse","HEAD"],text=True).strip()
    if head!=SKILL_PIN:
        raise ValueError("SkillHorizon checkout is at a different commit")
    return SKILL


def skillhorizon(out, local):
    require_clean_target(out)
    checkout_skill(local)
    c95, c96 = ARTIFACTS/C95, out/"cutoffs"
    if c95.exists():
        raise FileExistsError("Use a fresh TrustMem-Bench checkout for native SkillHorizon reproduction")
    from_names = ("freeze","reference","observe","compare")
    for phase in from_names:
        execute("c95_integration_dispatch_followup.py",phase,"--out",c95)
    for phase in ("freeze","run"):
        execute("c96_integration_author_budget_boundary.py",phase,"--out",c96)
    record=read(c96/"RESULT.json")
    cutoffs=[cutoff for run in record["runs"] for cutoff in run["cutoffs"]]
    expected=read(ROOT/"locks/NATIVE_EXPECTED.json")["skillhorizon_c96"]
    check(c96/"RESULT.json",expected)
    print(f"SkillHorizon C96 reproduced {len(cutoffs)} cutoff records and matched the locked result digest.")


def acquire(items, target, local=None, retries=5):
    total = len(items)
    completed = 0

    def fetch_one(item):
        name, spec = item
        path = target / name
        expected = spec["sha256"]
        if path.is_file() and digest(path.read_bytes()) == expected:
            return
        raw = None
        if local is not None:
            candidate = local / name
            if candidate.is_file():
                cand_bytes = candidate.read_bytes()
                if digest(cand_bytes) == expected:
                    raw = cand_bytes
                else:
                    raise ValueError(f"Local source hash mismatch: {candidate}")
        if raw is None:
            last_err = None
            for attempt in range(1, retries + 1):
                try:
                    request = Request(spec["url"], headers={"User-Agent": "TrustMem-Bench-Reproduction/1.0-rc7.3"})
                    with urlopen(request, timeout=45) as response:
                        cand_bytes = response.read(25 * 1024 * 1024 + 1)
                    if len(cand_bytes) > 25 * 1024 * 1024 or digest(cand_bytes) != expected:
                        raise ValueError(f"Unexpected content from pinned upstream: {name}")
                    raw = cand_bytes
                    break
                except Exception as exc:
                    last_err = exc
                    if isinstance(exc, ValueError) or attempt == retries:
                        raise
                    time.sleep(min(16, 2 ** (attempt - 1)))
            if raw is None and last_err is not None:
                raise last_err
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in pool.map(fetch_one, items.items()):
            completed += 1
            if total >= 50 and (completed % 50 == 0 or completed == total):
                print(f"Acquired {completed}/{total} pinned upstream files...", flush=True)


def stage_forms(local):
    sources=ARTIFACTS/FORMS_SOURCE
    acquire(read(ROOT/"locks/RESCOPE_INPUTS.json")["forms"],sources/"source",local)
    seal=sources/"SOURCE_FREEZE.json"
    if not seal.is_file():
        shutil.copyfile(ROOT/"locks/FORMS_SOURCE_FREEZE.json",seal)
    results=ARTIFACTS/FORMS
    if not results.is_dir():
        for phase in ("freeze","observe","compare"):
            execute("c93_oracle_archive_path.py",phase,"--out",results)
    return sources/"source",results


@contextmanager
def p3_manifest_encoding(upstream):
    # The original Windows freeze hashed the working-tree line endings.
    expected=read(ROOT/"locks/SKILLHORIZON_P3_MANIFESTS.json")
    original={}
    try:
        for name, checksum in expected.items():
            path=upstream/"manifests"/name
            raw=path.read_bytes()
            lf=raw.replace(b"\r\n",b"\n")
            for candidate in (raw,lf,lf.replace(b"\n",b"\r\n")):
                if digest(candidate)==checksum:
                    if candidate!=raw:
                        original[path]=raw
                        path.write_bytes(candidate)
                    break
            else:
                raise ValueError(f"P3 upstream manifest bytes differ beyond line endings: {name}")
        yield
    finally:
        for path, raw in original.items():
            path.write_bytes(raw)


def p3_native(out, local, skill):
    require_clean_target(out)
    upstream=checkout_skill(skill)
    print('Rebuilding P3 native adjudication (typical CPU runtime: 30-50 minutes)...', flush=True)
    sources=out/"sources"
    acquire(read(ROOT/"locks/RESCOPE_INPUTS.json")["p3"],sources,local)
    shutil.copyfile(ROOT/"locks/P3_STATIC_ACQUISITION.json",out/"STATIC_ACQUISITION.json")
    expected=read(ROOT/"locks/NATIVE_EXPECTED.json")["p3_files"]
    with p3_manifest_encoding(upstream):
        execute("p3_prospective_admit.py","--out",out,"--sources",sources)
    check(out/"ADMISSION_AUDIT.json",expected["ADMISSION_AUDIT.json"])
    for phase in ("freeze","observe","blind"):
        execute("p3_prospective_audit_increment.py",phase,"--out",out,"--sources",sources)
    execute("p3_prospective_verify.py",out)
    execute("p3_prospective_audit_increment.py","compare","--out",out,"--sources",sources)
    execute("p3_prospective_score.py",out)
    for name, checksum in expected.items():
        check(out/name,checksum)
    with ZipFile(out/"organizer-p3.zip","x") as organizer:
        for name in ("OBSERVE_LOSS.json","RESULT.json","ADMISSION_AUDIT.json"):
            organizer.write(out/name, f"artifacts/research_decisions/{P3}/{name}")
    print(f"P3 content verified: {len(expected)} locked files. Organizer archive is in {out}.")


def p4_openings(source,out):
    sys.path[:0] = [str(EXPERIMENTS), str(source.resolve())]
    from p3_prospective_audit_increment import cold, make_openings
    out.mkdir(exist_ok=True)
    for workflow in ("medical_appointment","api_reliability"):
        make_openings(out, source, cold(workflow,source))


def copy_runtime(runtime, files, getter):
    require_clean_target(runtime)
    for name,expected in files.items():
        dest=runtime/name
        raw=getter(name)
        if digest(raw)!=expected:
            raise ValueError(f"Frozen P4 runtime hash mismatch: {name}")
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
    shutil.copyfile(ROOT/"locks/P4_BUNDLE_MANIFEST.json",runtime/"BUNDLE_MANIFEST.json")
    shutil.copyfile(ROOT/"modules/p4/p4_review_scores.py",runtime/"p4_review_scores.py")
    subprocess.run([sys.executable,"-B",str(runtime/"run_p4_modelscope_audit.py"),"verify-bundle"],
                   cwd=runtime,check=True)


def stage_p4(args):
    files=read(ROOT/"locks/P4_BUNDLE_MANIFEST.json")["files"]
    code=ROOT/"modules/p4"
    expected=read(ROOT/"locks/NATIVE_EXPECTED.json")
    if args.local_bundle:
        check(args.local_bundle,expected["p4_bundle"])
        with ZipFile(args.local_bundle) as z:
            def original(name):
                return z.read(name) if name.startswith(("sources/","snapshots/")) else (code/name).read_bytes()
            copy_runtime(args.out,files,original)
        return
    forms_source, forms = stage_forms(args.forms_sources)
    p3_source=ARTIFACTS/"rc7-p4-p3-sources"
    acquire(read(ROOT/"locks/RESCOPE_INPUTS.json")["p4_p3"],p3_source,args.p3_sources)
    openings=ARTIFACTS/"rc7-p4-derived-openings"
    snapshots = [name.removeprefix("snapshots/p3/") for name in files if name.startswith("snapshots/p3/")]
    if any(not (openings/"CHECKPOINTS"/name).is_file() for name in snapshots):
        p4_openings(p3_source,openings)
    prefixes={
        "sources/forms/":forms_source,
        "sources/p3/":p3_source,
        "snapshots/forms/":forms,
        "snapshots/p3/":openings/"CHECKPOINTS",
    }
    def rebuilt(name):
        for prefix,directory in prefixes.items():
            if name.startswith(prefix):
                return (directory/name.removeprefix(prefix)).read_bytes()
        return (code/name).read_bytes()
    copy_runtime(args.out,files,rebuilt)


def stage_p4b(out, p3_run):
    """Assemble the extension from an organizer's P3 source tree and checkpoints."""
    require_clean_target(out)
    manifest = ROOT/"locks/P4B_BUNDLE_MANIFEST.json"
    for name, expected in read(manifest)["files"].items():
        if name.startswith("sources/p3/"):
            src = p3_run/"sources"/name.removeprefix("sources/p3/")
        elif name.startswith("snapshots/p3/"):
            src = p3_run/"CHECKPOINTS"/name.removeprefix("snapshots/p3/")
        else:
            src = ROOT/"modules/p4b"/name
        check(src, expected)
        dest = out/name
        dest.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(src, dest)
    shutil.copyfile(manifest, out/"BUNDLE_MANIFEST.json")
    subprocess.run([sys.executable, "-B", str(out/"run_p4b_p3_extension.py"), "verify-bundle"],
                   cwd=out, check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest="command",required=True)
    actions.add_parser("verify")
    sh=actions.add_parser("skillhorizon")
    sh.add_argument("--out",type=Path,required=True)
    sh.add_argument("--skill-checkout",type=Path)
    p3=actions.add_parser("p3")
    p3.add_argument("--out",type=Path,required=True)
    p3.add_argument("--p3-sources",type=Path)
    p3.add_argument("--skill-checkout",type=Path)
    p4=actions.add_parser("stage-p4")
    p4.add_argument("--out",type=Path,required=True)
    p4.add_argument("--local-bundle",type=Path)
    p4.add_argument("--forms-sources",type=Path)
    p4.add_argument("--p3-sources",type=Path)
    extension=actions.add_parser("stage-p4b")
    extension.add_argument("--p3-run",type=Path,required=True)
    extension.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="verify":
        verify()
    elif args.command=="skillhorizon":
        skillhorizon(args.out.resolve(),args.skill_checkout)
    elif args.command=="p3":
        p3_native(args.out.resolve(),args.p3_sources,args.skill_checkout)
    elif args.command=="stage-p4b":
        stage_p4b(args.out.resolve(), args.p3_run.resolve())
    else:
        args.out=args.out.resolve()
        stage_p4(args)


if __name__=="__main__":
    main()
