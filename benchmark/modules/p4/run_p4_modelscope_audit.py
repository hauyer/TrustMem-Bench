"""Portable CLI runner, ModelScope bundle packager, and offline replay verifier for P4.

Subcommands:
  freeze        Write/refresh P4_MODELSCOPE_FREEZE.json with SHA-256 hashes of pinned code & snapshots.
  pack          Build a self-contained portable ZIP (~2 MB) ready to upload to ModelScope Notebook.
  verify-bundle Verify all SHA-256 hashes inside an unpacked bundle and smoke-load all 3 ReScopeBench drivers.
  qualify       Run Gate 1 / Gate 2 qualification on forms T11 and emit PASS/DISQUALIFIED verdict.
  run           Run the frozen multi-workflow native counterfactual audit with per-branch resume & tape recording.
  replay        Zero-GPU offline verification replaying every recorded model_calls.jsonl tape via RecordedReplayAdapter.
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


def _resolve_layout() -> tuple[Path, Path, Path, Path, Path, Path]:
    """Detect whether running inside an unpacked ModelScope bundle or the research workspace."""
    if (SCRIPT_DIR / "BUNDLE_MANIFEST.json").is_file():
        bundle = SCRIPT_DIR
        pkg_root = bundle
        forms_src = bundle / "sources/forms"
        p3_src = bundle / "sources/p3"
        forms_snap = bundle / "snapshots/forms"
        p3_snap = bundle / "snapshots/p3"
        return bundle, pkg_root, forms_src, p3_src, forms_snap, p3_snap

    workspace = SCRIPT_DIR.parents[1]
    pkg_root = workspace / "github-release/TrustMem-Bench"
    forms_src = workspace / "artifacts/research_decisions/20261119-c93-native-oracle-source-v1/source"
    p3_src = workspace / "artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1/sources"
    forms_snap = workspace / "artifacts/research_decisions/20261119-c93-oracle-archive-path-v1"
    p3_snap = workspace / "artifacts/research_decisions/20261120-p3-prospective-audit-increment-v1/CHECKPOINTS"
    return workspace, pkg_root, forms_src, p3_src, forms_snap, p3_snap


ROOT_DIR, PKG_ROOT, FORMS_SRC, P3_SRC, FORMS_SNAP, P3_SNAP = _resolve_layout()
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from trustmem_bench.eval_ext.budget import AttemptBudget  # noqa: E402
from trustmem_bench.eval_ext.native_audit import (  # noqa: E402
    AuditCase,
    load_rescopebench_driver,
    run_forms_menu_episode,
    run_native_episode,
    summarize_case_audit,
)
from trustmem_bench.eval_ext.openai_compatible import (  # noqa: E402
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
    RecordingAdapter,
)
from trustmem_bench.eval_ext.recorded import RecordedReplayAdapter  # noqa: E402


FROZEN_COHORT: tuple[dict[str, Any], ...] = (
    # Forms (released, 3 tools, budget 17, T11-T16)
    {"workflow": "forms", "day": 11, "focal": "cr-d90f63b7", "sham": "cr-18b5ea74", "direct": ("cr-d90f63b7",), "status": "released"},
    {"workflow": "forms", "day": 12, "focal": "cr-c64a097e", "sham": "cr-42e8c1ad", "direct": ("cr-c64a097e",), "status": "released"},
    {"workflow": "forms", "day": 13, "focal": "cr-7f3b912c", "sham": "cr-18b5ea74", "direct": ("cr-7f3b912c",), "status": "released"},
    {"workflow": "forms", "day": 14, "focal": "cr-18b5ea74", "sham": "cr-42e8c1ad", "direct": ("cr-18b5ea74",), "status": "released"},
    {"workflow": "forms", "day": 15, "focal": "cr-d90f63b7", "sham": "cr-18b5ea74", "direct": ("cr-d90f63b7",), "status": "released"},
    {"workflow": "forms", "day": 16, "focal": "cr-c64a097e", "sham": "cr-42e8c1ad", "direct": ("cr-c64a097e",), "status": "released"},
    # Medical Appointment (released, 4 tools, budget 72, T11-T16)
    {"workflow": "medical_appointment", "day": 11, "focal": '["patient-harper-reed"]', "sham": '["patient-adeline-baker"]', "direct": ("patient-harper-reed",), "status": "released"},
    {"workflow": "medical_appointment", "day": 12, "focal": '["patient-harper-reed"]', "sham": '["patient-ariana-foster"]', "direct": ("patient-harper-reed",), "status": "released"},
    {"workflow": "medical_appointment", "day": 13, "focal": '["patient-marcus-walker"]', "sham": '["patient-ariana-foster"]', "direct": ("patient-marcus-walker",), "status": "released"},
    {"workflow": "medical_appointment", "day": 14, "focal": '["patient-ariana-santos"]', "sham": '["patient-adeline-baker"]', "direct": ("patient-ariana-santos",), "status": "released"},
    {"workflow": "medical_appointment", "day": 15, "focal": '["patient-harper-reed"]', "sham": '["patient-ariana-foster"]', "direct": ("patient-harper-reed",), "status": "released"},
    {"workflow": "medical_appointment", "day": 16, "focal": '["patient-harper-reed"]', "sham": '["patient-ariana-foster"]', "direct": ("patient-harper-reed",), "status": "released"},
    # API Reliability (candidate_model_validation, 5 tools, budget 57, T09-T16)
    {"workflow": "api_reliability", "day": 9, "focal": '["queued_replay","mutation"]', "sham": '["queued_replay","decision"]', "direct": ("call-77dc7024e90b",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 10, "focal": '["queued_replay","mutation"]', "sham": '["queued_replay","decision"]', "direct": ("call-c5749c9f7100",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 11, "focal": '["queued_replay","mutation"]', "sham": '["queued_replay","decision"]', "direct": ("call-38132c27c98a",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 12, "focal": '["queued_replay","mutation"]', "sham": '["queued_replay","decision"]', "direct": ("call-79084b048b85",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 13, "focal": '["queued_replay","mutation"]', "sham": '["queued_replay","decision"]', "direct": ("call-7fa5a9cc6676",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 14, "focal": '["queued_replay","observation"]', "sham": '["queued_replay","mutation"]', "direct": ("call-f74dd39a477d",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 15, "focal": '["queued_replay","observation"]', "sham": '["provider_5xx","decision"]', "direct": ("call-b5678f50b142",), "status": "candidate_model_validation"},
    {"workflow": "api_reliability", "day": 16, "focal": '["queued_replay","decision"]', "sham": '["queued_replay","observation"]', "direct": ("call-a1255c398399",), "status": "candidate_model_validation"},
)


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_cases(suite: str = "all") -> list[AuditCase]:
    suite_map = {
        "all": {"forms", "medical_appointment", "api_reliability"},
        "released": {"forms", "medical_appointment"},
        "forms": {"forms"},
        "medical": {"medical_appointment"},
        "medical_appointment": {"medical_appointment"},
        "api": {"api_reliability"},
        "api_reliability": {"api_reliability"},
        "qualify": {"forms"},
    }
    wanted = suite_map[suite]
    cases: list[AuditCase] = []
    for row in FROZEN_COHORT:
        wf = row["workflow"]
        if wf not in wanted:
            continue
        if suite == "qualify" and row["day"] != 11:
            continue
        day = int(row["day"])
        if wf == "forms":
            day_dir = FORMS_SNAP / f"T{day:02d}"
            cases.append(
                AuditCase(
                    workflow=wf,
                    day=day,
                    focal_key=row["focal"],
                    sham_key=row["sham"],
                    direct_targets=row["direct"],
                    opening_world_path=day_dir / "OPENING.json",
                    opening_memory_path=day_dir / "PUBLIC_MEMORY.json",
                    source_root=FORMS_SRC,
                    upstream_release_status=row["status"],
                )
            )
        else:
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


def build_freeze_manifest() -> dict[str, Any]:
    protocol_path = SCRIPT_DIR / "P4_MODELSCOPE_MULTIMODEL_AUDIT_PROTOCOL.md"
    eval_ext_dir = PKG_ROOT / "trustmem_bench/eval_ext"
    code_hashes = {
        "run_p4_modelscope_audit.py": _sha256_file(Path(__file__)),
    }
    for py_file in sorted(eval_ext_dir.glob("*.py")):
        code_hashes[f"eval_ext/{py_file.name}"] = _sha256_file(py_file)

    snapshot_hashes: dict[str, str] = {}
    all_cases = build_cases("all")
    for case in all_cases:
        snapshot_hashes[f"{case.case_id()}:world"] = _sha256_file(case.opening_world_path)
        if case.opening_memory_path is not None:
            snapshot_hashes[f"{case.case_id()}:memory"] = _sha256_file(case.opening_memory_path)

    return {
        "schema": "trustmem/model-family-freeze/v1",
        "experiment_id": "P4_MODELSCOPE_MULTIMODEL_NATIVE_AUDIT",
        "status": "frozen_ready_for_local_gpu",
        "paid_api_funding_approved": False,
        "local_gpu_compute_backend": "modelscope_free_gpu",
        "api_usd_cap": 0,
        "protocol_path": "experiments/memory_correctability/P4_MODELSCOPE_MULTIMODEL_AUDIT_PROTOCOL.md",
        "protocol_sha256": _sha256_file(protocol_path) if protocol_path.is_file() else None,
        "code_hashes": code_hashes,
        "qualification_cases": ["forms-T11"],
        "mechanism_recheck_released_cases": [
            c.case_id() for c in all_cases if c.upstream_release_status == "released"
        ],
        "mechanism_recheck_candidate_cases": [
            c.case_id() for c in all_cases if c.upstream_release_status != "released"
        ],
        "opening_snapshot_hashes": snapshot_hashes,
        "opening_snapshot_manifest_sha256": sha256(
            json.dumps(snapshot_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "model_slots": [
            {
                "slot": "Q0",
                "role": "Gate 1 CUDA qualification (24GB VRAM)",
                "provider": "openai_compatible_local",
                "model_version": "Qwen/Qwen2.5-7B-Instruct",
                "vllm_tool_parser": "hermes",
            },
            {
                "slot": "A",
                "role": "Family 1 primary reference + same-weight menu-vs-native + thinking contrast (192GB AMD)",
                "provider": "openai_compatible_local",
                "model_version": "Qwen/Qwen3-32B",
                "backup_model": "Qwen/Qwen2.5-72B-Instruct",
                "vllm_tool_parser": "hermes",
            },
            {
                "slot": "B",
                "role": "Family 2 distinct family (Meta Llama, 192GB AMD)",
                "provider": "openai_compatible_local",
                "model_version": "LLM-Research/Llama-3.3-70B-Instruct",
                "vllm_tool_parser": "llama3_json",
            },
            {
                "slot": "C",
                "role": "Family 3 distinct family (Mistral or GLM-4, 192GB AMD)",
                "provider": "openai_compatible_local",
                "model_version": "mistralai/Mistral-Small-24B-Instruct-2501",
                "backup_model": "ZhipuAI/GLM-4-32B-0414",
                "vllm_tool_parser": "mistral",
            },
        ],
        "qualification_attempt_cap": 150,
        "qualification_cap_nano_usd": 150,
        "matrix_attempt_cap_per_slot": 2000,
        "matrix_cap_nano_usd_per_slot": 2000,
        "session_protocol": "single_native_call_per_turn",
        "analysis_units": ["workflow_history", "paired_cell"],
        "stopping_gates": {
            "gate_0": "offline unit + real-world integration tests pass and bundle SHA-256 verified",
            "gate_1": "24GB CUDA forms-T11 qualification has 0 transport crashes and 100% offline tape replay match",
            "gate_2": "per-slot AMD forms-T11 parse error rate <= 25% and >= 1 legal completion in keep repeats",
        },
    }


def cmd_freeze(args: argparse.Namespace) -> None:
    manifest = build_freeze_manifest()
    out = Path(args.out)
    _write_json(out, manifest)
    print(f"Wrote freeze manifest to {out} ({len(manifest['opening_snapshot_hashes'])} snapshots pinned)")


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

    freeze_path = SCRIPT_DIR / "P4_MODELSCOPE_FREEZE.json"
    manifest = build_freeze_manifest()
    _write_json(freeze_path, manifest)

    entries: list[tuple[Path, str]] = []
    # 1. Runner, automation shell script, matrix summarizer, protocol, freeze manifest
    entries.append((Path(__file__), "run_p4_modelscope_audit.py"))
    for helper_name in (
        "run_all_amd_slots.sh",
        "summarize_p4_matrix.py",
        "P4_MODELSCOPE_MULTIMODEL_AUDIT_PROTOCOL.md",
    ):
        helper_path = SCRIPT_DIR / helper_name
        if helper_path.is_file():
            entries.append((helper_path, helper_name))
    entries.append((freeze_path, "P4_MODELSCOPE_FREEZE.json"))

    # 2. trustmem_bench package minimal init + eval_ext
    tb_init = PKG_ROOT / "trustmem_bench/__init__.py"
    if tb_init.is_file():
        entries.append((tb_init, "trustmem_bench/__init__.py"))
    entries.extend(_collect_dir_entries(PKG_ROOT / "trustmem_bench/eval_ext", "trustmem_bench/eval_ext"))

    # 3. Pinned Forms ReScopeBench source
    entries.extend(_collect_dir_entries(FORMS_SRC / "rescopebench", "sources/forms/rescopebench"))

    # 4. Pinned P3 ReScopeBench shared modules + agent_runtime + medical_appointment + api_reliability
    p3_pkg = P3_SRC / "rescopebench"
    for py_file in sorted(p3_pkg.glob("*.py")):
        entries.append((py_file, f"sources/p3/rescopebench/{py_file.name}"))
    entries.append((p3_pkg / "cases/__init__.py", "sources/p3/rescopebench/cases/__init__.py"))
    entries.extend(_collect_dir_entries(p3_pkg / "agent_runtime", "sources/p3/rescopebench/agent_runtime"))
    entries.extend(_collect_dir_entries(p3_pkg / "cases/medical_appointment", "sources/p3/rescopebench/cases/medical_appointment"))
    entries.extend(_collect_dir_entries(p3_pkg / "cases/api_reliability", "sources/p3/rescopebench/cases/api_reliability"))

    # 5. Frozen opening snapshots for all 20 batches
    for case in build_cases("all"):
        if case.workflow == "forms":
            tag = f"T{case.day:02d}"
            entries.append((case.opening_world_path, f"snapshots/forms/{tag}/OPENING.json"))
            assert case.opening_memory_path is not None
            entries.append((case.opening_memory_path, f"snapshots/forms/{tag}/PUBLIC_MEMORY.json"))
        else:
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
            "schema": "trustmem/p4-modelscope-bundle/v1",
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
        raise RuntimeError("BUNDLE_MANIFEST.json not found next to run_p4_modelscope_audit.py")
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

    for wf, src in (("forms", FORMS_SRC), ("medical_appointment", P3_SRC), ("api_reliability", P3_SRC)):
        driver, _ = load_rescopebench_driver(wf, src)
        world = driver.create_world()
        if hasattr(world, "close"):
            world.close()
    print(f"Bundle OK: {manifest['file_count']} files verified, all 3 ReScopeBench drivers load cleanly.")


def _arm_seed(arm: str, base_seed: int) -> int:
    if arm.startswith("keep_r"):
        idx = int(arm.split("keep_r", 1)[1])
        return base_seed + idx
    return base_seed


def _execute_branch(
    *,
    case: AuditCase,
    interface: str,
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
    branch_dir = out_dir / case.case_id() / f"{interface}__{arm}"
    ep_path = branch_dir / "EPISODE.json"
    if ep_path.is_file():
        return json.loads(ep_path.read_text(encoding="utf-8"))

    branch_dir.mkdir(parents=True, exist_ok=True)
    tape_path = branch_dir / "model_calls.jsonl"
    ledger_path = branch_dir / "attempt_ledger.jsonl"
    # Clean any partial incomplete tape from an interrupted run before writing.
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

    if interface == "native":
        episode = run_native_episode(
            case,
            arm,
            recorder,
            provider=cfg.provider,
            model=cfg.model,
            config_sha256=cfg_sha,
            max_output_tokens=max_output_tokens,
            fee_prefix_source=fee_prefix_source,
        )
    elif interface == "menu":
        episode = run_forms_menu_episode(
            case,
            arm,
            recorder,
            provider=cfg.provider,
            model=cfg.model,
            config_sha256=cfg_sha,
            max_output_tokens=max_output_tokens,
        )
    else:
        raise ValueError(f"Unsupported interface: {interface}")

    meta = {
        "case_id": case.case_id(),
        "workflow": case.workflow,
        "day": case.day,
        "interface": interface,
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
        "schema": "trustmem/p4-run-config/v1",
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
        "with_menu": bool(args.with_menu),
        "call_cap": args.call_cap,
        "api_usd": 0,
    }
    _write_json(out_dir / "RUN_CONFIG.json", run_config)

    cases = build_cases("qualify" if is_qualify else suite)
    summaries: list[dict[str, Any]] = []
    menu_comparisons: list[dict[str, Any]] = []
    total_native_turns = 0
    total_parse_errors = 0

    for case in cases:
        arms_to_run = ["keep_r0", "keep_r1"]
        if not is_qualify and case.workflow == "forms":
            arms_to_run.append("keep_r2")
        arms_to_run.extend(["sham", "remove"])
        if case.workflow in {"forms", "medical_appointment"}:
            arms_to_run.append("archive")

        case_arms: dict[str, dict[str, Any]] = {}
        for arm in arms_to_run:
            ep = _execute_branch(
                case=case,
                interface="native",
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

        # Prefix-pinned fee_only fork derived from remove
        fee_ep = _execute_branch(
            case=case,
            interface="native",
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

        summary = summarize_case_audit(case, case_arms)
        summaries.append(summary)

        if args.with_menu and case.workflow == "forms":
            menu_arms: dict[str, dict[str, Any]] = {}
            for m_arm in ("keep_r0", "remove", "archive"):
                m_ep = _execute_branch(
                    case=case,
                    interface="menu",
                    arm=m_arm,
                    out_dir=out_dir,
                    base_url=args.base_url,
                    model=args.model,
                    api_key_env=args.api_key_env,
                    seed=_arm_seed(m_arm, args.seed),
                    temperature=args.temperature,
                    max_output_tokens=min(args.max_output_tokens, 256),
                    extra_body=extra_body,
                    endpoint_profile=args.endpoint_profile,
                    budget=budget,
                )
                menu_arms[m_arm] = m_ep
                print(
                    f"[{case.case_id()}][menu][{m_arm}] completed={m_ep.get('completed_count')}/4 "
                    f"spent={m_ep.get('budget_spent')} stop={m_ep.get('stop_reason')}",
                    flush=True,
                )
            menu_comparisons.append(
                {
                    "case_id": case.case_id(),
                    "native_keep_completed": case_arms["keep_r0"]["completed"],
                    "menu_keep_completed": menu_arms["keep_r0"]["completed"],
                    "native_remove_completed": case_arms["remove"]["completed"],
                    "menu_remove_completed": menu_arms["remove"]["completed"],
                    "native_archive_completed": case_arms["archive"]["completed"],
                    "menu_archive_completed": menu_arms["archive"]["completed"],
                    "keep_same_set": set(case_arms["keep_r0"]["completed"]) == set(menu_arms["keep_r0"]["completed"]),
                    "remove_same_set": set(case_arms["remove"]["completed"]) == set(menu_arms["remove"]["completed"]),
                }
            )

    _write_json(out_dir / "CASE_SUMMARIES.json", summaries)
    _write_summary_csv(out_dir / "SUMMARY_TABLE.csv", summaries)
    aggregate = _aggregate_reports(summaries)
    if menu_comparisons:
        aggregate["interface_sensitivity_menu_vs_native"] = menu_comparisons
    _write_json(out_dir / "AGGREGATE_REPORT.json", aggregate)

    if is_qualify:
        t11_keep0 = json.loads((out_dir / "forms-T11/native__keep_r0/EPISODE.json").read_text(encoding="utf-8"))
        t11_keep1 = json.loads((out_dir / "forms-T11/native__keep_r1/EPISODE.json").read_text(encoding="utf-8"))
        parse_err_rate = (total_parse_errors / total_native_turns) if total_native_turns else 1.0
        max_keep_comp = max(int(t11_keep0["completed_count"]), int(t11_keep1["completed_count"]))
        passed = (parse_err_rate <= 0.25) and (max_keep_comp >= 1) and bool(t11_keep0["grade_valid"])
        verdict = {
            "slot": args.slot,
            "model": args.model,
            "passed": passed,
            "verdict": "QUALIFIED" if passed else "DISQUALIFIED_INTERFACE",
            "total_native_turns": total_native_turns,
            "total_parse_errors": total_parse_errors,
            "parse_error_rate": round(parse_err_rate, 4),
            "keep_r0_completed": t11_keep0["completed_count"],
            "keep_r1_completed": t11_keep1["completed_count"],
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
    case_index = {c.case_id(): c for c in build_cases("all")}

    meta_files = sorted(run_dir.glob("*/*/BRANCH_META.json"))
    if not meta_files:
        raise RuntimeError(f"No recorded branches found under {run_dir}")

    # Replay non-fee_only arms first so fee_only can load replayed/recorded remove traces.
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
        interface = meta["interface"]
        arm = meta["arm"]

        if recorded_ep.get("status") != "ok":
            rows.append(
                {
                    "case_id": meta["case_id"],
                    "interface": interface,
                    "arm": arm,
                    "status": recorded_ep.get("status"),
                    "matched": True,
                }
            )
            continue

        tape_path = branch_dir / "model_calls.jsonl"
        replay_adapter = RecordedReplayAdapter(tape_path)
        fee_src = replayed_cache.get((meta["case_id"], "remove")) if arm == "fee_only" else None
        if interface == "native":
            replayed = run_native_episode(
                case,
                arm,
                replay_adapter,
                provider=meta["provider"],
                model=meta["model"],
                config_sha256=meta["config_sha256"],
                max_output_tokens=int(meta["max_output_tokens"]),
                fee_prefix_source=fee_src,
            )
        else:
            replayed = run_forms_menu_episode(
                case,
                arm,
                replay_adapter,
                provider=meta["provider"],
                model=meta["model"],
                config_sha256=meta["config_sha256"],
                max_output_tokens=int(meta["max_output_tokens"]),
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
                "interface": interface,
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
    print(f"Offline replay verification: {len(rows)} branches checked, {mismatches} mismatches.")
    if mismatches > 0:
        raise SystemExit(1)


def _add_model_args(parser: argparse.ArgumentParser, default_cap: int) -> None:
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:8000/v1")
    parser.add_argument("--model", required=True, help="Served model name")
    parser.add_argument("--slot", required=True, help="Model slot label (Q0, A, B, C, A_think)")
    parser.add_argument("--out", required=True, type=Path, help="Output directory")
    parser.add_argument("--api-key-env", default=None, help="Optional env var holding Bearer token")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--extra-body", default=None, help="Optional JSON object merged into request body")
    parser.add_argument("--endpoint-profile", default="modelscope_vllm_local")
    parser.add_argument("--with-menu", action="store_true", help="Also run Forms indexed-menu comparison")
    parser.add_argument("--call-cap", type=int, default=default_cap)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze", help="Generate/update P4_MODELSCOPE_FREEZE.json")
    p_freeze.add_argument("--out", type=Path, default=SCRIPT_DIR / "P4_MODELSCOPE_FREEZE.json")
    p_freeze.set_defaults(func=cmd_freeze)

    p_pack = sub.add_parser("pack", help="Pack portable ModelScope ZIP bundle")
    p_pack.add_argument("--out", type=Path, required=True)
    p_pack.set_defaults(func=cmd_pack)

    p_verify = sub.add_parser("verify-bundle", help="Verify unpacked bundle integrity and drivers")
    p_verify.set_defaults(func=cmd_verify_bundle)

    p_qual = sub.add_parser("qualify", help="Run Gate 1/Gate 2 qualification on forms T11")
    _add_model_args(p_qual, default_cap=150)
    p_qual.set_defaults(func=cmd_qualify)

    p_run = sub.add_parser("run", help="Run frozen native audit matrix")
    _add_model_args(p_run, default_cap=2000)
    p_run.add_argument("--suite", choices=("forms", "medical", "api", "released", "all"), default="all")
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("replay", help="Zero-GPU offline verification via RecordedReplayAdapter")
    p_rep.add_argument("--run-dir", type=Path, required=True)
    p_rep.add_argument("--out", type=Path, required=True)
    p_rep.set_defaults(func=cmd_replay)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
