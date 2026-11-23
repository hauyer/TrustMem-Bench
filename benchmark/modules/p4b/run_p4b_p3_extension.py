"""Portable CLI runner, ModelScope bundle packager, and offline replay verifier for P4b.

Extends P4 multi-family native tool-calling counterfactual audits to P3's two largest
upstream-released prospective workflows without modifying frozen P4 code:
  - backup_recovery (all 10 P3 openings: T05, T06, T08-T15)
  - railway_ticketing (first 8 contiguous P3 openings: T09-T16)

Subcommands:
  freeze        Write/refresh P4B_P3_EXTENSION_FREEZE.json with SHA-256 hashes.
  pack          Build a self-contained portable ZIP ready to upload to ModelScope Notebook.
  verify-bundle Verify all SHA-256 hashes inside an unpacked bundle and smoke-load both drivers.
  qualify       Run Gate 2 qualification on backup_recovery-T05 and emit QUALIFIED/DISQUALIFIED.
  run           Run the frozen P4b native counterfactual audit with per-branch resume & tape recording.
  replay        Zero-GPU offline verification replaying every model_calls.jsonl via RecordedReplayAdapter.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _resolve_layout() -> tuple[Path, Path, Path, Path]:
    if (SCRIPT_DIR / "BUNDLE_MANIFEST.json").is_file():
        bundle = SCRIPT_DIR
        return bundle, bundle, bundle / "sources/p3", bundle / "snapshots/p3"

    workspace = SCRIPT_DIR.parents[1]
    pkg_root = workspace / "github-release/TrustMem-Bench"
    p3_src = workspace / "artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1/sources"
    p3_snap = workspace / "artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1/CHECKPOINTS"
    return workspace, pkg_root, p3_src, p3_snap


ROOT_DIR, PKG_ROOT, P3_SRC, P3_SNAP = _resolve_layout()
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from trustmem_bench.eval_ext.budget import AttemptBudget  # noqa: E402
from trustmem_bench.eval_ext.native_audit_p4b import (  # noqa: E402
    AuditCase,
    load_p4b_driver,
    run_p4b_native_episode,
    summarize_case_audit,
)
from trustmem_bench.eval_ext.openai_compatible import (  # noqa: E402
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
    RecordingAdapter,
)
from trustmem_bench.eval_ext.recorded import RecordedReplayAdapter  # noqa: E402


FROZEN_P4B_COHORT: tuple[dict[str, Any], ...] = (
    # Backup Recovery (upstream released P3 cohort: ALL 10 eligible openings)
    {"workflow": "backup_recovery", "day": 5, "focal": '["critical","restricted"]', "sham": '["critical","confidential"]', "direct": ("PR-B1A5DB2AC2",), "status": "released"},
    {"workflow": "backup_recovery", "day": 6, "focal": '["critical","confidential"]', "sham": None, "direct": ("PR-DFEC7F104D",), "status": "released"},
    {"workflow": "backup_recovery", "day": 8, "focal": '["standard","internal"]', "sham": None, "direct": ("PR-B9EFE42247",), "status": "released"},
    {"workflow": "backup_recovery", "day": 9, "focal": '["critical","confidential"]', "sham": None, "direct": ("PR-F56BA4D303",), "status": "released"},
    {"workflow": "backup_recovery", "day": 10, "focal": '["standard","internal"]', "sham": '["critical","confidential"]', "direct": ("PR-E8890AC30B",), "status": "released"},
    {"workflow": "backup_recovery", "day": 11, "focal": '["critical","confidential"]', "sham": '["standard","internal"]', "direct": ("PR-7DED2C1F81",), "status": "released"},
    {"workflow": "backup_recovery", "day": 12, "focal": '["standard","internal"]', "sham": None, "direct": ("PR-A2E0A0F6A2",), "status": "released"},
    {"workflow": "backup_recovery", "day": 13, "focal": '["critical","confidential"]', "sham": '["standard","internal"]', "direct": ("PR-C67AD1A3A9",), "status": "released"},
    {"workflow": "backup_recovery", "day": 14, "focal": '["standard","internal"]', "sham": '["critical","confidential"]', "direct": ("PR-5A16FB7D8F",), "status": "released"},
    {"workflow": "backup_recovery", "day": 15, "focal": '["critical","confidential"]', "sham": None, "direct": ("PR-73110DF43B",), "status": "released"},
    # Railway Ticketing (upstream released P3 cohort: first 8 contiguous openings T09-T16)
    {"workflow": "railway_ticketing", "day": 9, "focal": '["Cedar Point"]', "sham": None, "direct": ("RQ-9d40f90bd396238c01",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 10, "focal": '["Cedar Point"]', "sham": None, "direct": ("RQ-6c5271812da9b7f720",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 11, "focal": '["Maple Junction"]', "sham": None, "direct": ("RQ-07c3b3baf2845c5b5f",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 12, "focal": '["Maple Junction"]', "sham": None, "direct": ("RQ-abc62d88a966f2bb61",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 13, "focal": '["Pine Central"]', "sham": None, "direct": ("RQ-7df501f52bd715c08d",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 14, "focal": '["Pine Central"]', "sham": None, "direct": ("RQ-0aa57fa633afc987d2",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 15, "focal": '["Bay Exchange"]', "sham": None, "direct": ("RQ-5d7e12e39b4992070a",), "status": "released"},
    {"workflow": "railway_ticketing", "day": 16, "focal": '["Bay Exchange"]', "sham": None, "direct": ("RQ-1061afebba5f865b6e",), "status": "released"},
)


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_p4b_cases(suite: str = "all") -> list[AuditCase]:
    suite_map = {
        "all": {"backup_recovery", "railway_ticketing"},
        "released": {"backup_recovery", "railway_ticketing"},
        "backup_recovery": {"backup_recovery"},
        "backup": {"backup_recovery"},
        "railway_ticketing": {"railway_ticketing"},
        "railway": {"railway_ticketing"},
        "qualify": {"backup_recovery"},
    }
    wanted = suite_map[suite]
    cases: list[AuditCase] = []
    for row in FROZEN_P4B_COHORT:
        wf = row["workflow"]
        if wf not in wanted:
            continue
        if suite == "qualify" and row["day"] != 11:
            continue
        day = int(row["day"])
        cases.append(
            AuditCase(
                workflow=wf,
                day=day,
                focal_key=row["focal"],
                sham_key=row["sham"],
                direct_targets=row["direct"],
                opening_world_path=P3_SNAP / f"{wf}-T{day:02d}.json",
                opening_memory_path=None,
                source_root=P3_SRC,
                upstream_release_status=row["status"],
            )
        )
    return cases


def build_p4b_freeze_manifest() -> dict[str, Any]:
    protocol_path = SCRIPT_DIR / "P4B_P3_EXTENSION_PROTOCOL.md"
    eval_ext_dir = PKG_ROOT / "trustmem_bench/eval_ext"
    code_hashes = {
        "run_p4b_p3_extension.py": _sha256_file(Path(__file__)),
    }
    for py_file in sorted(eval_ext_dir.glob("*.py")):
        code_hashes[f"eval_ext/{py_file.name}"] = _sha256_file(py_file)

    snapshot_hashes: dict[str, str] = {}
    all_cases = build_p4b_cases("all")
    for case in all_cases:
        snapshot_hashes[f"{case.case_id()}:world"] = _sha256_file(case.opening_world_path)

    return {
        "schema": "trustmem/model-family-freeze/v1",
        "experiment_id": "P4B_P3_OFFICIAL_WORKFLOWS_NATIVE_AUDIT",
        "status": "frozen_ready_for_local_gpu",
        "paid_api_funding_approved": False,
        "local_gpu_compute_backend": "modelscope_free_gpu",
        "api_usd_cap": 0,
        "protocol_path": "experiments/memory_correctability/P4B_P3_EXTENSION_PROTOCOL.md",
        "protocol_sha256": _sha256_file(protocol_path) if protocol_path.is_file() else None,
        "code_hashes": code_hashes,
        "qualification_cases": ["backup_recovery-T11"],
        "released_p3_extension_cases": [c.case_id() for c in all_cases],
        "opening_snapshot_hashes": snapshot_hashes,
        "opening_snapshot_manifest_sha256": sha256(
            json.dumps(snapshot_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "model_slots": [
            {
                "slot": "A",
                "role": "Family 1 primary reference (Qwen3-32B, 192GB AMD)",
                "provider": "openai_compatible_local",
                "model_version": "Qwen/Qwen3-32B",
                "vllm_tool_parser": "hermes",
            },
            {
                "slot": "C",
                "role": "Family 3 distinct family (Mistral-Small-24B, 192GB AMD)",
                "provider": "openai_compatible_local",
                "model_version": "mistralai/Mistral-Small-24B-Instruct-2501",
                "vllm_tool_parser": "mistral",
            },
            {
                "slot": "B",
                "role": "Family 2 distinct family (Llama-3.3-70B, 192GB AMD)",
                "provider": "openai_compatible_local",
                "model_version": "LLM-Research/Llama-3.3-70B-Instruct",
                "vllm_tool_parser": "llama3_json",
            },
        ],
        "qualification_attempt_cap": 250,
        "matrix_attempt_cap_per_slot": 4000,
        "session_protocol": "single_native_call_per_turn",
        "max_output_tokens": 384,
        "keep_repeats": 3,
        "analysis_units": ["workflow_history", "paired_cell"],
    }


def cmd_freeze(args: argparse.Namespace) -> None:
    manifest = build_p4b_freeze_manifest()
    out = Path(args.out)
    _write_json(out, manifest)
    print(f"Wrote P4b freeze manifest to {out} ({len(manifest['opening_snapshot_hashes'])} snapshots pinned)")


def _collect_dir_entries(src_dir: Path, arc_prefix: str) -> list[tuple[Path, str]]:
    entries: list[tuple[Path, str]] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(src_dir).as_posix()
        entries.append((path, f"{arc_prefix}/{rel}"))
    return entries


def cmd_pack(args: argparse.Namespace) -> None:
    if (SCRIPT_DIR / "BUNDLE_MANIFEST.json").is_file():
        raise RuntimeError("Run `pack` from the main workspace, not inside an unpacked bundle.")

    freeze_path = SCRIPT_DIR / "P4B_P3_EXTENSION_FREEZE.json"
    manifest = build_p4b_freeze_manifest()
    _write_json(freeze_path, manifest)

    entries: list[tuple[Path, str]] = []
    entries.append((Path(__file__), "run_p4b_p3_extension.py"))
    for helper_name in (
        "run_all_amd_p4b.sh",
        "summarize_p4_matrix.py",
        "P4B_P3_EXTENSION_PROTOCOL.md",
    ):
        helper_path = SCRIPT_DIR / helper_name
        if helper_path.is_file():
            entries.append((helper_path, helper_name))
    entries.append((freeze_path, "P4B_P3_EXTENSION_FREEZE.json"))

    tb_init = PKG_ROOT / "trustmem_bench/__init__.py"
    if tb_init.is_file():
        entries.append((tb_init, "trustmem_bench/__init__.py"))
    entries.extend(_collect_dir_entries(PKG_ROOT / "trustmem_bench/eval_ext", "trustmem_bench/eval_ext"))

    # Pinned P3 shared modules + agent_runtime + backup_recovery + railway_ticketing
    p3_pkg = P3_SRC / "rescopebench"
    for py_file in sorted(p3_pkg.glob("*.py")):
        entries.append((py_file, f"sources/p3/rescopebench/{py_file.name}"))
    entries.append((p3_pkg / "cases/__init__.py", "sources/p3/rescopebench/cases/__init__.py"))
    entries.extend(_collect_dir_entries(p3_pkg / "agent_runtime", "sources/p3/rescopebench/agent_runtime"))
    entries.extend(_collect_dir_entries(p3_pkg / "cases/backup_recovery", "sources/p3/rescopebench/cases/backup_recovery"))
    entries.extend(_collect_dir_entries(p3_pkg / "cases/railway_ticketing", "sources/p3/rescopebench/cases/railway_ticketing"))

    for case in build_p4b_cases("all"):
        entries.append((case.opening_world_path, f"snapshots/p3/{case.opening_world_path.name}"))

    bundle_hashes: dict[str, str] = {}
    out_zip = Path(args.out)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in entries:
            data = src.read_bytes()
            bundle_hashes[arc] = sha256(data).hexdigest()
            zf.writestr(arc, data)
        bundle_manifest = {
            "schema": "trustmem/p4b-modelscope-bundle/v1",
            "file_count": len(bundle_hashes),
            "files": bundle_hashes,
        }
        zf.writestr(
            "BUNDLE_MANIFEST.json",
            json.dumps(bundle_manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        )

    size_mb = out_zip.stat().st_size / (1024 * 1024)
    print(f"Packed {len(bundle_hashes)} files into {out_zip} ({size_mb:.2f} MB)")


def cmd_verify_bundle(_args: argparse.Namespace) -> None:
    manifest_path = SCRIPT_DIR / "BUNDLE_MANIFEST.json"
    if not manifest_path.is_file():
        raise RuntimeError("BUNDLE_MANIFEST.json not found next to run_p4b_p3_extension.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for rel, expected in sorted(manifest["files"].items()):
        path = SCRIPT_DIR / rel
        if not path.is_file():
            mismatches.append((rel, "missing"))
            continue
        actual = _sha256_file(path)
        if actual != expected:
            mismatches.append((rel, f"sha mismatch {actual[:12]} != {expected[:12]}"))
    if mismatches:
        raise RuntimeError(f"Bundle verification failed ({len(mismatches)} issues): {mismatches[:5]}")

    for wf in ("backup_recovery", "railway_ticketing"):
        driver, _ = load_p4b_driver(wf, P3_SRC)
        world = driver.create_world()
        if hasattr(world, "close"):
            world.close()
    print(f"P4b Bundle OK: {manifest['file_count']} files verified, both P3 released drivers load cleanly.")


def _arm_seed(arm: str, base_seed: int) -> int:
    if arm.startswith("keep_r"):
        idx = int(arm.split("keep_r", 1)[1])
        return base_seed + idx
    return base_seed


def _execute_branch(
    *,
    case: AuditCase,
    arm: str,
    out_dir: Path,
    base_url: str,
    model: str,
    api_key_env: str | None,
    seed: int,
    temperature: float,
    max_output_tokens: int,
    extra_body: dict[str, Any],
    endpoint_profile: str,
    budget: AttemptBudget,
    fee_prefix_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    branch_dir = out_dir / case.case_id() / f"native__{arm}"
    ep_path = branch_dir / "EPISODE.json"
    if ep_path.is_file():
        return json.loads(ep_path.read_text(encoding="utf-8"))

    branch_dir.mkdir(parents=True, exist_ok=True)
    tape_path = branch_dir / "model_calls.jsonl"
    ledger_path = branch_dir / "attempt_ledger.jsonl"
    if tape_path.exists():
        tape_path.unlink()
    if ledger_path.exists():
        ledger_path.unlink()

    cfg = OpenAICompatibleConfig(
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        temperature=temperature,
        seed=seed,
        extra_body=extra_body,
        endpoint_profile=endpoint_profile,
    )
    cfg_sha = cfg.fingerprint()
    live = OpenAICompatibleAdapter(cfg, budget=budget, bound_nano_usd=1)
    recorder = RecordingAdapter(live, tape_path, ledger_path=ledger_path)

    episode = run_p4b_native_episode(
        case,
        arm,
        recorder,
        provider=cfg.provider,
        model=cfg.model,
        config_sha256=cfg_sha,
        max_output_tokens=max_output_tokens,
        fee_prefix_source=fee_prefix_source,
    )

    meta = {
        "case_id": case.case_id(),
        "workflow": case.workflow,
        "day": case.day,
        "interface": "native",
        "arm": arm,
        "provider": cfg.provider,
        "model": cfg.model,
        "config_sha256": cfg_sha,
        "seed": seed,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "extra_body": extra_body,
        "endpoint_profile": endpoint_profile,
        "tape_exists": tape_path.is_file(),
        "tape_sha256": _sha256_file(tape_path) if tape_path.is_file() else None,
        "recorded_calls": recorder.recorded_count,
    }
    _write_json(branch_dir / "BRANCH_META.json", meta)
    _write_json(ep_path, episode)
    return episode


def _aggregate_reports(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    def agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
        ok = [r for r in rows if r.get("status") == "ok"]
        workflows = sorted({r["workflow"] for r in ok})
        fee_ok = [r["fee_only_effect"] for r in ok if (r.get("fee_only_effect") or {}).get("status") == "ok"]
        arch_ok = [r["archive_effect"] for r in ok if (r.get("archive_effect") or {}).get("status") == "ok"]
        return {
            "workflows": workflows,
            "workflow_count": len(workflows),
            "paired_cases": len(ok),
            "keep_set_stable": sum(bool(r["variance_controls"]["keep_set_stable"]) for r in ok),
            "sham_available": sum(r["variance_controls"]["sham_set_matches_keep"] is not None for r in ok),
            "sham_matches_keep": sum(r["variance_controls"]["sham_set_matches_keep"] is True for r in ok),
            "total_set_changed": sum(bool(r["total_effect"]["total_set_changed"]) for r in ok),
            "outside_changed": sum(bool(r["total_effect"]["outside_changed"]) for r in ok),
            "pre_charge_dispatch_changed": sum(bool(r["total_effect"]["pre_charge_dispatch_changed"]) for r in ok),
            "same_value_reread_triggered": sum(bool(r["total_effect"]["same_value_reread_triggered"]) for r in ok),
            "signal_above_keep_and_sham_noise": sum(
                bool(r["total_effect"]["signal_above_keep_and_sham_noise"]) for r in ok
            ),
            "missed_by_total_count_only": sum(bool(r["total_effect"]["missed_by_total_count_only"]) for r in ok),
            "missed_by_direct_target_only": sum(bool(r["total_effect"]["missed_by_direct_target_only"]) for r in ok),
            "missed_by_both_counts": sum(bool(r["total_effect"]["missed_by_both_counts"]) for r in ok),
            "fee_only_eligible": len(fee_ok),
            "fee_only_set_changed": sum(bool(f["set_changed"]) for f in fee_ok),
            "fee_only_outside_changed": sum(bool(f["outside_changed"]) for f in fee_ok),
            "fee_only_direction_reversals": sum(bool(f["direction_reversal"]) for f in fee_ok),
            "fee_only_prefix_calls_saved": sum(int(f["prefix_replayed_calls"]) for f in fee_ok),
            "archive_tested": len(arch_ok),
            "archive_used": sum(bool(a["used_archive"]) for a in arch_ok),
            "archive_matches_keep_set": sum(bool(a["matches_keep_set"]) for a in arch_ok),
        }

    return {
        "released_only": agg([r for r in summaries if r.get("upstream_release_status") == "released"]),
        "candidate_model_validation": agg(
            [r for r in summaries if r.get("upstream_release_status") != "released"]
        ),
        "all_workflows": agg(summaries),
    }


def _write_summary_csv(path: Path, summaries: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "workflow",
        "day",
        "upstream_release_status",
        "keep_set_stable",
        "sham_set_matches_keep",
        "total_set_changed",
        "total_count_delta",
        "outside_changed",
        "pre_charge_dispatch_changed",
        "same_value_reread_triggered",
        "signal_above_noise",
        "fee_status",
        "fee_count_delta",
        "fee_outside_changed",
        "fee_direction_reversal",
        "archive_used",
        "archive_matches_keep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for r in summaries:
            if r.get("status") != "ok":
                continue
            vc = r["variance_controls"]
            te = r["total_effect"]
            fe = r.get("fee_only_effect") or {}
            ae = r.get("archive_effect") or {}
            writer.writerow(
                {
                    "case_id": r["case_id"],
                    "workflow": r["workflow"],
                    "day": r["day"],
                    "upstream_release_status": r["upstream_release_status"],
                    "keep_set_stable": vc["keep_set_stable"],
                    "sham_set_matches_keep": vc["sham_set_matches_keep"],
                    "total_set_changed": te["total_set_changed"],
                    "total_count_delta": te["total_count_delta"],
                    "outside_changed": te["outside_changed"],
                    "pre_charge_dispatch_changed": te["pre_charge_dispatch_changed"],
                    "same_value_reread_triggered": te["same_value_reread_triggered"],
                    "signal_above_noise": te["signal_above_keep_and_sham_noise"],
                    "fee_status": fe.get("status", "not_run"),
                    "fee_count_delta": fe.get("completed_count_delta", ""),
                    "fee_outside_changed": fe.get("outside_changed", ""),
                    "fee_direction_reversal": fe.get("direction_reversal", ""),
                    "archive_used": ae.get("used_archive", ""),
                    "archive_matches_keep": ae.get("matches_keep_set", ""),
                }
            )


def _run_suite(args: argparse.Namespace, *, suite: str, is_qualify: bool) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    extra_body = json.loads(args.extra_body) if args.extra_body else {}
    budget = AttemptBudget(cap_nano_usd=args.call_cap, cap_attempts=args.call_cap)

    run_config = {
        "schema": "trustmem/p4b-run-config/v1",
        "mode": "qualify" if is_qualify else "main_matrix",
        "slot": args.slot,
        "suite": suite,
        "model": args.model,
        "base_url": args.base_url,
        "temperature": args.temperature,
        "base_seed": args.seed,
        "max_output_tokens": args.max_output_tokens,
        "extra_body": extra_body,
        "endpoint_profile": args.endpoint_profile,
        "call_cap": args.call_cap,
        "api_usd": 0,
    }
    _write_json(out_dir / "RUN_CONFIG.json", run_config)

    cases = build_p4b_cases("qualify" if is_qualify else suite)
    summaries: list[dict[str, Any]] = []
    total_native_turns = 0
    total_parse_errors = 0

    for case in cases:
        arms_to_run = ["keep_r0", "keep_r1"]
        if not is_qualify:
            arms_to_run.append("keep_r2")
        arms_to_run.extend(["sham", "remove", "archive"])

        case_arms: dict[str, dict[str, Any]] = {}
        for arm in arms_to_run:
            ep = _execute_branch(
                case=case,
                arm=arm,
                out_dir=out_dir,
                base_url=args.base_url,
                model=args.model,
                api_key_env=args.api_key_env,
                seed=_arm_seed(arm, args.seed),
                temperature=args.temperature,
                max_output_tokens=args.max_output_tokens,
                extra_body=extra_body,
                endpoint_profile=args.endpoint_profile,
                budget=budget,
            )
            case_arms[arm] = ep
            if ep.get("status") == "ok":
                total_native_turns += int(ep["model_calls"])
                total_parse_errors += len(ep.get("parse_errors", []))
            print(
                f"[{case.case_id()}][native][{arm}] status={ep.get('status')} "
                f"completed={ep.get('completed_count')}/{ep.get('total_targets')} "
                f"spent={ep.get('budget_spent')} stop={ep.get('stop_reason')}",
                flush=True,
            )

        fee_ep = _execute_branch(
            case=case,
            arm="fee_only",
            out_dir=out_dir,
            base_url=args.base_url,
            model=args.model,
            api_key_env=args.api_key_env,
            seed=_arm_seed("fee_only", args.seed),
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            extra_body=extra_body,
            endpoint_profile=args.endpoint_profile,
            budget=budget,
            fee_prefix_source=case_arms["remove"],
        )
        case_arms["fee_only"] = fee_ep
        if fee_ep.get("status") == "ok":
            total_native_turns += int(fee_ep["model_calls"])
            total_parse_errors += len(fee_ep.get("parse_errors", []))
        print(
            f"[{case.case_id()}][native][fee_only] status={fee_ep.get('status')} "
            f"completed={fee_ep.get('completed_count')}/{fee_ep.get('total_targets')} "
            f"spent={fee_ep.get('budget_spent')}",
            flush=True,
        )

        summaries.append(summarize_case_audit(case, case_arms))

    _write_json(out_dir / "CASE_SUMMARIES.json", summaries)
    _write_summary_csv(out_dir / "SUMMARY_TABLE.csv", summaries)
    _write_json(out_dir / "AGGREGATE_REPORT.json", _aggregate_reports(summaries))

    if is_qualify:
        k0 = json.loads((out_dir / "backup_recovery-T11/native__keep_r0/EPISODE.json").read_text(encoding="utf-8"))
        k1 = json.loads((out_dir / "backup_recovery-T11/native__keep_r1/EPISODE.json").read_text(encoding="utf-8"))
        rem = json.loads((out_dir / "backup_recovery-T11/native__remove/EPISODE.json").read_text(encoding="utf-8"))
        arch = json.loads((out_dir / "backup_recovery-T11/native__archive/EPISODE.json").read_text(encoding="utf-8"))
        parse_err_rate = (total_parse_errors / total_native_turns) if total_native_turns else 1.0
        max_any_comp = max(
            int(k0["completed_count"]),
            int(k1["completed_count"]),
            int(rem["completed_count"]),
            int(arch["completed_count"]),
        )
        # All 3 P4b models already passed P4 Gate 2; here require clean native tool calling (parse_err <= 25%)
        # and valid grading without falsely discarding negative-memory cases (e.g., keep=0/4, remove=1/4).
        passed = (parse_err_rate <= 0.25) and bool(k0["grade_valid"])
        verdict = {
            "slot": args.slot,
            "model": args.model,
            "qualification_case": "backup_recovery-T11",
            "passed": passed,
            "verdict": "QUALIFIED" if passed else "DISQUALIFIED_INTERFACE",
            "total_native_turns": total_native_turns,
            "total_parse_errors": total_parse_errors,
            "parse_error_rate": round(parse_err_rate, 4),
            "keep_r0_completed": k0["completed_count"],
            "keep_r1_completed": k1["completed_count"],
            "remove_completed": rem["completed_count"],
            "archive_completed": arch["completed_count"],
            "max_completed_any_arm": max_any_comp,
        }
        _write_json(out_dir / "QUALIFICATION_VERDICT.json", verdict)
        print("QUALIFICATION VERDICT:", json.dumps(verdict, ensure_ascii=False))


def cmd_qualify(args: argparse.Namespace) -> None:
    _run_suite(args, suite="qualify", is_qualify=True)


def cmd_run(args: argparse.Namespace) -> None:
    _run_suite(args, suite=args.suite, is_qualify=False)


def cmd_replay(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    case_index = {c.case_id(): c for c in build_p4b_cases("all")}

    meta_files = sorted(run_dir.glob("*/*/BRANCH_META.json"))
    if not meta_files:
        raise RuntimeError(f"No recorded branches found under {run_dir}")

    ordered_metas = sorted(
        meta_files,
        key=lambda p: (1 if "__fee_only" in p.parent.name else 0, str(p)),
    )
    replayed_cache: dict[tuple[str, str], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    mismatches = 0

    for meta_path in ordered_metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        branch_dir = meta_path.parent
        recorded_ep = json.loads((branch_dir / "EPISODE.json").read_text(encoding="utf-8"))
        case = case_index[meta["case_id"]]
        arm = meta["arm"]

        if recorded_ep.get("status") != "ok":
            rows.append(
                {
                    "case_id": meta["case_id"],
                    "interface": "native",
                    "arm": arm,
                    "status": recorded_ep.get("status"),
                    "matched": True,
                }
            )
            continue

        tape_path = branch_dir / "model_calls.jsonl"
        replay_adapter = RecordedReplayAdapter(tape_path)
        fee_src = replayed_cache.get((meta["case_id"], "remove")) if arm == "fee_only" else None
        replayed = run_p4b_native_episode(
            case,
            arm,
            replay_adapter,
            provider=meta["provider"],
            model=meta["model"],
            config_sha256=meta["config_sha256"],
            max_output_tokens=int(meta["max_output_tokens"]),
            fee_prefix_source=fee_src,
        )
        replay_adapter.assert_exhausted()
        replayed_cache[(meta["case_id"], arm)] = replayed

        matched = (
            replayed["completed"] == recorded_ep["completed"]
            and replayed["budget_spent"] == recorded_ep["budget_spent"]
            and replayed["stop_reason"] == recorded_ep["stop_reason"]
            and replayed["native_log"] == recorded_ep["native_log"]
        )
        if not matched:
            mismatches += 1
        rows.append(
            {
                "case_id": meta["case_id"],
                "interface": "native",
                "arm": arm,
                "status": "ok",
                "matched": matched,
                "completed": replayed["completed"],
                "budget_spent": replayed["budget_spent"],
            }
        )

    report = {
        "run_dir": str(run_dir),
        "branches_checked": len(rows),
        "mismatches": mismatches,
        "all_matched": mismatches == 0,
        "api_usd": 0,
        "rows": rows,
    }
    _write_json(out_dir / "REPLAY_VERIFICATION.json", report)
    print(f"P4b offline replay verification: {len(rows)} branches checked, {mismatches} mismatches.")
    if mismatches > 0:
        raise SystemExit(1)


def _add_model_args(parser: argparse.ArgumentParser, default_cap: int) -> None:
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL")
    parser.add_argument("--model", required=True, help="Served model name")
    parser.add_argument("--slot", required=True, help="Model slot label (A, B, C)")
    parser.add_argument("--out", required=True, type=Path, help="Output directory")
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--max-output-tokens", type=int, default=384)
    parser.add_argument("--extra-body", default=None)
    parser.add_argument("--endpoint-profile", default="modelscope_vllm_local")
    parser.add_argument("--call-cap", type=int, default=default_cap)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze", help="Generate/update P4B_P3_EXTENSION_FREEZE.json")
    p_freeze.add_argument("--out", type=Path, default=SCRIPT_DIR / "P4B_P3_EXTENSION_FREEZE.json")
    p_freeze.set_defaults(func=cmd_freeze)

    p_pack = sub.add_parser("pack", help="Pack portable ModelScope P4b ZIP bundle")
    p_pack.add_argument("--out", type=Path, required=True)
    p_pack.set_defaults(func=cmd_pack)

    p_verify = sub.add_parser("verify-bundle", help="Verify unpacked P4b bundle integrity and drivers")
    p_verify.set_defaults(func=cmd_verify_bundle)

    p_qual = sub.add_parser("qualify", help="Run Gate 2 qualification on backup_recovery-T11")
    _add_model_args(p_qual, default_cap=250)
    p_qual.set_defaults(func=cmd_qualify)

    p_run = sub.add_parser("run", help="Run frozen P4b P3-extension native audit matrix")
    _add_model_args(p_run, default_cap=4000)
    p_run.add_argument(
        "--suite",
        choices=("backup_recovery", "railway_ticketing", "released", "all"),
        default="all",
    )
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("replay", help="Zero-GPU offline verification via RecordedReplayAdapter")
    p_rep.add_argument("--run-dir", type=Path, required=True)
    p_rep.add_argument("--out", type=Path, required=True)
    p_rep.set_defaults(func=cmd_replay)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
