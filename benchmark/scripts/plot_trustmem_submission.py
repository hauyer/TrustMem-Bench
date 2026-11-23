"""Render publication figures from the frozen TrustMem-Bench evidence."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/research_decisions"
RUNS = ROOT / "artifacts/p4_all_results/p4_runs"
EXTENSION = ROOT / "artifacts/p4b_all_results/p4b_runs"
P4 = EVIDENCE / "20261121-p4-posthoc-manuscript-audit"
P3 = EVIDENCE / "20261120-p3-prospective-audit-increment-v1"
ORDER = EVIDENCE / "20261121-review-readiness/inventory/FORM_ORDER_CROSS.csv"
MODELS = ("Qwen3-32B", "Llama-3.3-70B", "Mistral-Small-24B")
INK, BLUE, TEAL, RUST, MUTE = "#172837", "#245889", "#18786e", "#a2402c", "#526472"
PALE, GRID = "#eff4f7", "#d8e2e9"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Arial"], "font.size": 8,
    "pdf.fonttype": 42, "svg.fonttype": "none", "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
})


def read(path):
    return json.loads(path.read_bytes())


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))



def forms_t14():
    comparison = []
    context = set()
    for slot, name in zip("BC", MODELS[1:]):
        run, = RUNS.glob(f"slot{slot}_*_main")
        case = run / "forms-T14"

        def episode(arm):
            return read(case / f"native__{arm}/EPISODE.json")

        keep, remove, fee = (episode(a) for a in ("keep_r0", "remove", "fee_only"))
        assert all(ep["status"] == "ok" and ep["grade_valid"] for ep in (keep, remove, fee))
        assert all(episode(a)["completed"] == keep["completed"] for a in ("keep_r1", "keep_r2", "sham"))
        charge = fee["fee_only_control"]
        assert charge["nonaccounting_match"]
        context.add((keep["focal_key"], keep["initial_budget"], keep["total_targets"], charge["waived_cost"]))
        comparison.append(dict(model=name, keep=keep["completed_count"], remove=remove["completed_count"],
                               fee_only=fee["completed_count"], keep_matches_remove=set(keep["completed"]) == set(remove["completed"]),
                               fee_matches_remove=set(fee["completed"]) == set(remove["completed"])))
    (_, budget, requests, charge), = context
    return dict(budget=budget, requests=requests, charge=charge, model_outcomes=comparison)


def railway_outcomes():
    results = []
    for slot, name in zip("ABC", MODELS):
        run, = EXTENSION.glob(f"p4b_slot{slot}_*_main")
        cases = sorted(run.glob("railway_ticketing-T*"))
        assert len(cases) == 8
        totals = Counter()
        for case in cases:
            assert read(case/"native__sham/EPISODE.json")["status"] == "ineligible_no_sham_key"
            for arm, label in (("keep_r0", "keep"), ("remove", "remove"), ("archive", "archive")):
                episode = read(case / f"native__{arm}/EPISODE.json")
                assert episode["status"] == "ok" and episode["grade_valid"]
                totals[label] += episode["completed_count"]
                if arm == "keep_r0":
                    totals["requests"] += episode["total_targets"]
        results.append(dict(name=name, **totals))
    return results

def collect():
    controls = read_csv(EVIDENCE / "20261121-manuscript-audit-tables/P3_NATIVE_CONTROLS.csv")
    pooled = {k: int(v) for k, v in controls[0].items() if k != "cohort"}
    admission = read_csv(EVIDENCE / "20261121-manuscript-audit-tables/P3_ORDERED_ADMISSION.csv")
    loss = next(row for row in read(P3 / "OBSERVE_LOSS.json")
                if (row["workflow"], row["day"], row["mode"]) == ("backup_recovery", 8, "ordered"))
    fee = read(P3 / "REPLAY/backup_recovery-T08-ordered.json")["fee_only"]
    backup = dict(waived=loss["calls"][0]["charged"] - fee["calls"][0]["charged"],
                  loss_balance=loss["dispatch"][2]["balance"], entry=fee["dispatch"][2]["floor"],
                  fee_balance=fee["dispatch"][2]["balance"],
                  later_balance=fee["dispatch"][3]["balance"], later_floor=fee["dispatch"][3]["floor"],
                  loss_completions=len(loss["completed"]), fee_completions=len(fee["completed"]))
    form_examples = []
    forms_dir = EVIDENCE / "20261119-c93-oracle-archive-path-v1"
    for day in ("T11", "T13"):
        ordered = read(forms_dir / day / "CONTROL_ordered.json")
        low = read(forms_dir / day / "CONTROL_low_cost.json")
        assert ordered["waive_context"]["completed"] == ordered["archive"]["completed"]
        assert len(low["loss"]["completed"]) == len(low["archive"]["completed"])
        assert set(low["loss"]["completed"]) != set(low["archive"]["completed"])
        form_examples.append(dict(day=day, ordered_loss=len(ordered["loss"]["completed"]),
                                  ordered_fee=len(ordered["waive_context"]["completed"]),
                                  low_count=len(low["loss"]["completed"])))
    assert {r["batch"] for r in read_csv(ORDER)} >= {"T11", "T13"}

    rows = {r["slot"]: r for r in read_csv(P4 / "P4_PAPER_TABLE.csv") if r["cohort"] == "released"}
    p4 = []
    for slot, name in zip("ABC", MODELS):
        run = next(RUNS.glob(f"slot{slot}_*_main"))
        combinations = Counter()
        forms = Counter()
        archive_uses = 0
        for workflow, tool, parameter in [
            ("forms", "get_correction_context", "record_ref"),
            ("medical_appointment", "get_patient_scheduling_context", "patient_id"),
        ]:
            for case in sorted(run.glob(f"{workflow}-T*")):
                keep = read(case / "native__keep_r0/EPISODE.json")
                archive = read(case / "native__archive/EPISODE.json")
                reread = any(event["tool"] == tool and event["charged"] > 0
                             and event["arguments"].get(parameter) in keep["direct_targets"]
                             for event in keep["native_log"])
                lookup = bool(archive["archive_lookups"])
                combinations[reread, lookup] += 1
                archive_uses += lookup
                if workflow == "forms":
                    remove = read(case / "native__remove/EPISODE.json")
                    forms.update(keep=keep["completed_count"], remove=remove["completed_count"], archive=archive["completed_count"],
                                 archive_used=lookup)
                    if slot == "A":
                        menu = read(case / "menu__keep_r0/EPISODE.json")
                        forms.update(menu=menu["completed_count"])
        assert sum(combinations.values()) == int(rows[slot]["paired_openings"]) == 12
        p4.append(dict(name=name, slot=slot, reread=sum(combinations[True, k] for k in (True, False)),
                       archive_uses=archive_uses, forms=dict(forms),
                       combinations=[combinations[a, b] for a, b in
                                     ((True, True), (True, False), (False, True), (False, False))],
                       outside=int(rows[slot]["strict_outside_changes"]),
                       fee_added=int(rows[slot]["fee_outside_additions"]),
                       fee_eligible=int(rows[slot]["verified_fee_pairs"])))
    return dict(p3=pooled, fixed_admission=len(admission), backup=backup,
                forms=form_examples, p4=p4, forms_t14=forms_t14(), railway=railway_outcomes())


def label(ax, x, y, value, size=8, bold=False, **opts):
    ax.text(x, y, value, ha=opts.pop("ha", "center"), va=opts.pop("va", "center"),
            fontsize=size, fontweight="bold" if bold else "normal", **opts)


def box(ax, x, y, w, h, title, detail="", fc=PALE, ec=GRID):
    ax.add_patch(FancyBboxPatch((x-w/2, y-h/2), w, h,
                                boxstyle="round,pad=0.008,rounding_size=0.018",
                                fc=fc, ec=ec, lw=0.75))
    label(ax, x, y+(h*.21 if detail else 0), title, 8, True)
    if detail:
        label(ax, x, y-h*.20, detail, 7.05, color=MUTE)


def arrow(ax, a, b, color=MUTE):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-|>", color=color, lw=0.85,
                                                    shrinkA=0, shrinkB=0))


def schematic(ax):
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")


def figure_one(data):
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    fig.subplots_adjust(left=.02, right=.98, top=.99, bottom=.015)
    schematic(ax)
    label(ax, .02, .97, "a   TrustMem-Audit protocol", 10, True, ha="left")
    box(ax, .5, .87, .52, .10, "Same opening (W, G, B)", "world state, pending requests and shared budget")
    xs = (.10, .26, .42, .58, .74, .90)
    ax.plot([xs[0], xs[-1]], [.777, .777], color=MUTE, lw=.8)
    arrow(ax, (.5, .813), (.5, .777))
    for x, title, detail in zip(xs, ("Keep", "Sham", "Remove", "Fee only", "Order cross", "Archive"),
                               ("retain receipt", "drop unrelated", "drop focal", "waive one fee",
                                "fix each order", "offer recovery")):
        arrow(ax, (x, .777), (x, .737))
        box(ax, x, .68, .132, .10, title, detail)
        ax.plot([x, x], [.62, .576], color=MUTE, lw=.8)
    ax.plot([xs[0], xs[-1]], [.576, .576], color=MUTE, lw=.8)
    arrow(ax, (.5, .576), (.5, .544))
    box(ax, .5, .49, .61, .09, "Native execution and adjudication",
        "tool trace, charges, completed request identities")
    if "forms_t14" in data:
        forms_panel(ax, data["forms_t14"])
        return fig
    label(ax, .02, .375, "b   Forms T11 and T13 under two controllers", 10, True, ha="left")
    dates = data["forms"]
    text_fee = "  |  ".join(f"{r['day']}  {r['ordered_loss']}/4 → {r['ordered_fee']}/4" for r in dates)
    text_order = "  |  ".join(f"{r['day']}  {r['low_count']}/4 → {r['low_count']}/4" for r in dates)
    box(ax, .255, .275, .46, .12, "Request order · charge path", "same-value lookup still executes", "#eef6fb", "#b8d3e6")
    box(ax, .745, .275, .46, .12, "Cost priority · dispatch path", "first divergence before designated reread", "#eaf5f1", "#b4d5c8")
    arrow(ax, (.255, .205), (.255, .176), BLUE)
    arrow(ax, (.745, .205), (.745, .176), TEAL)
    box(ax, .255, .113, .46, .11, "Waive 5 units · one more delivery", text_fee, "#eef6fb", "#b8d3e6")
    box(ax, .745, .113, .46, .11, "Restore receipt · different deliveries", text_order, "#eaf5f1", "#b4d5c8")
    label(ax, .5, .014, "The right panel preserves the completion count and changes request identities.",
          7, color=MUTE)
    return fig



def forms_panel(ax, case):
    subtitle = f"Four requests · {case['budget']}-unit budget · {case['charge']}-unit reread"
    label(ax, .02, .375, "b   Forms T14 · same receipt, different repair", 10, True, ha="left")
    label(ax, .02, .313, subtitle, 8, ha="left", color=MUTE)
    positions = (.53, .70, .88)
    for x, title in zip(positions, ("Keep", "Remove", "Fee only")):
        label(ax, x, .249, title, 8, True)
    for row, y in zip(case["model_outcomes"], (.169, .089)):
        label(ax, .02, y, row["model"], 9, True, ha="left")
        for x, arm in zip(positions, ("keep", "remove", "fee_only")):
            count = row[arm]
            salient = arm != "remove" and (
                not row["keep_matches_remove"] if arm == "keep" else not row["fee_matches_remove"]
            )
            box(ax, x, y, .128, .055, f"{count}/{case['requests']}",
                fc="#eaf5f1" if salient else "#f7f9fa", ec="#95bfb2" if salient else GRID)
    label(ax, .02, .019, "Within each model, the completed sets agree across keep repeats and sham.",
          7.35, ha="left", color=MUTE)

def figure_two(data):
    fig, ax = plt.subplots(figsize=(6.6, 4.55))
    fig.subplots_adjust(left=.02, right=.98, top=.992, bottom=.012)
    schematic(ax)
    p = data["p3"]
    b = data["backup"]
    label(ax, .02, .971, "a   Which intervention applies in P3?", 10, True, ha="left")
    box(ax, .5, .886, .46, .091, f"{p['eligible']} batch–controller pairs", "64 openings in five histories")
    for x in (.25, .75):
        arrow(ax, (.5, .833), (x, .782))
    with_fee, changed_fee = p["charge_eligible"], p["changes_with_charge"]
    no_fee, changed_no_fee = p["eligible"]-with_fee, p["changes_without_charge"]
    box(ax, .25, .724, .45, .106, f"{with_fee} with an eligible charge",
        f"{changed_fee} changed  ·  {with_fee-changed_fee} unchanged", "#eef6fb", "#b8d3e6")
    box(ax, .75, .724, .45, .106, f"{no_fee} without an eligible charge",
        f"{changed_no_fee} changed  ·  {no_fee-changed_no_fee} unchanged", "#eaf5f1", "#b4d5c8")
    arrow(ax, (.25, .659), (.25, .625), BLUE)
    arrow(ax, (.75, .659), (.75, .625), TEAL)
    box(ax, .25, .561, .45, .113, f"{changed_fee}/{changed_fee} changed sets reproduced",
        f"Fee waiver matches archive in {p['fee_matches_archive']}/{with_fee}", "#eef6fb", "#b8d3e6")
    crossings = p["order_cross_checked"]
    box(ax, .75, .561, .45, .113, f"{crossings} cost-priority dispatch changes",
        f"{p['order_interaction']}/{crossings} show receipt × order interaction", "#eaf5f1", "#b4d5c8")
    label(ax, .75, .469, f"{data['fixed_admission']} other changes under fixed order involved entry quotes",
          7.15, color=MUTE)
    label(ax, .02, .407, "b   Backup Recovery T08 · waiving a fee reduces completion", 10, True, ha="left")
    label(ax, .025, .303, "Receipt absent", 7.4, True, ha="left")
    label(ax, .025, .164, f"Waive {b['waived']} units", 7.4, True, ha="left")
    step_x = (.30, .505, .715, .917)
    widths = (.152, .154, .166, .102)
    entries = (
        (f"{b['loss_balance']} < {b['entry']}", "skip request A", "A costs 0", "no attempt",
         f"{b['loss_balance']} ≥ {b['later_floor']}", "B completes", f"{b['loss_completions']}/4"),
        (f"{b['fee_balance']} ≥ {b['entry']}", "start request A", f"{b['fee_balance']-b['later_balance']} spent", "native rejection",
         f"{b['later_balance']} < {b['later_floor']}", "B cannot start", f"{b['fee_completions']}/4"),
    )
    for y, content, color in zip((.303, .164), entries, (BLUE, RUST)):
        for index, (x, width) in enumerate(zip(step_x, widths)):
            title, detail = content[2*index:2*index+2] if index < 3 else (content[-1], "done")
            box(ax, x, y, width, .10, title, detail, fc="#f7f9fa", ec=color)
            if index < 3:
                arrow(ax, (x+width/2+.011, y), (step_x[index+1]-widths[index+1]/2-.011, y), color)
    label(ax, .5, .037, "Balances are measured at request entry. A and B are two distinct requests in the batch.",
          7.05, color=MUTE)
    return fig


def rate_panel(ax, title, nums, denoms):
    ax.set_title(title, loc="left", fontweight="bold", fontsize=8.4, pad=5)
    x = range(3)
    bars = ax.bar(x, [a/b for a, b in zip(nums, denoms)], width=.60, color=(BLUE, TEAL, RUST))
    ax.set(ylim=(0,1.23), xticks=list(x), xticklabels=["Qwen", "Llama", "Mistral"],
           yticks=[0,.5,1], yticklabels=["0%", "50%", "100%"])
    ax.tick_params(axis="y", length=2.5, labelsize=8)
    ax.tick_params(axis="x", length=0, labelsize=8)
    ax.bar_label(bars, labels=[f"{a}/{b}" for a,b in zip(nums,denoms)], padding=3, fontsize=8.4)




def completions_panel(ax, title, rows, requests):
    ax.set_title(title, loc="left", fontweight="bold", fontsize=8.4, pad=5)
    x = range(3)
    arms = [("keep", MUTE), ("archive", TEAL)]
    if all("remove" in row for row in rows):
        arms.insert(1, ("remove", "#aba8a4"))
    width = .76 / len(arms)
    for i, (arm, color) in enumerate(arms):
        bars = ax.bar([n+(i-(len(arms)-1)/2)*width for n in x], [r[arm] for r in rows],
                      width=width*.90, label=arm.capitalize(), color=color)
        ax.bar_label(bars, padding=2, fontsize=8.25)
    ax.set(ylim=(0,requests*1.12), yticks=[0,requests//2,requests], xticks=list(x),
           xticklabels=["Qwen", "Llama", "Mistral"])
    ax.set_ylabel(f"Completed / {requests}", fontsize=7)
    ax.tick_params(axis="y", length=2.5, labelsize=8)
    ax.tick_params(axis="x", length=0, labelsize=8)
    ax.legend(loc="upper center", frameon=False, ncol=len(arms), fontsize=7.55,
              handlelength=.9, columnspacing=.55)


def figure_three(data):
    has_railway = "railway" in data
    fig, axes = plt.subplots(3 if has_railway else 2, 2,
                             figsize=(6.6, 5.8 if has_railway else 4.65))
    fig.subplots_adjust(left=.085, right=.976, top=.94, bottom=.09 if has_railway else .235,
                        hspace=.78 if has_railway else .64, wspace=.33)
    p4 = data["p4"]
    rate_panel(axes[0,0],"a   Paid focal read in keep", [r["reread"] for r in p4], [12]*3)
    rate_panel(axes[0,1],"b   Outside-scope change, strict", [r["outside"] for r in p4], [12]*3)
    rate_panel(axes[1,0],"c   Outside gain after fee waiver", [r["fee_added"] for r in p4],
               [r["fee_eligible"] for r in p4])
    completions_panel(axes[1,1], "d   Forms", [r["forms"] for r in p4], 24)
    qwen = p4[0]["forms"]
    if not has_railway:
        fig.text(.085,.12,"Qwen on Forms, same weights", fontsize=8, fontweight="bold")
        fig.text(.085,.07, f"Keep in indexed menu  {qwen['menu']}/24     |     Keep with native tools  {qwen['keep']}/24"
                 "     |     Completed sets match  0/6", fontsize=8, color=MUTE)
        return fig
    railway = data["railway"]
    requests, = {r["requests"] for r in railway}
    completions_panel(axes[2,0], "e   Railway Ticketing", railway, requests)
    ax = axes[2,1]
    ax.set_title("f   Qwen on Forms · same weights", loc="left", fontweight="bold", fontsize=8.4, pad=5)
    bars = ax.bar([0, 1], [qwen["menu"], qwen["keep"]], color=[BLUE, MUTE], width=.52)
    ax.bar_label(bars, padding=2, fontsize=8.25)
    ax.set(xlim=(-.5,1.5), ylim=(0,27), yticks=[0,12,24], xticks=[0,1],
           xticklabels=["Indexed menu", "Native tools"])
    ax.set_ylabel("Completed / 24 in keep", fontsize=7)
    ax.tick_params(axis="y", length=2.5, labelsize=8)
    ax.tick_params(axis="x", length=0, labelsize=8)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data", type=Path, help="Regenerate figures from the distributed aggregate record")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    packaged = ROOT / "tables" / "FIGURE_DATA.json"
    if args.data:
        data = read(args.data)
    elif packaged.is_file() and not RUNS.is_dir():
        data = read(packaged)
    else:
        data = collect()
    (args.out / "FIGURE_DATA.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for title, render in (("fig1_protocol_paths", figure_one), ("fig2_p3_and_backup", figure_two),
                          ("fig3_p4_native_models", figure_three)):
        fig = render(data)
        fig.canvas.draw()
        bounds = [list(ax.get_position().bounds) for ax in fig.axes]
        if len(bounds) > 1:
            assert max(b[2] for b in bounds) - min(b[2] for b in bounds) < 1e-6
            assert max(b[3] for b in bounds) - min(b[3] for b in bounds) < 1e-6
        (args.out / f"{title}.alignment.json").write_text(json.dumps(bounds) + "\n", encoding="utf-8")
        fig.savefig(args.out / f"{title}.pdf", facecolor="white")
        fig.savefig(args.out / f"{title}.svg", facecolor="white")
        fig.savefig(args.out / f"{title}.png", dpi=600, facecolor="white")
        plt.close(fig)


if __name__ == "__main__":
    main()
