"""Ordinary offline controllers. Only published goals and native tool replies enter policy."""

import json


DOMAINS = {
    "api_reliability": ("call_id", "targets", "call_id", "search_recovery_evidence"),
    "backup_recovery": ("target_id", "deliverables", "target_id", "search_protection_policy_evidence"),
    "emergency_response": ("request_code", "artifacts", "request_code", "get_coordination_policy"),
    "k8s_operations": ("release_id", "artifacts", "release_id", "inspect_release_policy"),
    "railway_ticketing": ("request_id", "targets", "request_id", "list_stations"),
    "medical_appointment": ("patient_id", "artifacts", "patient_id", "get_patient_scheduling_context"),
}


def goals(name, task):
    public = task["query"]
    if public.lstrip().startswith("{"):
        return json.loads(public)["targets"]
    use = public.split("Requested artifacts:", 1)[1].lstrip()
    rows = json.JSONDecoder().raw_decode(use)[0]
    if name == "emergency_response":
        return [{"request_code": row} for row in rows]
    return rows


def cell(*parts):
    return json.dumps(parts, separators=(",", ":"))


def release_cell(t):
    w, p, s = t["workload"], t["placement"], t["service"]
    return dict(workload_class=w["workload_class"], change_window=w["change_window"],
                placement_class=p["placement_class"], access_class=s["access_class"], traffic_class=s["traffic_class"])


def known_key(name, t, memory):
    if name == "api_reliability":
        return cell(t["failure_signal"], t["operation_class"])
    if name == "backup_recovery":
        return cell(t["service_tier"], t["data_class"])
    if name == "emergency_response":
        return memory["keys"].get(t["request_code"])
    if name == "k8s_operations":
        return cell(*release_cell(t).values())
    if name == "railway_ticketing":
        return cell(t["origin_station_name"])
    return cell(t["patient_id"])


def floor(name, t, mem, inserted=None):
    key = known_key(name, t, mem)
    have = key in mem["receipts"] or (inserted is not None and key == inserted)
    if name == "api_reliability":
        credential = cell(t["integration_id"], t["operation"]) in mem["aux"]
        return 16 + (0 if credential else 3) + (0 if have else 17)
    if name == "backup_recovery":
        return 20 + (0 if have else 20)
    if name == "emergency_response":
        return 23 + (0 if have else 5)
    if name == "k8s_operations":
        return 16 + 3*t["workload"]["desired_replicas"] + 2*len(t["service"]["ports"]) + (0 if have else 18)
    if name == "railway_ticketing":
        dest = cell("station", t["destination_station_name"])
        pax = cell("passenger", t["passenger_name"])
        return 16 + 8 * ((not have) + (dest not in mem["aux"]) + (pax not in mem["aux"]))
    if have:
        receipt = mem["receipts"].get(key)
        policy = receipt is not None and cell(receipt["care_tier"], t["request_class"]) in mem["aux"]
        return 14 + (0 if policy or receipt is None else 10)
    return 30


def execute(name, t, run):
    return globals()["work_" + name](t, run)


def work_api_reliability(t, run):
    integration, operation = t["integration_id"], t["operation"]
    key = known_key(run.name, t, run.memory)
    credential = run.remember("list_api_credentials", cell(integration, operation),
                              {"integration_id": integration, "scope_contains": operation}, lambda d: d["items"][0]["credential_id"])
    quota = run.read("list_retry_budgets", {"integration_id": integration})["items"][0]
    bucket = run.read("inspect_rate_limit_status", {"integration_id": integration, "operation": operation})["buckets"][0]
    if quota["status"] != "open" or bucket["remaining"] < 1:
        return "live_capacity_unavailable"
    query = dict(failure_signal=t["failure_signal"], operation_class=t["operation_class"])
    argument = dict(call_id=t["call_id"], credential_id=credential, retry_budget_id=quota["budget_id"],
                    rate_limit_bucket_id=bucket["bucket_id"])
    for _ in range(2):
        policy = run.receipt(key, query, lambda d: {"profile": d["evidence"][0]["recovery_profile_id"]})
        result = run.tool("retry_api_call", {**argument, "recovery_profile_id": policy["profile"]})
        if run.success(result):
            return "committed"
        run.reject(key)
        if "PROFILE" not in run.error(result).upper():
            return run.error(result)
        run.require(27, "policy_retry")
    return "retry_rejected"


