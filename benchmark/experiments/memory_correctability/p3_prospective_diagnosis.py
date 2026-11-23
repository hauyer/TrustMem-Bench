"""Deterministic diagnosis using the public single-loss-track record only."""

DIAGNOSTICS = ("D0", "D1", "D2a", "D2b")


def verdict(label, reason, added=(), displaced=()):
    return dict(predicted_class=label, predicted_added_targets=sorted(added),
                predicted_displaced_targets=sorted(displaced), reason_code=reason)


def from_sets(before, after, reason, confirmation=False):
    added, displaced = set(after) - set(before), set(before) - set(after)
    if len(added) > len(displaced):
        label = "business_omission"
    elif len(added) < len(displaced):
        label = "fewer_business_completions"
    elif added:
        label = "target_swap"
    else:
        label = "confirmation_only" if confirmation else "no_terminal_change"
    return verdict(label, reason, added, displaced)


def budget_stops(row):
    return "unfunded" in row["stop"]


def order_risk(record):
    for step in record["dispatch"]:
        selected = step["target"]
        for other in step["queue"]:
            target = other["target"]
            if other["receipt_covered"] and target != selected:
                quoted = (other["with_receipt_floor"], other["position"])
                selected_row = next(row for row in step["queue"] if row["target"] == selected)
                selected_quote = (selected_row["with_receipt_floor"], selected_row["position"])
                if quoted != (other["floor"], other["position"]) and quoted < selected_quote:
                    return True
    return False


def opportunities(record, index, credit, retries):
    choices = []
    for step in record["dispatch"]:
        if step["stop"] == "unfunded_entry" and (index is None or step["start"] > index):
            if step["floor"] <= step["balance"] + credit:
                choices.append((step["target"], step["floor"], "entry"))
        elif retries:
            for gate in step["gates"]:
                if (index is None or gate["call_index"] > index) and gate["needed"] <= gate["remaining"] + credit:
                    choices.append((step["target"], gate["needed"], "retry" if gate["after_reject"] and not gate.get("lower_bound_only") else "branch"))
    return list(dict.fromkeys(choices))


def static_plan(record, question, credit):
    done = set(record["completed"])
    alternate = set()
    first_queue = record["dispatch"][0]["queue"]
    observed = {step["target"]: step for step in record["dispatch"]}
    balance = record["initial_budget"] + (credit if question == "fee" else 0)
    use_receipt = question == "total"
    cost_key = "with_receipt_floor" if use_receipt else "floor"
    ordered = sorted(first_queue, key=lambda q: (
        q[cost_key] if record["mode"] == "low_cost" else 0, q["position"]))
    for row in ordered:
        target = row["target"]
        step = observed[target]
        actual_cost = step["balance"] - step["remaining"]
        saving = row["floor"] - row[cost_key]
        price = max(row[cost_key], actual_cost - saving)
        if price <= balance:
            alternate.add(target)
            balance -= price
    return from_sets(done, alternate, "static_allocation")


def predict(record, question):
    done = set(record["completed"])
    scope = set(record["scope"])
    index = record["same_value_read"]
    credit = record["same_value_cost"]
    stops = any(budget_stops(step) for step in record["dispatch"])
    all_done = len(done) == len(record["targets"])
    d0 = verdict("business_omission", "budget_stop") if stops else verdict(
        "no_terminal_change" if scope <= done or all_done else "undecided", "direct_and_count")
    basic = opportunities(record, index, credit, False) if index is not None else []
    d1 = verdict("business_omission", "threshold_recovery", [basic[0][0]]) if basic else verdict(
        "no_terminal_change", "no_late_entry_crossing")
    risk = question == "total" and record["mode"] == "low_cost" and order_risk(record)
    retry = opportunities(record, index, credit, True) if index is not None else []
    handled = {c[0] for c in retry}
    confirm_price = record["blocked_optional_post_publish_price"]
    if all_done and record["published"] and confirm_price is not None and index is not None and (
        record["remaining"] + credit >= confirm_price
    ):
        strong = verdict("confirmation_only", "post_publish_confirm_only")
    elif risk and (stops or not all_done):
        strong = verdict("undecided", "dispatch_shift_ambiguous")
    elif question == "total" and (record["focal_reread_different"] or record["focal_prior_rejected"]):
        strong = verdict("undecided", "stale_receipt_or_retry")
    elif len(handled) > 1 or any(c[2] == "branch" for c in retry) or (
        retry and credit > min(c[1] for c in retry)
    ):
        strong = verdict("undecided", "multi_branch_path_change")
    elif handled:
        strong = verdict("business_omission", "retry_crossing" if retry[0][2] == "retry"
                         else "threshold_recovery", handled)
    elif all_done and question == "total" and risk:
        direct_floors = sum(q["with_receipt_floor"] for q in record["dispatch"][0]["queue"])
        strong = verdict("no_terminal_change", "slack_budget") if (
            record["remaining"] >= direct_floors
        ) else verdict("undecided", "dispatch_shift_ambiguous")
    elif question == "total" and not all_done and index is None and any(
        q["receipt_covered"] and q["floor"] > q["with_receipt_floor"] and q["with_receipt_floor"] <= step["balance"]
        for step in record["dispatch"] for q in step["queue"] if q["target"] == step["target"]
    ):
        strong = verdict("undecided", "receipt_enables_unattempted_route")
    elif question == "total" and record["focal_receipt_used_in_loss"] and index is None:
        strong = verdict("undecided", "same_value_charge_unobserved")
    else:
        strong = verdict("no_terminal_change", "slack_budget" if all_done else "no_visible_crossing")
    aggressive = static_plan(record, question, credit) if strong["predicted_class"] == "undecided" else strong
    return dict(zip(DIAGNOSTICS, (d0, d1, strong, aggressive), strict=True))

