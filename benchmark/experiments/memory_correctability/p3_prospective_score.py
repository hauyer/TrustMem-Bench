"""Score pre-locked single-track predictions against native interventions."""
import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path

from p3_prospective_audit_increment import read, write
from p3_prospective_diagnosis import DIAGNOSTICS

EMPTY = "no_terminal_change"


def key(row):
    return row["workflow"], row["day"], row["mode"]


def signature(v):
    return (v["predicted_class"], tuple(v["predicted_added_targets"]), tuple(v["predicted_displaced_targets"]))


def record(stats, expected, candidate):
    label, added, lost = signature(expected)
    estimate, guess_added, guess_lost = signature(candidate)
    exact = signature(candidate)==signature(expected)
    stats["exact"] += exact
    if estimate=="undecided":
        stats["undecided"]+=1
    else:
        stats["confident_errors"]+=not exact
        stats["false_negative"]+=label!=EMPTY and estimate==EMPTY
        stats["false_positive"]+=label in (EMPTY,"confirmation_only") and estimate=="business_omission"
        stats["wrong_target_identity"]+=(
            estimate!=EMPTY and bool(added or lost) and (added,lost)!=(guess_added,guess_lost)
        )
    return exact


def sum_cost(costs, timing, arms):
    return sum(costs[a]["calls"] for a in arms), sum(costs[a]["restorations"] for a in arms), sum(
        timing[a] for a in arms)


def stats_for(items):
    tally = {diag:Counter({k:0 for k in (
        "exact","confident_errors","undecided","false_negative","false_positive","wrong_target_identity"
    )}) for diag in DIAGNOSTICS}
    overall=Counter()
    causes=Counter()
    cost=defaultdict(float)
    histories=set()
    actual_classes=Counter()
    for row, question, expected, preds, ms in items:
        histories.add(row["workflow"])
        label, added, dropped=signature(expected)
        actual_classes[label]+=1
        overall["changed_verdicts"]+=label!=EMPTY
        overall["business_changes"]+=bool(added or dropped)
        overall["outside_scope_business_changes"]+=bool((set(added)|set(dropped))-set(row["scope"]))
        overall["ambiguity_checked"]+= (
            bool(row["receipt_order_interaction"] is not None) if question=="total" else label!=EMPTY)
        overall["ambiguity_with_witness"]+= (
            bool(row["receipt_order_interaction"]) if question=="total" else bool(row["equal_charge_alternatives"]))
        overall["cross_scope_alternative_charges"]+=sum(
            a["outside_scope"] for a in row["equal_charge_alternatives"]) if question=="fee" else 0
        exact={d:record(tally[d],expected,preds[d]) for d in DIAGNOSTICS}
        uncertain=preds["D2a"]["predicted_class"]=="undecided"
        overall["D2a_undecided_resolved"]+=uncertain
        overall["D2a_confident_errors_corrected"]+=not exact["D2a"] and not uncertain
        overall["D2a_business_verdicts_corrected"]+= label not in (EMPTY,"confirmation_only") and not exact["D2a"]
        overall["D2a_business_relevant_judgments_corrected"]+=not exact["D2a"] and (
            label not in (EMPTY,"confirmation_only") or preds["D2a"]["predicted_class"] not in (
                EMPTY,"confirmation_only","undecided"))
        overall["D2b_errors_corrected"]+=not exact["D2b"]
        overall["selective_exact"]+=uncertain or exact["D2a"]
        overall["selective_confident_errors_remaining"]+=not uncertain and not exact["D2a"]
        if not exact["D2b"]:
            if question=="total" and row["same_prefix_before_dispatch_and_prior_to_designated_charge"] and row["receipt_order_interaction"]:
                cause="pre_charge_dispatch"
            elif preds["D2a"]["reason_code"]=="retry_crossing":
                cause="retry_branch"
            else:
                cause="other"
            causes[cause]+=1
        if question=="total":
            minimal=["archive"]
            full=list(row["costs"])
        else:
            minimal=["fee_only"]
            full=[a for a in row["costs"] if a=="fee_only" or a.startswith("equal_charge_")]
        for scope, arms in (("minimal_full",minimal),("all_controls",full),
                            ("selective",minimal if uncertain else [])):
            calls, restorations, elapsed=sum_cost(row["costs"],ms,arms)
            cost[scope+"_calls"]+=calls
            cost[scope+"_restorations"]+=restorations
            cost[scope+"_wall_ms"]+=elapsed
    n=len(items)
    for k in ("changed_verdicts","business_changes","outside_scope_business_changes","ambiguity_checked",
              "ambiguity_with_witness","cross_scope_alternative_charges","D2a_undecided_resolved",
              "D2a_confident_errors_corrected","D2a_business_verdicts_corrected",
              "D2a_business_relevant_judgments_corrected","D2b_errors_corrected","selective_exact",
              "selective_confident_errors_remaining"):
        overall[k]+=0
    for p in ("minimal_full","all_controls","selective"):
        for k in ("calls","restorations","wall_ms"):
            cost[p+"_"+k]+=0
    corrected=overall["D2a_undecided_resolved"]+overall["D2a_confident_errors_corrected"]
    real=overall["D2a_business_relevant_judgments_corrected"]
    ratio=lambda a,b:a/b if b else None
    return dict(independent_histories=len(histories), n=n, observed_classes=dict(actual_classes),
                diagnostics={n:dict(t, exact_accuracy=ratio(t["exact"],len(items))) for n,t in tally.items()},
                full_replay_resolutions=n, selective_accuracy=ratio(overall["selective_exact"],n),
                residual_ambiguity_rate=ratio(overall["ambiguity_with_witness"],overall["ambiguity_checked"]),
                saved_replay_call_fraction=1-cost["selective_calls"]/cost["minimal_full_calls"] if cost["minimal_full_calls"] else None,
                **dict(overall), D2b_error_details=dict(causes), costs=dict(cost),
                extra_calls_per_correction=ratio(cost["minimal_full_calls"],corrected),
                extra_ms_per_correction=ratio(cost["minimal_full_wall_ms"],corrected),
                extra_calls_per_business_correction=ratio(cost["minimal_full_calls"],real),
                extra_ms_per_business_correction=ratio(cost["minimal_full_wall_ms"],real))


