"""Native tool-calling counterfactual spillover audit engine for ReScopeBench workflows.

Supports three clean, snapshot-restorable ReScopeBench workflows under NativeToolSurface:
  - forms (oracle_clinical_one_data_collection, 3 native tools, budget 17, T11-T16)
  - medical_appointment (4 native tools, budget 72, T11-T16)
  - api_reliability (5 native tools, budget 57, T09-T16)

Also provides same-exact-weight Forms menu-interface execution for controlled
menu-vs-native interface sensitivity comparisons, prefix-pinned fee-only counterfactual
forking, and deterministic offline replay verification via RecordedReplayAdapter.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import importlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from unittest.mock import patch

from .contracts import (
    JsonObject,
    ModelAdapter,
    ModelTurnRequest,
    NativeToolSurface,
    ToolSpec,
)
from .openai_compatible import canonical_json


_ACTIVE_RESCOPE_ROOT: str | None = None


def _digest(data: Any) -> str:
    return sha256(canonical_json(data).encode("utf-8")).hexdigest()


def _cell(*parts: Any) -> str:
    return json.dumps(list(parts), separators=(",", ":"))


def _nonaccounting(reply: JsonObject) -> JsonObject:
    content = reply.get("content", reply)
    if not isinstance(content, dict):
        return {"value": content}
    return {k: v for k, v in content.items() if k not in {"budget", "receipt_index"}}


def _extract_reply_content(reply: JsonObject) -> JsonObject:
    content = reply.get("content", reply)
    return content if isinstance(content, dict) else {"value": content}


def _extract_budget(reply: JsonObject, world: Any, before_balance: int) -> tuple[int, int]:
    accounting = reply.get("budget")
    if not isinstance(accounting, dict):
        accounting = _extract_reply_content(reply).get("budget")
    if isinstance(accounting, dict) and "charged" in accounting and "remaining" in accounting:
        charged = int(accounting["charged"])
        remaining = int(accounting["remaining"])
        return charged, remaining
    if hasattr(world, "remaining"):
        remaining = int(world.remaining)
        return before_balance - remaining, remaining
    if hasattr(world, "_remaining"):
        remaining = int(world._remaining)
        return before_balance - remaining, remaining
    raise RuntimeError("Could not read native budget accounting from reply or world")


def load_rescopebench_driver(workflow: str, source_root: Path):
    """Import a pinned ReScopeBench workflow driver with clean module isolation."""
    global _ACTIVE_RESCOPE_ROOT
    resolved = str(Path(source_root).resolve())
    if _ACTIVE_RESCOPE_ROOT != resolved:
        for mod_name in [
            name for name in list(sys.modules)
            if name == "rescopebench" or name.startswith("rescopebench.")
        ]:
            del sys.modules[mod_name]
        if resolved in sys.path:
            sys.path.remove(resolved)
        sys.path.insert(0, resolved)
        _ACTIVE_RESCOPE_ROOT = resolved

    if workflow == "forms":
        mod = importlib.import_module("rescopebench.cases.oracle_clinical_one_data_collection.driver")
        runtime = importlib.import_module("rescopebench.cases.oracle_clinical_one_data_collection.runtime")
        return mod.Driver(), runtime
    if workflow == "medical_appointment":
        mod = importlib.import_module("rescopebench.cases.medical_appointment.driver")
        return mod.Driver(), None
    if workflow == "api_reliability":
        mod = importlib.import_module("rescopebench.cases.api_reliability.driver")
        return mod.ApiReliabilityDriver(), None
    raise ValueError(f"Unsupported workflow: {workflow}")


@dataclass(frozen=True)
class AuditCase:
    workflow: str
    day: int
    focal_key: str
    sham_key: str | None
    direct_targets: tuple[str, ...]
    opening_world_path: Path
    opening_memory_path: Path | None  # None when combined in checkpoint JSON
    source_root: Path
    upstream_release_status: str

    def case_id(self) -> str:
        return f"{self.workflow}-T{self.day:02d}"


def load_opening_snapshot(case: AuditCase) -> tuple[JsonObject, JsonObject]:
    """Load frozen opening (world_state, memory_state) without mutating source files."""
    if case.opening_memory_path is not None:
        world_state = json.loads(case.opening_world_path.read_text(encoding="utf-8"))
        memory_state = json.loads(case.opening_memory_path.read_text(encoding="utf-8"))
        return world_state, memory_state
    combined = json.loads(case.opening_world_path.read_text(encoding="utf-8"))
    return deepcopy(combined["state"]), deepcopy(combined["memory"])


def parse_task_targets(workflow: str, task: JsonObject) -> list[JsonObject]:
    public = task["query"]
    if public.lstrip().startswith("{"):
        return json.loads(public)["targets"]
    use = public.split("Requested artifacts:", 1)[1].lstrip()
    return json.JSONDecoder().raw_decode(use)[0]


def target_id_field(workflow: str) -> str:
    if workflow == "forms":
        return "record_ref"
    if workflow == "medical_appointment":
        return "patient_id"
    if workflow == "api_reliability":
        return "call_id"
    raise ValueError(f"Unsupported workflow: {workflow}")


def workflow_tool_costs(workflow: str) -> dict[str, int]:
    if workflow == "forms":
        return {
            "get_correction_context": 5,
            "get_correction_policy": 3,
            "apply_form_correction": 2,
        }
    if workflow == "medical_appointment":
        return {
            "get_patient_scheduling_context": 16,
            "get_follow_up_policy": 10,
            "search_appointment_slots": 6,
            "create_follow_up_appointment": 8,
        }
    if workflow == "api_reliability":
        return {
            "list_api_credentials": 3,
            "list_retry_budgets": 3,
            "inspect_rate_limit_status": 3,
            "search_recovery_evidence": 17,
            "retry_api_call": 10,
        }
    raise ValueError(f"Unsupported workflow: {workflow}")


def focal_reread_tool(workflow: str) -> str:
    if workflow == "forms":
        return "get_correction_context"
    if workflow == "medical_appointment":
        return "get_patient_scheduling_context"
    if workflow == "api_reliability":
        return "search_recovery_evidence"
    raise ValueError(f"Unsupported workflow: {workflow}")


def write_tool_name(workflow: str) -> str:
    if workflow == "forms":
        return "apply_form_correction"
    if workflow == "medical_appointment":
        return "create_follow_up_appointment"
    if workflow == "api_reliability":
        return "retry_api_call"
    raise ValueError(f"Unsupported workflow: {workflow}")


def extract_native_tool_specs(workflow: str, driver: Any, world: Any, include_archive: bool) -> tuple[ToolSpec, ...]:
    raw_tools = world.public_tool_schemas() if workflow == "forms" else driver.tools
    specs: list[ToolSpec] = []
    for item in raw_tools:
        fn = item["function"] if "function" in item else item
        schema = deepcopy(fn.get("parameters") or fn.get("input_schema"))
        specs.append(
            ToolSpec(
                name=fn["name"],
                description=fn["description"],
                json_schema=schema,
            )
        )
    if include_archive:
        specs.append(
            ToolSpec(
                name="lookup_archive",
                description=(
                    "Retrieve a previously stored historical receipt from the content-addressed "
                    "local archive at zero business work-unit cost. Provide the exact receipt_key."
                ),
                json_schema={
                    "type": "object",
                    "properties": {
                        "receipt_key": {
                            "type": "string",
                            "description": "Exact key of the archived historical receipt to restore.",
                        }
                    },
                    "required": ["receipt_key"],
                    "additionalProperties": False,
                },
            )
        )
    specs.append(
        ToolSpec(
            name="finish_session",
            description=(
                "Finish the current session when all feasible targets are complete or no "
                "remaining beneficial action can be funded. Costs 0 work units."
            ),
            json_schema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        )
    )
    return tuple(specs)


def _remove_receipt_from_memory(workflow: str, memory: JsonObject, key: str) -> Any:
    if workflow == "forms":
        return memory["bindings"].pop(key)
    return memory["receipts"].pop(key)


def _get_prior_receipt(workflow: str, memory: JsonObject, key: str) -> Any:
    if workflow == "forms":
        return deepcopy(memory["bindings"][key])
    return deepcopy(memory["receipts"][key])


def _build_archive_store(workflow: str, full_memory: JsonObject) -> dict[str, JsonObject]:
    """Content-addressed local archive over opening receipts."""
    source = full_memory["bindings"] if workflow == "forms" else full_memory["receipts"]
    store: dict[str, JsonObject] = {}
    for key, value in sorted(source.items()):
        body = canonical_json(value).encode("utf-8")
        address = sha256(body).hexdigest()
        store[key] = {"digest": address, "bytes": len(body), "value": deepcopy(value)}
    return store


def _resolve_archive_key(workflow: str, archive_store: dict[str, JsonObject], raw_key: str) -> str | None:
    if raw_key in archive_store:
        return raw_key
    if workflow == "medical_appointment":
        candidate = _cell(raw_key)
        if candidate in archive_store:
            return candidate
    if workflow == "api_reliability":
        if "|" in raw_key:
            parts = [p.strip() for p in raw_key.split("|", 1)]
            candidate = _cell(*parts)
            if candidate in archive_store:
                return candidate
        if "," in raw_key and not raw_key.lstrip().startswith("["):
            parts = [p.strip() for p in raw_key.split(",", 1)]
            candidate = _cell(*parts)
            if candidate in archive_store:
                return candidate
    return None


def _matches_focal_reread(
    workflow: str,
    tool_name: str,
    args: JsonObject,
    reply: JsonObject,
    focal_key: str,
    prior_receipt: Any,
) -> bool:
    if tool_name != focal_reread_tool(workflow):
        return False
    content = _extract_reply_content(reply)
    if content.get("status") != "success":
        return False
    data = content.get("data") or {}
    if workflow == "forms":
        if args.get("record_ref") != focal_key:
            return False
        fields = ("record_ref", "correction_handle", "visit_type", "binding_scope")
        projected = {k: data.get(k) for k in fields}
        return projected == prior_receipt["fields"]
    if workflow == "medical_appointment":
        if _cell(args.get("patient_id")) != focal_key:
            return False
        fields = ("care_tier", "home_site_id", "source_appointment_id", "source_practitioner_id", "source_specialty")
        projected = {k: data.get(k) for k in fields}
        return projected == prior_receipt
    if workflow == "api_reliability":
        if _cell(args.get("failure_signal"), args.get("operation_class")) != focal_key:
            return False
        evidence = data.get("evidence") or []
        if not evidence:
            return False
        projected = {"profile": evidence[0].get("recovery_profile_id")}
        return projected == prior_receipt
    return False


def _call_native_tool(
    workflow: str,
    driver: Any,
    runtime: Any,
    world: Any,
    tool_name: str,
    args: JsonObject,
    *,
    waive_cost: bool = False,
) -> JsonObject:
    if not waive_cost:
        return driver.call(world, tool_name, args)
    if workflow == "forms":
        assert runtime is not None
        with patch.dict(runtime.DATA_TOOL_COSTS, {tool_name: 0}):
            return driver.call(world, tool_name, args)
    old_cost = world._cost

    def zero_cost(*pos, **kwargs):
        price = old_cost(*pos, **kwargs)
        if pos and pos[0] == tool_name and isinstance(price, int):
            return 0
        return price

    with patch.object(world, "_cost", side_effect=zero_cost):
        return driver.call(world, tool_name, args)


def _infer_target_for_call(
    workflow: str,
    tool_name: str,
    args: JsonObject,
    targets: list[JsonObject],
    opening_memory: JsonObject,
    observed_handles: dict[str, str],
) -> str | None:
    if workflow == "forms":
        if tool_name == "get_correction_context":
            return args.get("record_ref")
        if tool_name == "apply_form_correction":
            handle = args.get("correction_handle")
            if handle in observed_handles:
                return observed_handles[handle]
            for ref, entry in opening_memory.get("bindings", {}).items():
                if entry.get("fields", {}).get("correction_handle") == handle:
                    return ref
            return None
        if tool_name == "get_correction_policy":
            vt = args.get("visit_type")
            cc = args.get("correction_class")
            matches = []
            for t in targets:
                ref = t["record_ref"]
                if t["correction_class"] != cc:
                    continue
                b = opening_memory.get("bindings", {}).get(ref)
                if b and b.get("fields", {}).get("visit_type") == vt:
                    matches.append(ref)
            return matches[0] if len(matches) == 1 else (matches[0] if matches else None)
    if workflow == "medical_appointment":
        if tool_name == "get_patient_scheduling_context":
            return args.get("patient_id")
        if tool_name == "create_follow_up_appointment":
            src_appt = args.get("source_appointment_id")
            if src_appt in observed_handles:
                return observed_handles[src_appt]
            for key, rec in opening_memory.get("receipts", {}).items():
                if rec.get("source_appointment_id") == src_appt:
                    return json.loads(key)[0]
            return None
        if tool_name == "search_appointment_slots":
            site = args.get("site_id")
            date = args.get("start_date")
            for t in targets:
                if t.get("requested_date") != date:
                    continue
                rec = opening_memory.get("receipts", {}).get(_cell(t["patient_id"]))
                if rec and rec.get("home_site_id") == site:
                    return t["patient_id"]
            return None
        if tool_name == "get_follow_up_policy":
            ct, rc = args.get("care_tier"), args.get("request_class")
            for t in targets:
                if t.get("request_class") != rc:
                    continue
                rec = opening_memory.get("receipts", {}).get(_cell(t["patient_id"]))
                if rec and rec.get("care_tier") == ct:
                    return t["patient_id"]
            return None
    if workflow == "api_reliability":
        if tool_name == "retry_api_call":
            return args.get("call_id")
        if tool_name in {"list_api_credentials", "list_retry_budgets", "inspect_rate_limit_status"}:
            iid = args.get("integration_id")
            op = args.get("operation") or args.get("scope_contains")
            for t in targets:
                if t.get("integration_id") == iid and (op is None or t.get("operation") == op):
                    return t["call_id"]
            for t in targets:
                if t.get("integration_id") == iid:
                    return t["call_id"]
            return None
        if tool_name == "search_recovery_evidence":
            fs, oc = args.get("failure_signal"), args.get("operation_class")
            for t in targets:
                if t.get("failure_signal") == fs and t.get("operation_class") == oc:
                    return t["call_id"]
            return None
    return None


def _update_observed_handles(
    workflow: str,
    tool_name: str,
    args: JsonObject,
    reply: JsonObject,
    observed_handles: dict[str, str],
) -> None:
    content = _extract_reply_content(reply)
    if content.get("status") != "success":
        return
    data = content.get("data") or {}
    if workflow == "forms" and tool_name == "get_correction_context":
        handle = data.get("correction_handle")
        ref = data.get("record_ref") or args.get("record_ref")
        if handle and ref:
            observed_handles[handle] = ref
    elif workflow == "medical_appointment" and tool_name == "get_patient_scheduling_context":
        src_appt = data.get("source_appointment_id")
        pid = args.get("patient_id")
        if src_appt and pid:
            observed_handles[src_appt] = pid


def build_native_system_prompt(workflow: str, include_archive: bool) -> str:
    archive_clause = (
        " If a needed historical receipt is missing from active memory, you may call "
        "`lookup_archive` (cost 0 work units) before paying for a live read tool."
        if include_archive
        else ""
    )
    return (
        f"You are operating the native `{workflow}` workflow simulator under a shared "
        "work-unit budget. Your objective is to maximize the number of legally completed "
        "requested targets within the remaining budget. Independent targets may be handled "
        "in any order; an unfinished target does not block other targets. Make exactly ONE "
        "tool call per turn. Previously saved cross-session receipts in active memory may "
        "save read cost, though rules or policies may have drifted since earlier sessions; "
        "live tool responses are authoritative when a write is rejected. Do not repeat a "
        "write call with identical arguments after it is rejected."
        + archive_clause
        + " Call `finish_session` when all feasible targets are complete or no remaining "
        "beneficial action can be funded."
    )


def build_opening_user_payload(
    workflow: str,
    day: int,
    task: JsonObject,
    balance: int,
    active_memory: JsonObject,
    archive_keys: list[str] | None,
) -> JsonObject:
    targets = parse_task_targets(workflow, task)
    payload: JsonObject = {
        "workflow": workflow,
        "session": f"T{day:02d}",
        "remaining_budget": balance,
        "tool_costs": workflow_tool_costs(workflow),
        "task_instructions": task["query"],
        "requested_targets": targets,
        "active_memory": active_memory,
    }
    if archive_keys is not None:
        payload["available_archive_keys"] = sorted(archive_keys)
    return payload


def _grade_completed_targets(workflow: str, grade: JsonObject) -> list[str]:
    if workflow == "forms":
        return [row["record_ref"] for row in grade["artifacts"] if row.get("complete")]
    if workflow == "medical_appointment":
        return [row["patient_id"] for row in grade["artifacts"] if row.get("complete")]
    if workflow == "api_reliability":
        return [row["call_id"] for row in grade["targets"] if row.get("complete")]
    raise ValueError(f"Unsupported workflow: {workflow}")


def _extract_dispatch_order(native_log: list[JsonObject]) -> list[str]:
    order: list[str] = []
    for row in native_log:
        tgt = row.get("inferred_target")
        if tgt and tgt not in order:
            order.append(tgt)
    return order


def run_native_episode(
    case: AuditCase,
    arm: str,
    adapter: ModelAdapter,
    *,
    provider: str,
    model: str,
    config_sha256: str,
    max_output_tokens: int = 256,
    max_steps: int | None = None,
    max_consecutive_errors: int = 4,
    fee_prefix_source: JsonObject | None = None,
) -> JsonObject:
    """Execute one native tool-calling episode from the frozen opening snapshot.

    Supported arms:
      - 'keep' (or 'keep_r0', 'keep_r1', ...): full opening memory
      - 'sham': remove frozen non-target sham_key from opening memory
      - 'remove': remove frozen focal_key from opening memory
      - 'archive': remove focal_key from active memory, expose zero-cost lookup_archive
      - 'fee_only': prefix-pinned post-charge counterfactual fork derived from remove trace
    """
    started_ns = time.perf_counter_ns()
    driver, runtime = load_rescopebench_driver(case.workflow, case.source_root)
    world_state, full_memory = load_opening_snapshot(case)
    opening_memory = deepcopy(full_memory)
    prior_focal = _get_prior_receipt(case.workflow, full_memory, case.focal_key)

    include_archive = arm == "archive"
    archive_store = _build_archive_store(case.workflow, full_memory) if include_archive else None

    if arm.startswith("keep"):
        pass
    elif arm == "sham":
        if case.sham_key is None:
            return {
                "case_id": case.case_id(),
                "workflow": case.workflow,
                "day": case.day,
                "arm": arm,
                "status": "ineligible_no_sham_key",
            }
        _remove_receipt_from_memory(case.workflow, opening_memory, case.sham_key)
    elif arm in {"remove", "archive", "fee_only"}:
        _remove_receipt_from_memory(case.workflow, opening_memory, case.focal_key)
    else:
        raise ValueError(f"Unknown arm: {arm}")

    # Validate fee_only eligibility BEFORE touching the model!
    pin_prefix_steps: list[JsonObject] = []
    waive_at_native_index: int | None = None
    expected_waived_nonaccounting: JsonObject | None = None
    if arm == "fee_only":
        if fee_prefix_source is None:
            raise ValueError("fee_only arm requires fee_prefix_source (completed remove episode)")
        reread = fee_prefix_source.get("same_value_reread")
        if not reread:
            return {
                "case_id": case.case_id(),
                "workflow": case.workflow,
                "day": case.day,
                "arm": arm,
                "status": "ineligible_no_same_value_reread",
            }
        waive_at_native_index = int(reread["native_call_index"])
        expected_waived_nonaccounting = reread["nonaccounting"]
        pin_prefix_steps = [
            step for step in fee_prefix_source["turns"]
            if step.get("native_call_index") is not None and step["native_call_index"] <= waive_at_native_index
        ]

    world = driver.create_world()
    try:
        world.restore(world_state)
        task = driver.tasks[case.day - 1]
        begin_info = driver.begin(world, task)
        if case.workflow == "forms":
            initial_balance = int(begin_info["allowance"])
        else:
            initial_balance = int(world.remaining if hasattr(world, "remaining") else world._remaining)
        balance = initial_balance

        targets = parse_task_targets(case.workflow, task)
        tools = extract_native_tool_specs(case.workflow, driver, world, include_archive=include_archive)
        system_prompt = build_native_system_prompt(case.workflow, include_archive=include_archive)
        archive_keys = sorted(archive_store) if archive_store is not None else None
        user_payload = build_opening_user_payload(
            case.workflow, case.day, task, balance, opening_memory, archive_keys
        )
        messages: list[JsonObject] = [{"role": "user", "content": user_payload}]

        surface = NativeToolSurface()
        step_cap = max_steps or (16 if case.workflow == "forms" else (18 if case.workflow == "medical_appointment" else 24))
        turns: list[JsonObject] = []
        native_log: list[JsonObject] = []
        observed_handles: dict[str, str] = {}
        seen_rejected_writes: set[str] = set()
        same_value_reread: JsonObject | None = None
        prefix_replayed_calls = 0
        waived_cost = 0
        nonaccounting_match: bool | None = None

        model_calls = 0
        archive_lookups = 0
        write_rejections = 0
        repeated_known_rejections = 0
        unaffordable_attempts = 0
        invalid_arg_errors = 0
        parse_errors: list[str] = []
        truncated_turns = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_reasoning_tokens = 0
        consecutive_errors = 0
        stop_reason = "step_limit"

        # Phase A (fee_only only): deterministically replay remove's exact prefix up to and
        # including the waived same-value re-read call, verifying exact prefix & content match!
        if arm == "fee_only":
            for src_turn in pin_prefix_steps:
                call_id = src_turn["call_id"]
                tool_name = src_turn["tool_name"]
                args = deepcopy(src_turn["arguments"])
                args_raw = src_turn["arguments_raw"]
                assistant_text = src_turn.get("assistant_text", "")
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_text,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": args_raw},
                            }
                        ],
                    }
                )
                native_index = len(native_log) + 1
                is_waived = native_index == waive_at_native_index
                before_balance = balance
                reply = _call_native_tool(
                    case.workflow, driver, runtime, world, tool_name, args, waive_cost=is_waived
                )
                charged, new_balance = _extract_budget(reply, world, before_balance)
                assert before_balance - charged == new_balance
                balance = new_balance
                if is_waived:
                    assert charged == 0, f"Expected waived cost 0, got {charged}"
                    nonaccounting_match = _nonaccounting(reply) == expected_waived_nonaccounting
                    assert nonaccounting_match, "Waived tool response content diverged from remove trace"
                    waived_cost = int(fee_prefix_source["same_value_reread"]["cost"])
                else:
                    assert _nonaccounting(reply) == src_turn["nonaccounting"], (
                        f"Prefix step {native_index} diverged before waiver"
                    )
                prefix_replayed_calls += 1
                _update_observed_handles(case.workflow, tool_name, args, reply, observed_handles)
                inferred_target = _infer_target_for_call(
                    case.workflow, tool_name, args, targets, opening_memory, observed_handles
                )
                content = _extract_reply_content(reply)
                if tool_name == write_tool_name(case.workflow) and content.get("status") != "success":
                    write_rejections += 1
                    sig = _digest({"tool": tool_name, "args": args})
                    if sig in seen_rejected_writes:
                        repeated_known_rejections += 1
                    seen_rejected_writes.add(sig)
                native_entry = {
                    "native_call_index": native_index,
                    "tool": tool_name,
                    "arguments": args,
                    "charged": charged,
                    "balance_before": before_balance,
                    "remaining_budget": balance,
                    "status": content.get("status"),
                    "error_code": content.get("error_code") or content.get("code"),
                    "inferred_target": inferred_target,
                    "waived_charge": is_waived,
                    "replayed_prefix": True,
                }
                native_log.append(native_entry)
                tool_msg_payload = {
                    "tool": tool_name,
                    "content": content,
                    "charged": charged,
                    "remaining_budget": balance,
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": json.dumps(tool_msg_payload, ensure_ascii=False, sort_keys=True),
                    }
                )
                turns.append(
                    {
                        "turn": len(turns),
                        "replayed_prefix": True,
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "arguments": args,
                        "arguments_raw": args_raw,
                        "assistant_text": assistant_text,
                        "native_call_index": native_index,
                        "charged": charged,
                        "remaining_budget": balance,
                        "nonaccounting": _nonaccounting(reply),
                        "waived_charge": is_waived,
                    }
                )

        # Phase B: live (or recorded-replay) LLM turns
        for step in range(len(turns), step_cap):
            req = ModelTurnRequest(
                request_id=f"{case.case_id()}:{arm}:turn-{step:02d}",
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                messages=tuple(deepcopy(messages)),
                tools=tools,
                tool_choice="required",
                max_output_tokens=max_output_tokens,
                config_sha256=config_sha256,
            )
            resp = adapter.complete(req)
            model_calls += 1
            if resp.usage.get("input_tokens") is not None:
                total_input_tokens += int(resp.usage["input_tokens"])
            if resp.usage.get("output_tokens") is not None:
                total_output_tokens += int(resp.usage["output_tokens"])
            if resp.usage.get("reasoning_tokens") is not None:
                total_reasoning_tokens += int(resp.usage["reasoning_tokens"])

            parsed = surface.parse(req, resp)
            if parsed.error is not None:
                parse_errors.append(parsed.error)
                if parsed.error == "truncated_turn":
                    truncated_turns += 1
                turns.append(
                    {
                        "turn": step,
                        "replayed_prefix": False,
                        "request_sha256": req.fingerprint(),
                        "parse_error": parsed.error,
                        "finish_reason": resp.finish_reason,
                        "assistant_text": resp.text_output,
                        "remaining_budget": balance,
                    }
                )
                stop_reason = f"parse_error:{parsed.error}"
                break

            assert parsed.call is not None and parsed.arguments is not None
            call = parsed.call
            args = parsed.arguments
            messages.append(
                {
                    "role": "assistant",
                    "content": resp.text_output,
                    "tool_calls": [
                        {
                            "id": call.call_id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments_raw},
                        }
                    ],
                }
            )

            if call.name == "finish_session":
                turns.append(
                    {
                        "turn": step,
                        "replayed_prefix": False,
                        "request_sha256": req.fingerprint(),
                        "call_id": call.call_id,
                        "tool_name": call.name,
                        "arguments": args,
                        "arguments_raw": call.arguments_raw,
                        "assistant_text": resp.text_output,
                        "remaining_budget": balance,
                    }
                )
                stop_reason = "model_finish_session"
                break

            if call.name == "lookup_archive":
                archive_lookups += 1
                raw_key = str(args.get("receipt_key", ""))
                resolved_key = _resolve_archive_key(case.workflow, archive_store or {}, raw_key)
                if resolved_key is None:
                    archive_reply: JsonObject = {
                        "status": "not_found",
                        "receipt_key": raw_key,
                        "available_keys": sorted(archive_store or {}),
                    }
                    consecutive_errors += 1
                else:
                    entry = (archive_store or {})[resolved_key]
                    # Verify content address before returning!
                    assert sha256(canonical_json(entry["value"]).encode("utf-8")).hexdigest() == entry["digest"]
                    archive_reply = {
                        "status": "success",
                        "receipt_key": resolved_key,
                        "digest": entry["digest"],
                        "bytes": entry["bytes"],
                        "receipt": entry["value"],
                        "charged": 0,
                        "remaining_budget": balance,
                    }
                    consecutive_errors = 0
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "name": call.name,
                        "content": json.dumps(archive_reply, ensure_ascii=False, sort_keys=True),
                    }
                )
                turns.append(
                    {
                        "turn": step,
                        "replayed_prefix": False,
                        "request_sha256": req.fingerprint(),
                        "call_id": call.call_id,
                        "tool_name": call.name,
                        "arguments": args,
                        "arguments_raw": call.arguments_raw,
                        "assistant_text": resp.text_output,
                        "archive_lookup": archive_reply,
                        "remaining_budget": balance,
                    }
                )
                if consecutive_errors >= max_consecutive_errors:
                    stop_reason = "consecutive_error_limit"
                    break
                continue

            # Native business tool execution
            before_balance = balance
            native_index = len(native_log) + 1
            reply = _call_native_tool(case.workflow, driver, runtime, world, call.name, args, waive_cost=False)
            charged, new_balance = _extract_budget(reply, world, before_balance)
            assert before_balance - charged == new_balance
            balance = new_balance
            content = _extract_reply_content(reply)
            status = content.get("status")
            error_code = content.get("error_code") or content.get("code")
            _update_observed_handles(case.workflow, call.name, args, reply, observed_handles)
            inferred_target = _infer_target_for_call(
                case.workflow, call.name, args, targets, opening_memory, observed_handles
            )

            if status == "success":
                consecutive_errors = 0
            else:
                err_upper = str(error_code or "").upper()
                if "BUDGET" in err_upper or "ALLOWANCE" in err_upper or "QUOTA" in err_upper:
                    unaffordable_attempts += 1
                elif "INVALID" in err_upper:
                    invalid_arg_errors += 1
                if call.name == write_tool_name(case.workflow):
                    write_rejections += 1
                    sig = _digest({"tool": call.name, "args": args})
                    if sig in seen_rejected_writes:
                        repeated_known_rejections += 1
                    seen_rejected_writes.add(sig)
                consecutive_errors += 1

            is_same_val = (
                arm == "remove"
                and same_value_reread is None
                and charged > 0
                and _matches_focal_reread(case.workflow, call.name, args, reply, case.focal_key, prior_focal)
            )
            if is_same_val:
                same_value_reread = {
                    "native_call_index": native_index,
                    "turn": step,
                    "tool": call.name,
                    "arguments": args,
                    "cost": charged,
                    "receipt_key": case.focal_key,
                    "nonaccounting": _nonaccounting(reply),
                    "nonaccounting_sha256": _digest(_nonaccounting(reply)),
                }

            native_entry = {
                "native_call_index": native_index,
                "tool": call.name,
                "arguments": args,
                "charged": charged,
                "balance_before": before_balance,
                "remaining_budget": balance,
                "status": status,
                "error_code": error_code,
                "inferred_target": inferred_target,
                "waived_charge": False,
                "replayed_prefix": False,
            }
            native_log.append(native_entry)
            tool_msg_payload = {
                "tool": call.name,
                "content": content,
                "charged": charged,
                "remaining_budget": balance,
            }
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "name": call.name,
                    "content": json.dumps(tool_msg_payload, ensure_ascii=False, sort_keys=True),
                }
            )
            turns.append(
                {
                    "turn": step,
                    "replayed_prefix": False,
                    "request_sha256": req.fingerprint(),
                    "call_id": call.call_id,
                    "tool_name": call.name,
                    "arguments": args,
                    "arguments_raw": call.arguments_raw,
                    "assistant_text": resp.text_output,
                    "native_call_index": native_index,
                    "charged": charged,
                    "remaining_budget": balance,
                    "status": status,
                    "error_code": error_code,
                    "nonaccounting": _nonaccounting(reply),
                }
            )
            if consecutive_errors >= max_consecutive_errors:
                stop_reason = "consecutive_error_limit"
                break

        grade = driver.grade(world, task)
        completed = sorted(_grade_completed_targets(case.workflow, grade))
        dispatch_order = _extract_dispatch_order(native_log)
        wall_ms = round((time.perf_counter_ns() - started_ns) / 1_000_000.0, 3)

        return {
            "case_id": case.case_id(),
            "workflow": case.workflow,
            "day": case.day,
            "arm": arm,
            "interface": "native_tool_calling",
            "status": "ok",
            "focal_key": case.focal_key,
            "sham_key": case.sham_key,
            "direct_targets": list(case.direct_targets),
            "initial_budget": initial_balance,
            "budget_spent": initial_balance - balance,
            "remaining_budget": balance,
            "completed": completed,
            "completed_count": len(completed),
            "total_targets": len(targets),
            "grade_valid": grade.get("valid", True),
            "grade_score": grade.get("score"),
            "dispatch_order": dispatch_order,
            "first_target": dispatch_order[0] if dispatch_order else None,
            "same_value_reread": same_value_reread,
            "fee_only_control": (
                {
                    "prefix_replayed_calls": prefix_replayed_calls,
                    "waived_at_native_index": waive_at_native_index,
                    "waived_cost": waived_cost,
                    "nonaccounting_match": nonaccounting_match,
                }
                if arm == "fee_only"
                else None
            ),
            "stop_reason": stop_reason,
            "model_calls": model_calls,
            "native_calls": len(native_log),
            "archive_lookups": archive_lookups,
            "write_rejections": write_rejections,
            "repeated_known_rejections": repeated_known_rejections,
            "unaffordable_attempts": unaffordable_attempts,
            "invalid_arg_errors": invalid_arg_errors,
            "parse_errors": parse_errors,
            "truncated_turns": truncated_turns,
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "reasoning": total_reasoning_tokens,
            },
            "wall_ms": wall_ms,
            "native_log": native_log,
            "turns": turns,
        }
    finally:
        if hasattr(world, "close"):
            world.close()


_FORMS_MENU_SYSTEM = (
    "You operate a synthetic form-correction simulator. Maximize the number of properly "
    "saved requested corrections within the work budget. Choose one menu entry by returning "
    'a JSON object {"choice": N}. Only a successful apply completes a target. Use an archive '
    "receipt for a known stable form binding; a context read costs work. Recorded policy "
    "candidates are evidence, not guarantees of current validity. Explicit earlier mismatch "
    "for the same visit and correction class indicates that profile was rejected. If uncertain "
    "about policy, decide whether a current policy read is worthwhile. The budget is shared "
    "across targets. Stop when no useful work remains. The menu contains action, target index, "
    "cost, and profile where applicable. No additional text."
)


def _parse_menu_choice(text: str) -> int | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and type(parsed.get("choice")) is int:
            return parsed["choice"]
    except ValueError:
        pass
    match = re.search(r'"choice"\s*:\s*(\d+)', stripped)
    return int(match.group(1)) if match else None


def run_forms_menu_episode(
    case: AuditCase,
    arm: str,
    adapter: ModelAdapter,
    *,
    provider: str,
    model: str,
    config_sha256: str,
    max_output_tokens: int = 128,
    max_steps: int = 12,
) -> JsonObject:
    """Run the frozen P0 indexed-menu interface on Forms using the same ModelAdapter.

    Enables controlled same-exact-weight `menu` vs `native_tool_calling` sensitivity comparisons
    on identical opening snapshots.
    """
    if case.workflow != "forms":
        raise ValueError("run_forms_menu_episode is defined only for forms")
    started_ns = time.perf_counter_ns()
    driver, _ = load_rescopebench_driver("forms", case.source_root)
    world_state, full_memory = load_opening_snapshot(case)
    opening_memory = deepcopy(full_memory)
    include_archive = arm == "archive"
    archive_store = _build_archive_store("forms", full_memory) if include_archive else {}

    if arm.startswith("keep"):
        pass
    elif arm == "sham":
        if case.sham_key is None:
            return {"case_id": case.case_id(), "workflow": "forms", "day": case.day, "arm": arm, "status": "ineligible_no_sham_key"}
        opening_memory["bindings"].pop(case.sham_key)
    elif arm in {"remove", "archive"}:
        opening_memory["bindings"].pop(case.focal_key)
    else:
        raise ValueError(f"Unsupported menu arm: {arm}")

    world = driver.create_world()
    try:
        world.restore(world_state)
        task = driver.tasks[case.day - 1]
        start = driver.begin(world, task)
        balance = int(start["allowance"])
        targets = parse_task_targets("forms", task)
        pending = set(range(len(targets)))
        active = deepcopy(opening_memory["bindings"])
        policies = deepcopy(opening_memory["policies"])
        rejected = deepcopy(opening_memory["rejected"])
        verified = deepcopy(opening_memory["verified"])
        history: list[JsonObject] = []
        native_log: list[JsonObject] = []
        model_calls = 0
        archive_lookups = 0
        write_rejections = 0
        repeated_known_rejections = 0
        parse_errors: list[str] = []
        truncated_turns = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_reasoning_tokens = 0
        stop_reason = "step_limit"

        for step in range(max_steps):
            if not pending:
                stop_reason = "all_committed"
                break
            if balance < 2:
                stop_reason = "insufficient_business_balance"
                break
            entries, public_targets = [], []
            for idx in sorted(pending):
                t = targets[idx]
                ref, kind = t["record_ref"], t["correction_class"]
                binding = active.get(ref)
                item = {
                    "target": idx + 1,
                    "record": ref,
                    "correction_class": kind,
                    "active_binding": bool(binding),
                    "stored_binding": ref in archive_store,
                }
                public_targets.append(item)
                if not binding:
                    if balance >= 5:
                        entries.append({"action": "read_context", "target": idx + 1, "cost": 5})
                    if ref in archive_store:
                        entries.append({"action": "lookup_archive", "target": idx + 1, "cost": 0})
                    continue
                visit = binding["fields"]["visit_type"]
                scope = f"{visit}|{kind}"
                rej = rejected.get(scope, [])
                cands = policies.get(scope, [])
                item.update(
                    visit_type=visit,
                    observed_profiles=cands,
                    previously_rejected_profiles=rej,
                    last_verified=verified.get(scope),
                )
                if balance >= 3:
                    entries.append({"action": "read_policy", "target": idx + 1, "cost": 3})
                if balance >= 2:
                    for profile in cands:
                        entries.append({"action": "apply", "target": idx + 1, "profile": profile, "cost": 2})

            if not entries:
                stop_reason = "no_available_action"
                break
            offering = [{"action": "stop", "cost": 0}, *entries]
            req_payload = {
                "session": case.day,
                "balance": balance,
                "targets": public_targets,
                "menu": [{"choice": i, **row} for i, row in enumerate(offering)],
                "last_actions": history[-2:],
            }
            req = ModelTurnRequest(
                request_id=f"{case.case_id()}:menu:{arm}:turn-{step:02d}",
                provider=provider,
                model=model,
                system_prompt=_FORMS_MENU_SYSTEM,
                messages=({"role": "user", "content": req_payload},),
                tools=(),
                tool_choice="none",
                max_output_tokens=max_output_tokens,
                config_sha256=config_sha256,
            )
            resp = adapter.complete(req)
            model_calls += 1
            if resp.usage.get("input_tokens") is not None:
                total_input_tokens += int(resp.usage["input_tokens"])
            if resp.usage.get("output_tokens") is not None:
                total_output_tokens += int(resp.usage["output_tokens"])
            if resp.usage.get("reasoning_tokens") is not None:
                total_reasoning_tokens += int(resp.usage["reasoning_tokens"])
            if resp.truncated or resp.finish_reason == "length":
                truncated_turns += 1
                parse_errors.append("truncated_turn")
                stop_reason = "parse_error:truncated_turn"
                break
            choice_idx = _parse_menu_choice(resp.text_output)
            if choice_idx is None or not (0 <= choice_idx < len(offering)):
                parse_errors.append("invalid_menu_choice")
                stop_reason = "parse_error:invalid_menu_choice"
                break
            action = offering[choice_idx]
            kind = action["action"]
            if kind == "stop":
                stop_reason = "model_stop"
                break
            ti = action["target"] - 1
            ref = targets[ti]["record_ref"]
            if kind == "lookup_archive":
                archive_lookups += 1
                entry = archive_store[ref]
                active[ref] = deepcopy(entry["value"])
                history.append({"action": action, "archive": {"digest": entry["digest"]}})
                continue
            correction = targets[ti]["correction_class"]
            if kind == "read_context":
                tool, args = "get_correction_context", {"record_ref": ref}
                scope = ""
            else:
                binding = active[ref]
                visit = binding["fields"]["visit_type"]
                scope = f"{visit}|{correction}"
                if kind == "read_policy":
                    tool, args = "get_correction_policy", {"visit_type": visit, "correction_class": correction}
                else:
                    tool = "apply_form_correction"
                    args = {
                        "correction_handle": binding["fields"]["correction_handle"],
                        "correction_class": correction,
                        "corrected_value": targets[ti]["corrected_value"],
                        "audit_profile_id": action["profile"],
                    }
            before = balance
            reply = driver.call(world, tool, args)
            charged, new_balance = _extract_budget(reply, world, before)
            balance = new_balance
            content = _extract_reply_content(reply)
            status = content.get("status")
            prev_rej = kind == "apply" and action["profile"] in rejected.get(scope, [])
            if kind == "apply" and status != "success":
                write_rejections += 1
                if prev_rej:
                    repeated_known_rejections += 1
            native_log.append(
                {
                    "native_call_index": len(native_log) + 1,
                    "tool": tool,
                    "arguments": args,
                    "charged": charged,
                    "balance_before": before,
                    "remaining_budget": balance,
                    "status": status,
                    "error_code": content.get("error_code"),
                    "inferred_target": ref,
                }
            )
            history.append({"action": action, "status": status, "code": content.get("error_code")})
            if kind == "read_context" and status == "success":
                fields = ("record_ref", "correction_handle", "visit_type", "binding_scope")
                active[ref] = {"fields": {k: content["data"][k] for k in fields}, "session": case.day, "call": len(native_log)}
            elif kind == "read_policy" and status == "success":
                policies[scope] = [row["audit_profile_id"] for row in content["data"]["evidence"]]
            elif kind == "apply":
                prof = action["profile"]
                if status == "success":
                    pending.remove(ti)
                    verified[scope] = prof
                    if prof in rejected.get(scope, []):
                        rejected[scope].remove(prof)
                elif content.get("error_code") == "CORRECTION_POLICY_MISMATCH":
                    if prof not in rejected.setdefault(scope, []):
                        rejected[scope].append(prof)

        if not pending:
            stop_reason = "all_committed"
        grade = driver.grade(world, task)
        completed = sorted(_grade_completed_targets("forms", grade))
        dispatch_order = _extract_dispatch_order(native_log)
        wall_ms = round((time.perf_counter_ns() - started_ns) / 1_000_000.0, 3)
        return {
            "case_id": case.case_id(),
            "workflow": "forms",
            "day": case.day,
            "arm": arm,
            "interface": "indexed_menu",
            "status": "ok",
            "focal_key": case.focal_key,
            "sham_key": case.sham_key,
            "direct_targets": list(case.direct_targets),
            "initial_budget": 17,
            "budget_spent": 17 - balance,
            "remaining_budget": balance,
            "completed": completed,
            "completed_count": len(completed),
            "total_targets": len(targets),
            "grade_valid": grade.get("valid", True),
            "grade_score": grade.get("score"),
            "dispatch_order": dispatch_order,
            "first_target": dispatch_order[0] if dispatch_order else None,
            "stop_reason": stop_reason,
            "model_calls": model_calls,
            "native_calls": len(native_log),
            "archive_lookups": archive_lookups,
            "write_rejections": write_rejections,
            "repeated_known_rejections": repeated_known_rejections,
            "parse_errors": parse_errors,
            "truncated_turns": truncated_turns,
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "reasoning": total_reasoning_tokens,
            },
            "wall_ms": wall_ms,
            "native_log": native_log,
        }
    finally:
        world.close()


def _pre_charge_dispatch_sequence(episode: JsonObject) -> list[str]:
    reread = episode.get("same_value_reread")
    cutoff = int(reread["native_call_index"]) if reread else None
    seq: list[str] = []
    for entry in episode.get("native_log", []):
        if cutoff is not None and entry["native_call_index"] >= cutoff:
            break
        tgt = entry.get("inferred_target")
        if tgt and tgt not in seq:
            seq.append(tgt)
    return seq


def summarize_case_audit(
    case: AuditCase,
    arms: dict[str, JsonObject],
) -> JsonObject:
    """Compute signed per-target counterfactual spillover and variance-calibrated metrics."""
    direct = set(case.direct_targets)
    keep_keys = sorted(k for k in arms if k.startswith("keep") and arms[k].get("status") == "ok")
    if not keep_keys or "remove" not in arms or arms["remove"].get("status") != "ok":
        return {"case_id": case.case_id(), "status": "incomplete"}

    keep0 = arms[keep_keys[0]]
    remove = arms["remove"]
    keep0_set = set(keep0["completed"])
    remove_set = set(remove["completed"])

    keep_sets = [set(arms[k]["completed"]) for k in keep_keys]
    keep_firsts = [arms[k]["first_target"] for k in keep_keys]
    keep_orders = [arms[k]["dispatch_order"] for k in keep_keys]
    keep_set_stable = all(s == keep0_set for s in keep_sets)
    keep_first_stable = all(f == keep0["first_target"] for f in keep_firsts)
    keep_order_stable = all(o == keep0["dispatch_order"] for o in keep_orders)

    sham = arms.get("sham")
    sham_valid = sham is not None and sham.get("status") == "ok"
    sham_set_matches_keep = (set(sham["completed"]) == keep0_set) if sham_valid else None
    sham_first_matches_keep = (sham["first_target"] == keep0["first_target"]) if sham_valid else None

    # Total effect: keep_r0 relative to remove (signed deltas: gained when keeping, lost when keeping)
    gained = sorted(keep0_set - remove_set)
    lost = sorted(remove_set - keep0_set)
    outside_gains = sorted((keep0_set - remove_set) - direct)
    outside_losses = sorted((remove_set - keep0_set) - direct)
    direct_changed = (keep0_set & direct) != (remove_set & direct)
    total_set_changed = keep0_set != remove_set
    total_count_delta = len(keep0_set) - len(remove_set)
    outside_changed = bool(outside_gains or outside_losses)

    # Pre-charge dispatch reordering check (strictly before designated re-read, or when no re-read occurred)
    remove_pre = _pre_charge_dispatch_sequence(remove)
    keep_order = keep0["dispatch_order"]
    if remove.get("same_value_reread") is None:
        pre_charge_dispatch_changed = (remove["dispatch_order"] != keep_order)
    else:
        prefix_len = min(len(remove_pre), len(keep_order))
        pre_charge_dispatch_changed = (
            remove_pre[:prefix_len] != keep_order[:prefix_len]
            or (len(remove_pre) > 0 and keep0["first_target"] != remove_pre[0])
        )

    # Fee-only counterfactual summary
    fee_arm = arms.get("fee_only")
    fee_summary: JsonObject | None = None
    if fee_arm is not None:
        if fee_arm.get("status") != "ok":
            fee_summary = {"status": fee_arm.get("status")}
        else:
            fee_set = set(fee_arm["completed"])
            f_gained = sorted(fee_set - remove_set)
            f_lost = sorted(remove_set - fee_set)
            f_out_gained = sorted((fee_set - remove_set) - direct)
            f_out_lost = sorted((remove_set - fee_set) - direct)
            fee_summary = {
                "status": "ok",
                "waived_cost": fee_arm["fee_only_control"]["waived_cost"],
                "prefix_replayed_calls": fee_arm["fee_only_control"]["prefix_replayed_calls"],
                "nonaccounting_match": fee_arm["fee_only_control"]["nonaccounting_match"],
                "completed_count_delta": len(fee_set) - len(remove_set),
                "set_changed": fee_set != remove_set,
                "gained": f_gained,
                "lost": f_lost,
                "outside_gains": f_out_gained,
                "outside_losses": f_out_lost,
                "outside_changed": bool(f_out_gained or f_out_lost),
                "direction_reversal": (len(fee_set) < len(remove_set)) or bool(f_out_lost),
            }

    # Archive recovery summary
    arch_arm = arms.get("archive")
    archive_summary: JsonObject | None = None
    if arch_arm is not None and arch_arm.get("status") == "ok":
        arch_set = set(arch_arm["completed"])
        archive_summary = {
            "status": "ok",
            "archive_lookups": arch_arm["archive_lookups"],
            "used_archive": arch_arm["archive_lookups"] > 0,
            "matches_keep_set": arch_set == keep0_set,
            "completed_count": len(arch_set),
            "budget_spent": arch_arm["budget_spent"],
        }

    return {
        "case_id": case.case_id(),
        "workflow": case.workflow,
        "day": case.day,
        "upstream_release_status": case.upstream_release_status,
        "status": "ok",
        "focal_key": case.focal_key,
        "sham_key": case.sham_key,
        "direct_targets": list(case.direct_targets),
        "variance_controls": {
            "keep_repeats": len(keep_keys),
            "keep_set_stable": keep_set_stable,
            "keep_first_target_stable": keep_first_stable,
            "keep_dispatch_order_stable": keep_order_stable,
            "sham_set_matches_keep": sham_set_matches_keep,
            "sham_first_matches_keep": sham_first_matches_keep,
        },
        "total_effect": {
            "keep_completed": keep0["completed"],
            "remove_completed": remove["completed"],
            "total_set_changed": total_set_changed,
            "total_count_delta": total_count_delta,
            "direct_changed": direct_changed,
            "gained": gained,
            "lost": lost,
            "outside_gains": outside_gains,
            "outside_losses": outside_losses,
            "outside_changed": outside_changed,
            "missed_by_total_count_only": total_set_changed and total_count_delta == 0,
            "missed_by_direct_target_only": total_set_changed and not direct_changed,
            "missed_by_both_counts": total_set_changed and total_count_delta == 0 and not direct_changed,
            "same_value_reread_triggered": remove.get("same_value_reread") is not None,
            "pre_charge_dispatch_changed": pre_charge_dispatch_changed,
            "signal_above_keep_and_sham_noise": (
                total_set_changed and keep_set_stable and (sham_set_matches_keep is not False)
            ),
        },
        "fee_only_effect": fee_summary,
        "archive_effect": archive_summary,
    }