def work_backup_recovery(t, run):
    aux = run.memory["aux"]
    if "sites" not in aux:
        raw = run.read("list_protection_sites", {"limit": 10, "offset": 0})
        aux["sites"] = {row["name"]: row["site_id"] for row in raw["sites"]}
    site = aux["sites"][t["site_name"]]
    key = known_key(run.name, t, run.memory)
    query = {k:t[k] for k in ("service_tier", "data_class")}

    def projection(d):
        row = d["evidence"][0]
        return {k:row[k] for k in ("protection_route", "repository_profile", "effective_epoch")}

    def repository(profile, refresh=False):
        if refresh:
            aux.pop(cell("repositories", site), None)
        rows = run.remember("list_backup_repositories", cell("repositories", site),
                            dict(site_id=site, status_filter="online", limit=10, offset=0),
                            lambda d:d["repositories"])
        return next((row["repository_id"] for row in rows if row.get("protection_profile") == profile), None)

    policy = run.receipt(key, query, projection)
    repo = repository(policy["repository_profile"])
    if repo is None:
        return "repository_unavailable"
    run.require(20, "schedule_activate_assign")
    run.read("create_schedule_window", dict(policy_id=t["policy_id"], name=t["schedule_name"], frequency="daily",
             start_time_local=t["start_time_local"], duration_minutes=60, allowed_weekdays=["mon","tue","wed","thu","fri","sat","sun"]))
    run.read("update_backup_policy_status", dict(policy_id=t["policy_id"], new_status="active"))
    for _ in range(2):
        result = run.tool("assign_policy_to_asset", dict(policy_id=t["policy_id"], asset_id=t["asset_id"],
                          repository_id=repo, protection_route=policy["protection_route"]))
        if run.success(result):
            run.read("list_policy_assignments", dict(site_id=site, policy_id=t["policy_id"], asset_id=t["asset_id"],
                     limit=1, offset=0))
            return "committed"
        run.reject(key)
        if "EPOCH" in run.error(result).upper() or "REVALID" in run.error(result).upper() or result.get("status") == "error":
            run.require(35, "routing_retry")
            run.read("get_site_recovery_dashboard", {"site_id": site})
        else:
            return run.error(result)
        policy = run.receipt(key, query, projection)
        repo = repository(policy["repository_profile"], True)
        if repo is None:
            return "repository_unavailable"
    return "retry_rejected"


def work_emergency_response(t, run):
    ref = t["request_code"]
    order_id = run.read("search_dispatch_orders", {"request_code": ref})["orders"][0]["order_id"]
    data = run.read("get_dispatch_order", {"order_id": order_id})
    order = data.get("order", data)
    query = {k:order[k] for k in ("incident_type", "mission_class")}
    key = cell(*query.values())
    run.memory["keys"][ref] = key
    rule = run.receipt(key, query, lambda d:{k: v for k,v in d.get("policy", d).items()
                                           if k not in {"policy_id","effective_epoch","version","evidence_id"}})
    roster_data = run.remember("inspect_dispatch_roster", cell("roster", order["roster_id"]),
                               {"roster_id":order["roster_id"]}, lambda d:d)
    candidates = roster_data.get("candidates", roster_data.get("resources", []))
    required = order["required_capability"]
    agencies = rule.get("allowed_owner_agency_ids", rule.get("allowed_agency_ids"))
    rows = [r for r in candidates if (
        required == r.get("capability") or required in r.get("capabilities", [])
    ) and (not agencies or r.get("owner_agency_id", r.get("agency_id")) in agencies)]
    if not rows:
        return "no_qualified_roster_candidate"
    agency = order.get("lead_agency_id") or order["requested_by_agency_id"]
    for candidate in rows[:2]:
        resource = candidate["resource_id"]
        run.require(13, "assignment_release")
        result = run.tool("assign_resource_to_incident", dict(dispatch_order_id=order_id, resource_id=resource,
                          incident_id=order["incident_id"], requested_by_agency_id=agency, required_capability=required,
                          mission=order.get("mission", order["mission_class"]), priority=order["priority"],
                          assigned_at=order.get("requested_at", "2026-06-01T08:00:00Z")))
        if run.success(result):
            data = run.data(result)
            assignment = data.get("assignment", data)
            run.read("release_resource_assignment", dict(assignment_id=assignment["assignment_id"],
                     released_at="2026-12-31T12:00:00Z", release_status="available"))
            run.read("get_resource_unit_status", dict(resource_id=resource, include_assignment_history=False))
            return "committed"
        run.reject(key)
    return "retry_rejected"


