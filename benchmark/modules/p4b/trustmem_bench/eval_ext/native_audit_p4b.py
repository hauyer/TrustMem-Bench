"""Native tool-calling counterfactual spillover audit engine for P3 official workflows (P4b).

Extends TrustMem-Bench's unconstrained OpenAI native tool-calling audit to two additional
upstream-released P3 prospective ReScopeBench workflows without modifying frozen P4 code:
  - backup_recovery (14 native tools, budget 126, all 10 P3 openings: T05, T06, T08-T15)
  - railway_ticketing (18 native tools, budget 48, first 8 contiguous P3 openings: T09-T16)

Emits schema-identical EPISODE.json, model_calls.jsonl, CASE_SUMMARIES.json, and
AGGREGATE_REPORT.json outputs for full compatibility with summarize_p4_matrix.py and
zero-GPU deterministic replay via RecordedReplayAdapter.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
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
from .native_audit import AuditCase, summarize_case_audit
from .openai_compatible import canonical_json


_ACTIVE_P4B_RESCOPE_ROOT: str | None = None

BACKUP_WRITE_TOOLS = frozenset(
    {
        "create_backup_policy",
        "update_backup_policy_status",
        "create_schedule_window",
        "assign_policy_to_asset",
        "remove_policy_assignment",
    }
)

RAILWAY_WRITE_TOOLS = frozenset(
    {
        "add_passenger_to_order",
        "cancel_ticket_order",
        "cancel_waitlist_order",
        "change_ticket_seat_assignment",
        "create_booking_order",
        "set_ticket_seat_preference",
        "submit_booking_order",
        "submit_waitlist_order",
    }
)


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


def load_p4b_driver(workflow: str, source_root: Path):
    """Import a pinned P3 released ReScopeBench workflow driver cleanly."""
    global _ACTIVE_P4B_RESCOPE_ROOT
    resolved = str(Path(source_root).resolve())
    if _ACTIVE_P4B_RESCOPE_ROOT != resolved:
        for mod_name in [
            name
            for name in list(sys.modules)
            if name == "rescopebench" or name.startswith("rescopebench.")
        ]:
            del sys.modules[mod_name]
        if resolved in sys.path:
            sys.path.remove(resolved)
        sys.path.insert(0, resolved)
        _ACTIVE_P4B_RESCOPE_ROOT = resolved

    if workflow == "backup_recovery":
        mod = importlib.import_module("rescopebench.cases.backup_recovery.driver")
        return mod.Driver(), None
    if workflow == "railway_ticketing":
        mod = importlib.import_module("rescopebench.cases.railway_ticketing.driver")
        return mod.Driver(), None
    raise ValueError(f"Unsupported P4b workflow: {workflow}")


def load_p4b_opening_snapshot(case: AuditCase) -> tuple[JsonObject, JsonObject]:
    """Load frozen P3 checkpoint (world_state, memory_state) without mutating source files."""
    combined = json.loads(case.opening_world_path.read_text(encoding="utf-8"))
    return deepcopy(combined["state"]), deepcopy(combined["memory"])


def parse_p4b_targets(workflow: str, task: JsonObject) -> list[JsonObject]:
    public = task["query"]
    if public.lstrip().startswith("{"):
        return json.loads(public)["targets"]
    use = public.split("Requested artifacts:", 1)[1].lstrip()
    return json.JSONDecoder().raw_decode(use)[0]


def p4b_target_id_field(workflow: str) -> str:
    if workflow == "backup_recovery":
        return "target_id"
    if workflow == "railway_ticketing":
        return "request_id"
    raise ValueError(f"Unsupported P4b workflow: {workflow}")


def p4b_workflow_tool_costs(workflow: str) -> dict[str, Any]:
    if workflow == "backup_recovery":
        return {
            "list_protection_sites": 32,
            "get_site_recovery_dashboard": 7,
            "list_backup_repositories": "4 (+2 per row)",
            "list_workload_assets": 4,
            "get_workload_asset": 32,
            "list_backup_policies": 4,
            "get_backup_policy": 32,
            "list_policy_assignments": "6 (0 for own current-episode confirmation with site_id, policy_id, asset_id, limit=1, offset=0)",
            "search_protection_policy_evidence": "20 (14 after observing newer global epoch)",
            "create_backup_policy": 10,
            "update_backup_policy_status": 6,
            "create_schedule_window": 6,
            "assign_policy_to_asset": 8,
            "remove_policy_assignment": 8,
        }
    if workflow == "railway_ticketing":
        return {
            "list_stations": 8,
            "list_passenger_profiles": 8,
            "search_direct_trains": 7,
            "search_station_pairs": 4,
            "get_train_schedule": 4,
            "list_train_stops": 4,
            "get_remaining_ticket_summary": 4,
            "inspect_seat_map": 4,
            "get_passenger_verification_status": 4,
            "get_order_details": "4 (0 for own confirmed order)",
            "create_booking_order": 3,
            "set_ticket_seat_preference": 3,
            "submit_booking_order": 3,
            "add_passenger_to_order": 3,
            "change_ticket_seat_assignment": 3,
            "cancel_ticket_order": 3,
            "submit_waitlist_order": 3,
            "cancel_waitlist_order": 3,
        }
    raise ValueError(f"Unsupported P4b workflow: {workflow}")


def p4b_focal_reread_tool(workflow: str) -> str:
    if workflow == "backup_recovery":
        return "search_protection_policy_evidence"
    if workflow == "railway_ticketing":
        return "list_stations"
    raise ValueError(f"Unsupported P4b workflow: {workflow}")


def p4b_is_write_tool(workflow: str, tool_name: str) -> bool:
    if workflow == "backup_recovery":
        return tool_name in BACKUP_WRITE_TOOLS
    if workflow == "railway_ticketing":
        return tool_name in RAILWAY_WRITE_TOOLS
    return False


def _sanitize_tool_schema_for_llm(obj: Any) -> Any:
    """Strip JSON Schema keywords rejected by vLLM xgrammar (e.g. uniqueItems) without altering simulator validation."""
    if isinstance(obj, dict):
        return {
            k: _sanitize_tool_schema_for_llm(v)
            for k, v in obj.items()
            if k != "uniqueItems"
        }
    if isinstance(obj, list):
        return [_sanitize_tool_schema_for_llm(item) for item in obj]
    return obj


def extract_p4b_tool_specs(workflow: str, driver: Any, include_archive: bool) -> tuple[ToolSpec, ...]:
    specs: list[ToolSpec] = []
    for item in driver.tools:
        fn = item["function"] if "function" in item else item
        schema = _sanitize_tool_schema_for_llm(deepcopy(fn.get("parameters") or fn.get("input_schema")))
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


def _build_archive_store(full_memory: JsonObject) -> dict[str, JsonObject]:
    source = full_memory.get("receipts") or {}
    store: dict[str, JsonObject] = {}
    for key, value in sorted(source.items()):
        body = canonical_json(value).encode("utf-8")
        address = sha256(body).hexdigest()
        store[key] = {"digest": address, "bytes": len(body), "value": deepcopy(value)}
    return store


def _resolve_archive_key(workflow: str, archive_store: dict[str, JsonObject], raw_key: str) -> str | None:
    if raw_key in archive_store:
        return raw_key
    stripped = raw_key.strip()
    if stripped in archive_store:
        return stripped
    if workflow == "railway_ticketing":
        candidate = _cell(stripped)
        if candidate in archive_store:
            return candidate
    if workflow == "backup_recovery":
        for sep in ("|", ",", "/"):
            if sep in stripped and not stripped.startswith("["):
                parts = [p.strip() for p in stripped.split(sep, 1)]
                candidate = _cell(*parts)
                if candidate in archive_store:
                    return candidate
        # Normalize JSON array whitespace e.g. '["standard", "internal"]'
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    candidate = _cell(*parsed)
                    if candidate in archive_store:
                        return candidate
            except ValueError:
                pass
    return None


def _matches_p4b_focal_reread(
    workflow: str,
    tool_name: str,
    args: JsonObject,
    reply: JsonObject,
    focal_key: str,
    prior_receipt: Any,
) -> bool:
    if tool_name != p4b_focal_reread_tool(workflow):
        return False
    content = _extract_reply_content(reply)
    if content.get("status") != "success":
        return False
    data = content.get("data") or {}
    if workflow == "backup_recovery":
        if _cell(args.get("service_tier"), args.get("data_class")) != focal_key:
            return False
        evidence = data.get("evidence") or []
        if not evidence:
            return False
        row = evidence[0]
        projected = {
            k: row.get(k) for k in ("protection_route", "repository_profile", "effective_epoch")
        }
        return projected == prior_receipt
    if workflow == "railway_ticketing":
        origin_name = json.loads(focal_key)[0]
        query = args.get("query")
        if query is not None:
            q_low = str(query).strip().lower()
            o_low = str(origin_name).strip().lower()
            if q_low and (q_low not in o_low and o_low not in q_low):
                return False
        stations = data.get("stations") or []
        for row in stations:
            if row.get("name") == origin_name and row.get("station_id") == prior_receipt:
                return True
        return False
    return False


def _call_p4b_tool(
    workflow: str,
    driver: Any,
    world: Any,
    tool_name: str,
    args: JsonObject,
    *,
    waive_cost: bool = False,
) -> JsonObject:
    if not waive_cost:
        return driver.call(world, tool_name, args)
    if workflow == "railway_ticketing":
        old_finish = world._finish

        def zero_finish(name, arguments, actor, result, cost, before_hash):
            adjusted = 0 if name == tool_name else cost
            return old_finish(name, arguments, actor, result, adjusted, before_hash)

        with patch.object(world, "_finish", side_effect=zero_finish):
            return driver.call(world, tool_name, args)

    old_cost = world._cost

    def zero_cost(*pos, **kwargs):
        price = old_cost(*pos, **kwargs)
        if pos and pos[0] == tool_name and isinstance(price, int):
            return 0
        return price

    with patch.object(world, "_cost", side_effect=zero_cost):
        return driver.call(world, tool_name, args)


def _update_p4b_observed_handles(
    workflow: str,
    tool_name: str,
    args: JsonObject,
    reply: JsonObject,
    targets: list[JsonObject],
    opening_memory: JsonObject,
    observed_handles: dict[str, str],
) -> None:
    content = _extract_reply_content(reply)
    if content.get("status") != "success":
        return
    data = content.get("data") or {}
    if workflow == "railway_ticketing":
        if tool_name == "create_booking_order":
            order = data.get("order") if isinstance(data.get("order"), dict) else data
            oid = order.get("order_id")
            if oid:
                inferred = _infer_p4b_target(
                    workflow, tool_name, args, targets, opening_memory, observed_handles
                )
                if inferred:
                    observed_handles[f"order:{oid}"] = inferred
        elif tool_name == "list_stations":
            for row in data.get("stations") or []:
                if row.get("station_id") and row.get("name"):
                    observed_handles[f"station:{row['station_id']}"] = row["name"]
        elif tool_name == "list_passenger_profiles":
            for row in data.get("passengers") or []:
                if row.get("passenger_id") and row.get("full_name"):
                    observed_handles[f"pax:{row['passenger_id']}"] = row["full_name"]
    elif workflow == "backup_recovery":
        if tool_name == "list_protection_sites":
            for row in data.get("sites") or []:
                if row.get("site_id") and row.get("name"):
                    observed_handles[f"site:{row['site_id']}"] = row["name"]


def _infer_p4b_target(
    workflow: str,
    tool_name: str,
    args: JsonObject,
    targets: list[JsonObject],
    opening_memory: JsonObject,
    observed_handles: dict[str, str],
) -> str | None:
    if workflow == "backup_recovery":
        pid = args.get("policy_id")
        aid = args.get("asset_id")
        if pid:
            matches = [t["target_id"] for t in targets if t.get("policy_id") == pid]
            if len(matches) == 1:
                return matches[0]
        if aid:
            matches = [t["target_id"] for t in targets if t.get("asset_id") == aid]
            if len(matches) == 1:
                return matches[0]
        if tool_name == "search_protection_policy_evidence":
            st, dc = args.get("service_tier"), args.get("data_class")
            matches = [
                t["target_id"]
                for t in targets
                if t.get("service_tier") == st and t.get("data_class") == dc
            ]
            if len(matches) == 1:
                return matches[0]
        sid = args.get("site_id")
        if sid:
            site_name = observed_handles.get(f"site:{sid}")
            if site_name is None:
                sites_map = (opening_memory.get("aux") or {}).get("sites") or {}
                for nm, mapped_sid in sites_map.items():
                    if mapped_sid == sid:
                        site_name = nm
                        break
            if site_name is not None:
                matches = [t["target_id"] for t in targets if t.get("site_name") == site_name]
                if len(matches) == 1:
                    return matches[0]
        return None

    if workflow == "railway_ticketing":
        pay_ref = args.get("payment_reference")
        if pay_ref:
            matches = [t["request_id"] for t in targets if t.get("request_id") == pay_ref]
            if len(matches) == 1:
                return matches[0]
        oid = args.get("order_id")
        if oid and f"order:{oid}" in observed_handles:
            return observed_handles[f"order:{oid}"]

        # Build station_id -> name and passenger_id -> name maps from opening_memory + observed
        stn_to_name: dict[str, str] = {}
        pax_to_name: dict[str, str] = {}
        for k, v in (opening_memory.get("receipts") or {}).items():
            try:
                stn_to_name[str(v)] = json.loads(k)[0]
            except Exception:
                pass
        for k, v in (opening_memory.get("aux") or {}).items():
            try:
                parts = json.loads(k)
                if isinstance(parts, list) and len(parts) == 2:
                    if parts[0] == "station":
                        stn_to_name[str(v)] = parts[1]
                    elif parts[0] == "passenger":
                        pax_to_name[str(v)] = parts[1]
            except Exception:
                pass
        for hk, hv in observed_handles.items():
            if hk.startswith("station:"):
                stn_to_name[hk.split(":", 1)[1]] = hv
            elif hk.startswith("pax:"):
                pax_to_name[hk.split(":", 1)[1]] = hv

        pax_id = args.get("requester_passenger_id") or args.get("passenger_id")
        if pax_id and str(pax_id) in pax_to_name:
            pname = pax_to_name[str(pax_id)]
            matches = [t["request_id"] for t in targets if t.get("passenger_name") == pname]
            if len(matches) == 1:
                return matches[0]

        orig_id = args.get("origin_station_id")
        dest_id = args.get("destination_station_id")
        if orig_id and str(orig_id) in stn_to_name:
            oname = stn_to_name[str(orig_id)]
            matches = [t["request_id"] for t in targets if t.get("origin_station_name") == oname]
            if len(matches) == 1:
                return matches[0]
        if dest_id and str(dest_id) in stn_to_name:
            dname = stn_to_name[str(dest_id)]
            matches = [
                t["request_id"] for t in targets if t.get("destination_station_name") == dname
            ]
            if len(matches) == 1:
                return matches[0]

        if tool_name == "list_stations" and args.get("query"):
            q = str(args["query"]).strip().lower()
            matches = [
                t["request_id"]
                for t in targets
                if q == t["origin_station_name"].lower()
                or q == t["destination_station_name"].lower()
                or q in t["origin_station_name"].lower()
                or q in t["destination_station_name"].lower()
            ]
            if len(matches) == 1:
                return matches[0]
        if tool_name == "list_passenger_profiles" and args.get("query"):
            q = str(args["query"]).strip().lower()
            matches = [
                t["request_id"]
                for t in targets
                if q == t["passenger_name"].lower() or q in t["passenger_name"].lower()
            ]
            if len(matches) == 1:
                return matches[0]
        return None
    return None


def _grade_p4b_completed_targets(workflow: str, grade: JsonObject) -> list[str]:
    if workflow == "backup_recovery":
        return [row["target_id"] for row in grade["deliverables"] if row.get("complete")]
    if workflow == "railway_ticketing":
        return [row["request_id"] for row in grade["targets"] if row.get("complete")]
    raise ValueError(f"Unsupported P4b workflow: {workflow}")


def _extract_dispatch_order(native_log: list[JsonObject]) -> list[str]:
    order: list[str] = []
    for row in native_log:
        tgt = row.get("inferred_target")
        if tgt and tgt not in order:
            order.append(tgt)
    return order


def build_p4b_system_prompt(workflow: str, include_archive: bool) -> str:
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
        "tool call per turn. Previously saved cross-session receipts and auxiliary lookups in "
        "active memory may save read cost, though rules or policies may have drifted since "
        "earlier sessions; live tool responses are authoritative when a write is rejected. Do "
        "not repeat a write call with identical arguments after it is rejected."
        + archive_clause
        + " Call `finish_session` when all feasible targets are complete or no remaining "
        "beneficial action can be funded."
    )


def build_p4b_opening_user_payload(
    workflow: str,
    day: int,
    task: JsonObject,
    balance: int,
    active_memory: JsonObject,
    archive_keys: list[str] | None,
) -> JsonObject:
    targets = parse_p4b_targets(workflow, task)
    payload: JsonObject = {
        "workflow": workflow,
        "session": f"T{day:02d}",
        "remaining_budget": balance,
        "tool_costs": p4b_workflow_tool_costs(workflow),
        "task_instructions": task["query"],
        "requested_targets": targets,
        "active_memory": active_memory,
    }
    if archive_keys is not None:
        payload["available_archive_keys"] = sorted(archive_keys)
    return payload


def run_p4b_native_episode(
    case: AuditCase,
    arm: str,
    adapter: ModelAdapter,
    *,
    provider: str,
    model: str,
    config_sha256: str,
    max_output_tokens: int = 384,
    max_steps: int | None = None,
    max_consecutive_errors: int = 4,
    fee_prefix_source: JsonObject | None = None,
) -> JsonObject:
    """Execute one P4b native tool-calling episode from a frozen P3 checkpoint."""
    started_ns = time.perf_counter_ns()
    driver, _ = load_p4b_driver(case.workflow, case.source_root)
    world_state, full_memory = load_p4b_opening_snapshot(case)
    opening_memory = deepcopy(full_memory)
    prior_focal = deepcopy(full_memory["receipts"][case.focal_key])

    include_archive = arm == "archive"
    archive_store = _build_archive_store(full_memory) if include_archive else None

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
        opening_memory["receipts"].pop(case.sham_key)
    elif arm in {"remove", "archive", "fee_only"}:
        opening_memory["receipts"].pop(case.focal_key)
    else:
        raise ValueError(f"Unknown arm: {arm}")

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
            step
            for step in fee_prefix_source["turns"]
            if step.get("native_call_index") is not None
            and step["native_call_index"] <= waive_at_native_index
        ]

    world = driver.create_world()
    try:
        world.restore(world_state)
        task = driver.tasks[case.day - 1]
        driver.begin(world, task)
        initial_balance = int(world.remaining if hasattr(world, "remaining") else world._remaining)
        balance = initial_balance

        targets = parse_p4b_targets(case.workflow, task)
        tools = extract_p4b_tool_specs(case.workflow, driver, include_archive=include_archive)
        system_prompt = build_p4b_system_prompt(case.workflow, include_archive=include_archive)
        archive_keys = sorted(archive_store) if archive_store is not None else None
        user_payload = build_p4b_opening_user_payload(
            case.workflow, case.day, task, balance, opening_memory, archive_keys
        )
        messages: list[JsonObject] = [{"role": "user", "content": user_payload}]

        surface = NativeToolSurface()
        step_cap = max_steps or (28 if case.workflow == "backup_recovery" else 24)
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

        # Phase A (fee_only): deterministically replay remove's exact prefix up to the waived call
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
                reply = _call_p4b_tool(
                    case.workflow, driver, world, tool_name, args, waive_cost=is_waived
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
                _update_p4b_observed_handles(
                    case.workflow, tool_name, args, reply, targets, opening_memory, observed_handles
                )
                inferred_target = _infer_p4b_target(
                    case.workflow, tool_name, args, targets, opening_memory, observed_handles
                )
                content = _extract_reply_content(reply)
                err_code = (
                    content.get("error_code")
                    or content.get("code")
                    or (content.get("data") or {}).get("error_code")
                )
                if p4b_is_write_tool(case.workflow, tool_name) and content.get("status") != "success":
                    write_rejections += 1
                    sig = _digest({"tool": tool_name, "args": args})
                    if sig in seen_rejected_writes:
                        repeated_known_rejections += 1
                    seen_rejected_writes.add(sig)
                native_log.append(
                    {
                        "native_call_index": native_index,
                        "tool": tool_name,
                        "arguments": args,
                        "charged": charged,
                        "balance_before": before_balance,
                        "remaining_budget": balance,
                        "status": content.get("status"),
                        "error_code": err_code,
                        "inferred_target": inferred_target,
                        "waived_charge": is_waived,
                        "replayed_prefix": True,
                    }
                )
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
                        "status": content.get("status"),
                        "error_code": err_code,
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
                    assert (
                        sha256(canonical_json(entry["value"]).encode("utf-8")).hexdigest()
                        == entry["digest"]
                    )
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

            before_balance = balance
            native_index = len(native_log) + 1
            reply = _call_p4b_tool(case.workflow, driver, world, call.name, args, waive_cost=False)
            charged, new_balance = _extract_budget(reply, world, before_balance)
            assert before_balance - charged == new_balance
            balance = new_balance
            content = _extract_reply_content(reply)
            status = content.get("status")
            error_code = (
                content.get("error_code")
                or content.get("code")
                or (content.get("data") or {}).get("error_code")
            )
            _update_p4b_observed_handles(
                case.workflow, call.name, args, reply, targets, opening_memory, observed_handles
            )
            inferred_target = _infer_p4b_target(
                case.workflow, call.name, args, targets, opening_memory, observed_handles
            )

            if status == "success":
                consecutive_errors = 0
            else:
                err_upper = str(error_code or "").upper()
                if "BUDGET" in err_upper or "ALLOWANCE" in err_upper or "QUOTA" in err_upper or "GUARD" in err_upper:
                    unaffordable_attempts += 1
                elif "INVALID" in err_upper:
                    invalid_arg_errors += 1
                if p4b_is_write_tool(case.workflow, call.name):
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
                and _matches_p4b_focal_reread(
                    case.workflow, call.name, args, reply, case.focal_key, prior_focal
                )
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

            native_log.append(
                {
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
            )
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
        completed = sorted(_grade_p4b_completed_targets(case.workflow, grade))
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


__all__ = [
    "AuditCase",
    "build_p4b_opening_user_payload",
    "build_p4b_system_prompt",
    "extract_p4b_tool_specs",
    "load_p4b_driver",
    "load_p4b_opening_snapshot",
    "p4b_focal_reread_tool",
    "p4b_target_id_field",
    "p4b_workflow_tool_costs",
    "parse_p4b_targets",
    "run_p4b_native_episode",
    "summarize_case_audit",
]