def build(root):
    batch_data=read(root/"RESULT.json")["rows"]
    locked={key(b):b["answers"] for b in read(root/"DIAGNOSIS_BEFORE_TRUTH.json")}
    timing={key(t):t["arms_ms"] for t in read(root/"REPLAY_TIMINGS.json")}
    groups=defaultdict(list)
    excluded=Counter()
    cohort=read(root/"COHORT_FREEZE.json")["selected"]
    for scope in [i["workflow"] for i in cohort]+["ALL"]:
        for mode in ("ordered","low_cost","ALL"):
            for question in ("total","fee"):
                groups[scope,mode,question]
    for row in batch_data:
        wf, _, mode=key(row)
        for q in ("total","fee"):
            tags=[(wf,mode,q),(wf,"ALL",q),("ALL",mode,q),("ALL","ALL",q)]
            if row["status"]=="eligible" and row[q] is not None:
                item=row,q,row[q],locked[key(row)][q],timing[key(row)]
                for tag in tags:
                    groups[tag].append(item)
            else:
                for tag in tags:
                    excluded[(*tag,"ineligible_batch" if row["status"]!="eligible" else
                              "no_same_value_charge" if row["same_value_read"] is None else
                              "charge_control_not_validated")]+=1
    res=[]
    for (wf,mode,q),items in sorted(groups.items()):
        exclusion=dict((reason,excluded[wf,mode,q,reason]) for reason in (
            "ineligible_batch","no_same_value_charge","charge_control_not_validated"))
        res.append(dict(workflow=wf,mode=mode,question=q,**exclusion,**stats_for(items)))
    attention=dict(keep_archive_mismatches=[key(row) for row in batch_data
                                           if row.get("keep_archive_identical") is False],
                   sham_terminal_mismatches=[key(row) for row in batch_data
                                            if row.get("sham_terminal_identical") is False],
                   sham_trace_mismatches=[key(row) for row in batch_data
                                         if row.get("sham_trace_identical") is False],
                   sham_unavailable=sum(row.get("sham_terminal_identical") is None for row in batch_data
                                        if row["status"]=="eligible"),
                   invalid_equal_charge_branches=sum(not valid for row in batch_data
                       for arm,valid in row.get("dose_validated",{}).items() if arm.startswith("equal_charge_")))
    return dict(summary=res, control_attention=attention, independent_histories=len(cohort),
                audited_comparison_cells=len(batch_data), paid_model_calls=0, api_usd=0,
                replay_is_reference=True, costs_all_controls_nonadditive_across_questions=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("root",type=Path)
    a=p.parse_args()
    data=build(a.root)
    write(a.root/"INCREMENT_SUMMARY.json",data)
    rows=[]
    for r in data["summary"]:
        row={k:v for k,v in r.items() if not isinstance(v,dict)}
        for d,columns in r["diagnostics"].items():
            row.update({d+"_"+k:v for k,v in columns.items()})
        row.update(r["costs"])
        rows.append(row)
    with (a.root/"table4_prospective_audit_increment.csv").open("x",encoding="utf8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__=="__main__":
    main()