def work_k8s_operations(t, run):
    release = t["release_id"]
    query = release_cell(t)
    key = cell(*query.values())
    cluster_select = t["cluster_selector"]
    cluster = run.remember("list_clusters", cell("cluster", *cluster_select.values()), cluster_select,
                          lambda d:d.get("clusters", d.get("items"))[0])
    namespace_query = {**t["namespace_selector"], "cluster_id":cluster["cluster_id"], "status_filter":"active"}
    namespace = run.remember("list_namespaces", cell("namespace", *namespace_query.values()), namespace_query,
                             lambda d:d.get("namespaces", d.get("items"))[0])
    ns = namespace["namespace_id"]
    w, p, s = t["workload"], t["placement"], t["service"]
    directory = namespace.get("pool_directory_id", namespace.get("directory_id", cluster.get("pool_directory_id")))
    rule = run.receipt(key, query, lambda d:d["requirements"])
    selected = []
    for zone in p["required_zones"]:
        for offset in range(0,8,2):
            pool_data = run.read("list_worker_pools", dict(directory_id=directory, zone=zone,offset=offset,limit=2))
            candidate_pools = pool_data.get("pools", pool_data.get("worker_pools", pool_data.get("items")))
            if not candidate_pools:
                return "no_assigned_pool"
            match=None
            for pool in candidate_pools:
                view = run.read("inspect_worker_pool", dict(pool_id=pool["pool_id"], namespace_id=ns))
                if view.get("assignment",{}).get("status")=="assigned":
                    match=next((node for node in view.get("nodes",[]) if node.get("schedulable")
                                and node.get("active_pods",0)<node.get("allocatable_pods",0)),None)
                if match:
                    break
            if match:
                selected.append(match["node_id"])
                break
        else:
            return "no_assigned_pool"
    for _ in range(2):
        rule = run.receipt(key, query, lambda d:d["requirements"])
        run.require(16 + 3*w["desired_replicas"] + 2*len(s["ports"]), "publish_and_service")
        result = run.tool("publish_deployment", dict(namespace_id=ns, **{**w, **query},
                          placement_node_ids=selected, update_strategy=rule["update_strategy"], release_id=release))
        if run.success(result):
            data = run.data(result)
            dep = data.get("deployment", data)
            service = dict(s)
            service["ports"] = [{**port,"protocol":rule["protocol"]} for port in s["ports"]]
            if rule["external_dns"] != "required":
                service.pop("external_dns",None)
            run.read("create_service", dict(deployment_id=dep["deployment_id"], **service, service_type=rule["service_type"]))
            return "committed"
        if "POLICY" not in run.error(result).upper():
            return run.error(result)
        run.reject(key)
    return "retry_rejected"


def work_medical_appointment(t, run):
    patient = t["patient_id"]
    key = cell(patient)
    request = t["request_class"]
    included = ("care_tier","home_site_id","source_appointment_id","source_practitioner_id","source_specialty")
    context = run.receipt(key, {"patient_id":patient}, lambda d:{k:d[k] for k in included})
    policy_key = cell(context["care_tier"], request)
    date = t["requested_date"]
    for _ in range(2):
        rule = run.remember("get_follow_up_policy", policy_key,
                            dict(care_tier=context["care_tier"], request_class=request), lambda d:d["evidence"][0])
        run.require(14, "slot_and_booking")
        data = run.read("search_appointment_slots", dict(site_id=context["home_site_id"], start_date=date, end_date=date,
                        specialty=context["source_specialty"], visit_mode=rule["visit_mode"], limit=4))
        same = rule["practitioner_relation"] == "source_practitioner"
        slot = next((v for v in data["slots"] if (v["practitioner_id"] == context["source_practitioner_id"]) == same), None)
        if slot is not None:
            result = run.tool("create_follow_up_appointment", dict(source_appointment_id=context["source_appointment_id"],
                              new_slot_id=slot["slot_id"], follow_up_reason=request, request_class=request,
                              routing_profile_id=rule["routing_profile_id"], intake_channel="agent"))
            if run.success(result):
                return "committed"
            run.reject(key)
        run.memory["aux"].pop(policy_key, None)
    return "no_current_eligible_slot_or_retry_rejected"



def work_railway_ticketing(t, run):
    origin, dest, person = t["origin_station_name"], t["destination_station_name"], t["passenger_name"]

    def station(label):
        return lambda d: next(r["station_id"] for r in d["stations"] if r["name"] == label)

    source = run.receipt(cell(origin), dict(query=origin, limit=1), station(origin))
    target = run.remember("list_stations", cell("station",dest), dict(query=dest,limit=1), station(dest))
    pax = run.remember("list_passenger_profiles", cell("passenger",person), dict(query=person,limit=1),
                       lambda d: next(r["passenger_id"] for r in d["passengers"] if r["full_name"] == person))
    run.require(16, "service_and_confirmation")
    trip = dict(origin_station_id=source, destination_station_id=target)
    rows = run.read("search_direct_trains", dict(**trip, travel_date=t["travel_date"],
                    seat_class=t["seat_class"], only_available=True, limit=4))
    services = rows.get("trains", rows.get("services", rows.get("items", [])))
    if not services:
        return "no_live_service"
    service = services[0]
    position = t["requested_position"]
    run.require(9, "booking_and_confirmation")
    data = run.read("create_booking_order", dict(**trip, train_service_id=service["train_service_id"],
                    requester_passenger_id=pax, seat_preference=position if position in {"window","aisle"} else "none"))
    order = data.get("order", data)
    order_id = order["order_id"]
    selection = run.tool("set_ticket_seat_preference", dict(order_id=order_id, passenger_id=pax,
                         seat_position=position, seat_class=t["seat_class"]))
    if not run.success(selection):
        return run.error(selection)
    run.read("submit_booking_order", dict(order_id=order_id,payment_reference=t["request_id"],
             seat_assignment_strategy="respect_preference",allow_waitlist_fallback=False))
    return "committed"
