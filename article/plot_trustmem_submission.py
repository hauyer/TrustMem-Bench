"""Render publication figures from the frozen TrustMem-Bench evidence."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/research_decisions"
RUNS = ROOT / "artifacts/p4_all_results/p4_runs"
EXTENSION = ROOT / "artifacts/p4b_all_results/p4b_runs"
P4 = EVIDENCE / "20261121-p4-posthoc-manuscript-audit"
P3 = EVIDENCE / "20261120-p3-prospective-audit-increment-v1"
ORDER = EVIDENCE / "20261121-review-readiness/inventory/FORM_ORDER_CROSS.csv"
MODELS = ("Qwen3-32B", "Llama-3.3-70B", "Mistral-Small-24B")

# Top-venue academic palette (WCAG 2.2 AA & grayscale-staircase verified)
INK = "#1E293B"
DARK_INK = "#0F172A"
MUTED = "#475569"
BORDER = "#94A3B8"
GRID = "#E2E8F0"
BG_PANEL = "#F8FAFC"

NAVY = "#12344D"
NAVY_FILL = "#EDF4F8"
NAVY_EDGE = "#5B89A8"

STEEL = "#2F6690"
SAGE = "#1F6F50"
SAGE_LIGHT = "#4DA17F"
SAGE_FILL = "#ECF7F2"
SAGE_EDGE = "#4DA17F"

AMBER = "#9A5608"
AMBER_FILL = "#FDF6E7"
AMBER_EDGE = "#C67B17"

ORANGE = "#8B2814"
CRIMSON = "#B23A48"
CRIMSON_FILL = "#FDF2F3"
CRIMSON_EDGE = "#D4727D"

SLATE_FILL = "#F1F5F9"
SLATE_EDGE = "#94A3B8"
BAR_KEEP = NAVY
BAR_REMOVE = "#E2E8F0"
BAR_ARCHIVE = AMBER

# Physical width of Springer sn-jnl text block (369 pt = 5.125 in -> 1:1 native scale)
WIDTH_PT = 369.0
WIDTH_IN = WIDTH_PT / 72.0

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "mathtext.fontset": "stix",
    "font.size": 8.2,
    "axes.titlesize": 8.6,
    "axes.labelsize": 8.2,
    "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0,
    "legend.fontsize": 7.8,
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
    "text.color": INK,
    "axes.edgecolor": "#475569",
    "axes.linewidth": 0.75,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.unicode_minus": True,
})


def read(path):
    return json.loads(path.read_bytes())


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def forms_t14():
    comparison = []
    context = set()
    raw_sets = []
    direct_sets = set()
    for slot, name in zip("BC", MODELS[1:]):
        run, = RUNS.glob(f"slot{slot}_*_main")
        case = run / "forms-T14"

        def episode(arm):
            return read(case / f"native__{arm}/EPISODE.json")

        keep, remove, fee = (episode(a) for a in ("keep_r0", "remove", "fee_only"))
        assert all(ep["status"] == "ok" and ep["grade_valid"] for ep in (keep, remove, fee))
        assert all(episode(a)["completed"] == keep["completed"] for a in ("keep_r1", "keep_r2", "sham"))
        raw_sets.append({arm: set(record["completed"]) for arm, record in
                         (("keep", keep), ("remove", remove), ("fee_only", fee))})
        direct_sets.update(tuple(sorted(record["direct_targets"])) for record in (keep, remove, fee))
        charge = fee["fee_only_control"]
        assert charge["nonaccounting_match"]
        context.add((keep["focal_key"], keep["initial_budget"], keep["total_targets"], charge["waived_cost"]))
        comparison.append(dict(
            model=name,
            keep=keep["completed_count"],
            remove=remove["completed_count"],
            fee_only=fee["completed_count"],
            keep_matches_remove=set(keep["completed"]) == set(remove["completed"]),
            fee_matches_remove=set(fee["completed"]) == set(remove["completed"]),
        ))
    (_, budget, requests, charge), = context
    (direct,), = direct_sets
    universe = set().union(*(ids for row in raw_sets for ids in row.values()))
    assert direct in universe and len(universe) == requests
    request_order = [direct, *sorted(universe - {direct})]
    for row, arms in zip(comparison, raw_sets):
        row["request_mask"] = {arm: [key in completed for key in request_order]
                               for arm, completed in arms.items()}
        assert all(sum(mask) == row[arm] for arm, mask in row["request_mask"].items())
    return dict(budget=budget, requests=requests, charge=charge, model_outcomes=comparison)


def railway_outcomes():
    results = []
    for slot, name in zip("ABC", MODELS):
        run, = EXTENSION.glob(f"p4b_slot{slot}_*_main")
        cases = sorted(run.glob("railway_ticketing-T*"))
        assert len(cases) == 8
        totals = Counter()
        for case in cases:
            assert read(case / "native__sham/EPISODE.json")["status"] == "ineligible_no_sham_key"
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
    assert loss["dispatch"][3]["balance"] == loss["dispatch"][2]["balance"]
    backup = dict(
        waived=loss["calls"][0]["charged"] - fee["calls"][0]["charged"],
        loss_balance=loss["dispatch"][2]["balance"],
        entry=fee["dispatch"][2]["floor"],
        fee_balance=fee["dispatch"][2]["balance"],
        later_balance=fee["dispatch"][3]["balance"],
        later_floor=fee["dispatch"][3]["floor"],
        loss_completions=len(loss["completed"]),
        fee_completions=len(fee["completed"]),
    )
    form_examples = []
    forms_dir = EVIDENCE / "20261119-c93-oracle-archive-path-v1"
    for day in ("T11", "T13"):
        ordered = read(forms_dir / day / "CONTROL_ordered.json")
        low = read(forms_dir / day / "CONTROL_low_cost.json")
        assert ordered["waive_context"]["completed"] == ordered["archive"]["completed"]
        assert len(low["loss"]["completed"]) == len(low["archive"]["completed"])
        assert set(low["loss"]["completed"]) != set(low["archive"]["completed"])
        form_examples.append(dict(
            day=day,
            ordered_loss=len(ordered["loss"]["completed"]),
            ordered_fee=len(ordered["waive_context"]["completed"]),
            low_count=len(low["loss"]["completed"]),
        ))
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
                reread = any(
                    event["tool"] == tool and event["charged"] > 0
                    and event["arguments"].get(parameter) in keep["direct_targets"]
                    for event in keep["native_log"]
                )
                lookup = bool(archive["archive_lookups"])
                combinations[reread, lookup] += 1
                archive_uses += lookup
                if workflow == "forms":
                    remove = read(case / "native__remove/EPISODE.json")
                    forms.update(
                        keep=keep["completed_count"],
                        remove=remove["completed_count"],
                        archive=archive["completed_count"],
                        archive_used=lookup,
                    )
                    if slot == "A":
                        menu = read(case / "menu__keep_r0/EPISODE.json")
                        forms.update(menu=menu["completed_count"])
        assert sum(combinations.values()) == int(rows[slot]["paired_openings"]) == 12
        p4.append(dict(
            name=name,
            slot=slot,
            reread=sum(combinations[True, k] for k in (True, False)),
            archive_uses=archive_uses,
            forms=dict(forms),
            combinations=[combinations[a, b] for a, b in
                          ((True, True), (True, False), (False, True), (False, False))],
            outside=int(rows[slot]["strict_outside_changes"]),
            fee_added=int(rows[slot]["fee_outside_additions"]),
            fee_eligible=int(rows[slot]["verified_fee_pairs"]),
        ))
    return dict(
        p3=pooled,
        fixed_admission=len(admission),
        backup=backup,
        forms=form_examples,
        p4=p4,
        forms_t14=forms_t14(),
        railway=railway_outcomes(),
    )


def _rbox(ax, x, y, w, h, *, fc="white", ec=BORDER, lw=0.8, r=3.0, ls="-", z=2):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls, zorder=z,
    )
    ax.add_patch(patch)
    return patch


def _arrow(ax, x1, y1, x2, y2, *, color=MUTED, lw=0.85, z=3):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>,head_length=3.6,head_width=2.2",
        color=color, linewidth=lw, shrinkA=0, shrinkB=0, zorder=z,
    ))


def _txt(ax, x, y, s, *, size=8.2, color=INK, ha="left", va="center",
         bold=False, serif=False, z=5):
    return ax.text(
        x, y, s, fontsize=size, color=color, ha=ha, va=va,
        family="STIXGeneral" if serif else "DejaVu Sans",
        weight="bold" if bold else "normal", zorder=z,
    )


def _style_axis(ax, *, grid_axis="y"):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.75)
    ax.spines["bottom"].set_linewidth(0.75)
    ax.spines["left"].set_color("#475569")
    ax.spines["bottom"].set_color("#475569")
    ax.tick_params(direction="out", length=3.0, width=0.7, color="#475569", pad=2.5)
    ax.set_axisbelow(True)
    if grid_axis:
        ax.grid(axis=grid_axis, linestyle="--", linewidth=0.55, color=GRID, alpha=0.95)


def figure_one(data):
    """Top-venue system protocol pipeline (a) + Forms T14 teaser request-tile matrix (b)."""
    case = data.get("forms_t14")
    height_pt = 360.0 if case else 258.0
    fig = plt.figure(figsize=(WIDTH_IN, height_pt / 72.0), facecolor="white")
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set(xlim=(0.0, WIDTH_PT), ylim=(height_pt, 0.0))
    ax.axis("off")

    # ---------------- Panel (a): Left -> Center -> Right Protocol Pipeline ----------------
    _txt(ax, 3, 10.5, "(a) TrustMem-Audit matched counterfactual replay protocol",
         size=9.8, bold=True, serif=True)

    # Left stage: Saved Opening box
    x_in, y_in, w_in, h_in = 3, 52, 74, 82
    _rbox(ax, x_in, y_in, w_in, h_in, fc=NAVY_FILL, ec=NAVY_EDGE, lw=0.95, r=3.5)
    _rbox(ax, x_in, y_in, w_in, 19, fc=NAVY, ec=NAVY, lw=0.5, r=3.0, z=2.5)
    ax.add_patch(Rectangle((x_in, y_in + 13), w_in, 6, facecolor=NAVY, edgecolor="none", zorder=2.5))
    _txt(ax, x_in + w_in / 2, y_in + 9.8, "Saved opening", size=8.0, color="white", ha="center", bold=True)
    _txt(ax, x_in + 6, y_in + 31, r"World state $W$", size=7.8, color=INK)
    _txt(ax, x_in + 6, y_in + 46, r"Requests $G$", size=7.8, color=INK)
    _txt(ax, x_in + 6, y_in + 59, r"Direct $M \subseteq G$", size=7.8, color=MUTED)
    _txt(ax, x_in + 6, y_in + 73, r"Shared budget $B$", size=7.8, color=INK)

    # Center stage: 3 grouped intervention bands
    x_mid, w_mid = 94, 175
    groups = [
        ("Receipt toggles", 24, 62, SLATE_FILL, SLATE_EDGE, MUTED, [
            ("Keep", "retain historical receipt"),
            ("Sham", "drop unrelated receipt"),
            ("Remove", r"drop focal ($S_{\mathrm{loss}}$)"),
        ]),
        ("Causal repair probes", 91, 44, AMBER_FILL, AMBER_EDGE, AMBER, [
            ("Fee only", "waive one reread charge"),
            ("Order cross", "fix observed dispatch order"),
        ]),
        ("Recovery", 140, 26, SAGE_FILL, SAGE_EDGE, SAGE, [
            ("Archive", "restore at entry / lookup"),
        ]),
    ]

    bus_l = 85.5
    bus_r = 277.5
    y_in_mid = y_in + h_in / 2.0
    ax.plot([x_in + w_in, bus_l], [y_in_mid, y_in_mid], color=MUTED, lw=0.85, zorder=2)

    group_centers = []
    for g_title, gy, gh, gfc, gec, gcol, items in groups:
        _rbox(ax, x_mid, gy, w_mid, gh, fc=gfc, ec=gec, lw=0.85, r=3.0)
        _txt(ax, x_mid + w_mid - 5, gy + 7.5, g_title, size=7.5, color=gcol, ha="right", bold=True)
        n = len(items)
        top_pad = 17.5 if n > 1 else 14.5
        step = 15.8
        for idx, (arm, desc) in enumerate(items):
            yy = gy + top_pad + idx * step if n > 1 else gy + gh / 2.0 + 3.2
            _txt(ax, x_mid + 6, yy, arm, size=8.0, color=INK, bold=True)
            _txt(ax, x_mid + 63, yy, desc, size=7.8, color=MUTED)
        cy = gy + gh / 2.0
        group_centers.append(cy)
        _arrow(ax, bus_l, cy, x_mid - 1.0, cy, color=MUTED, lw=0.85)
        ax.plot([x_mid + w_mid, bus_r], [cy, cy], color=MUTED, lw=0.85, zorder=2)

    ax.plot([bus_l, bus_l], [group_centers[0], group_centers[-1]], color=MUTED, lw=0.85, zorder=2)
    ax.plot([bus_r, bus_r], [group_centers[0], group_centers[-1]], color=MUTED, lw=0.85, zorder=2)

    # Right stage: route cleanly INTO Native replay -> arrow down -> Adjudication
    x_out, w_out = 287, 79
    _arrow(ax, bus_r, 59.5, x_out - 1.0, 59.5, color=MUTED, lw=0.85)

    # Top-right box: Native replay
    _rbox(ax, x_out, 36, w_out, 47, fc=BG_PANEL, ec=NAVY_EDGE, lw=0.9, r=3.5)
    _rbox(ax, x_out, 36, w_out, 17, fc=STEEL, ec=STEEL, lw=0.5, r=3.0, z=2.5)
    ax.add_patch(Rectangle((x_out, 47), w_out, 6, facecolor=STEEL, edgecolor="none", zorder=2.5))
    _txt(ax, x_out + w_out / 2, 44.5, "Native replay", size=7.9, color="white", ha="center", bold=True)
    _txt(ax, x_out + w_out / 2, 62, "Real tools & ledger", size=7.7, color=INK, ha="center")
    _txt(ax, x_out + w_out / 2, 74, "Native grader", size=7.7, color=MUTED, ha="center")

    _arrow(ax, x_out + w_out / 2, 83, x_out + w_out / 2, 95, color=NAVY, lw=0.95)

    # Bottom-right box: Set Adjudication
    _rbox(ax, x_out, 96, w_out, 62, fc=NAVY_FILL, ec=NAVY_EDGE, lw=0.9, r=3.5)
    _rbox(ax, x_out, 96, w_out, 17, fc=NAVY, ec=NAVY, lw=0.5, r=3.0, z=2.5)
    ax.add_patch(Rectangle((x_out, 107), w_out, 6, facecolor=NAVY, edgecolor="none", zorder=2.5))
    _txt(ax, x_out + w_out / 2, 104.5, "Adjudication", size=7.9, color="white", ha="center", bold=True)
    _txt(ax, x_out + 6, 123, r"Gain: $S_j \setminus S_{\mathrm{loss}}$", size=7.7, color=INK)
    _txt(ax, x_out + 6, 136, r"Loss: $S_{\mathrm{loss}} \setminus S_j$", size=7.7, color=INK)
    _txt(ax, x_out + 6, 149, r"Outside: $\cap\,(G\setminus M)$", size=7.7, color=NAVY, bold=True)

    # Clean horizontal separator between (a) and (b)
    ax.plot([3, WIDTH_PT - 3], [176, 176], color=BORDER, lw=0.65, ls="-", zorder=1)

    if case is None:
        _txt(ax, 3, 190, "(b) Forms under two fixed controllers", size=9.8, bold=True, serif=True)
        for i, row in enumerate(data["forms"]):
            y = 212 + 22 * i
            _txt(ax, 6, y, row["day"], size=8.2, bold=True)
            _txt(ax, 52, y, f"Request order: {row['ordered_loss']}/4 → {row['ordered_fee']}/4", size=8.0)
            _txt(ax, 205, y, f"Cost priority: {row['low_count']}/4 → {row['low_count']}/4", size=8.0)
        return fig

    # ---------------- Panel (b): Forms T14 Teaser Case Study ----------------
    rows = case["model_outcomes"]
    _txt(ax, 3, 190, "(b) Forms T14: same receipt and 5-unit reread fee, opposite repairs",
         size=9.8, bold=True, serif=True)
    _txt(ax, 3, 204.5,
         f"Shared opening: {case['requests']} requests  |  {case['budget']}-unit budget  |  "
         f"{case['charge']}-unit reread  |  keep repeats & sham agree",
         size=7.6, color=MUTED)

    arm_labels = [("keep", "Keep"), ("remove", "Remove"), ("fee_only", "Fee only")]
    card_specs = [
        (3, 178, rows[0], "Only fee waiver adds outside R3", AMBER),
        (188, 178, rows[1], "Only receipt replaces R1 with R2–R4", SAGE),
    ]

    for cx, cw, row, takeaway, foot_col in card_specs:
        cy, ch = 215, 121
        _rbox(ax, cx, cy, cw, ch, fc=BG_PANEL, ec=BORDER, lw=0.8, r=3.5)
        # Clean centered model title header
        _rbox(ax, cx, cy, cw, 18, fc="#E8EEF5", ec=BORDER, lw=0.6, r=3.0, z=2.5)
        ax.add_patch(Rectangle((cx + 0.5, cy + 12), cw - 1.0, 6, facecolor="#E8EEF5", edgecolor="none", zorder=2.5))
        _txt(ax, cx + cw / 2, cy + 9.2, row["model"], size=8.8, color=NAVY, ha="center", bold=True, serif=True)

        # Column headers: R1 R2 R3 R4 Done
        col_xs = [cx + 56, cx + 79, cx + 102, cx + 125]
        done_x = cx + 157
        for i, rx in enumerate(col_xs):
            _txt(ax, rx, cy + 27, f"R{i + 1}", size=7.8, color=NAVY if i == 0 else MUTED,
                 ha="center", bold=(i == 0))
        _txt(ax, done_x, cy + 27, "Done", size=7.8, color=MUTED, ha="center")
        ax.plot([cx + 6, cx + cw - 6], [cy + 34, cy + 34], color=GRID, lw=0.7, zorder=3)

        for r_idx, (arm_key, arm_lbl) in enumerate(arm_labels):
            ry = cy + 46 + r_idx * 22
            changed_arm = (
                (arm_key == "keep" and not row["keep_matches_remove"])
                or (arm_key == "fee_only" and not row["fee_matches_remove"])
            )
            if changed_arm:
                hl_fc = SAGE_FILL if arm_key == "keep" else AMBER_FILL
                hl_ec = SAGE_EDGE if arm_key == "keep" else AMBER_EDGE
                _rbox(ax, cx + 4, ry - 9, cw - 8, 18, fc=hl_fc, ec=hl_ec, lw=0.7, r=2.5, z=2.8)

            _txt(ax, cx + 8, ry, arm_lbl, size=7.9, color=INK, bold=changed_arm)
            mask = row["request_mask"][arm_key]
            for i, (rx, done) in enumerate(zip(col_xs, mask)):
                tw, th = 16.8, 12.2
                if done:
                    if i == 0:
                        tile_fc, tile_ec, tile_fg = NAVY, NAVY, "white"
                    elif arm_key == "keep":
                        tile_fc, tile_ec, tile_fg = SAGE_LIGHT, SAGE, DARK_INK
                    else:
                        tile_fc, tile_ec, tile_fg = AMBER, AMBER, "white"
                    _rbox(ax, rx - tw / 2, ry - th / 2, tw, th, fc=tile_fc, ec=tile_ec, lw=0.65, r=2.0, z=3.5)
                    _txt(ax, rx, ry + 0.3, f"R{i + 1}", size=7.6, color=tile_fg, ha="center", bold=True, z=4.5)
                else:
                    _rbox(ax, rx - tw / 2, ry - th / 2, tw, th, fc="white", ec="#CBD5E1",
                          lw=0.7, ls="--", r=2.0, z=3.5)
                    _txt(ax, rx, ry + 0.2, "–", size=7.6, color="#94A3B8", ha="center", z=4.5)

            cnt_col = (SAGE if arm_key == "keep" else AMBER) if changed_arm else INK
            _txt(ax, done_x, ry, f"{row[arm_key]}/{case['requests']}",
                 size=8.1, color=cnt_col, ha="center", bold=True, z=4.5)

        # Clean takeaway strip at bottom of card
        ax.plot([cx + 6, cx + cw - 6], [cy + 103, cy + 103], color=GRID, lw=0.7, zorder=3)
        _txt(ax, cx + cw / 2, cy + 112, takeaway, size=7.6, color=foot_col, ha="center", bold=True)

    # Bottom compact legend strip (generous margins inside [3, 366])
    ly = 349.0
    legend_items = [
        (6, NAVY, NAVY, "-", "R1 (in scope)"),
        (82, SAGE_LIGHT, SAGE, "-", "R2–R4 (keep)"),
        (165, AMBER, AMBER, "-", "R3 added (waiver)"),
        (272, "white", "#94A3B8", "--", "Not delivered"),
    ]
    for lx, lfc, lec, lls, ltext in legend_items:
        _rbox(ax, lx, ly - 4.2, 8.5, 8.4, fc=lfc, ec=lec, lw=0.75, ls=lls, r=1.5, z=3)
        _txt(ax, lx + 11.5, ly, ltext, size=7.6, color=MUTED)

    return fig


def figure_two(data):
    """Real quantitative P3 stacked mechanism decomposition (a) + Backup T08 budget trajectory (b)."""
    p, b = data["p3"], data["backup"]
    fig = plt.figure(figsize=(WIDTH_IN, 344.0 / 72.0), facecolor="white")
    gs = gridspec.GridSpec(
        2, 1, figure=fig, height_ratios=[1.0, 1.42],
        left=0.225, right=0.965, top=0.925, bottom=0.11, hspace=0.62,
    )

    # ---------------- Panel (a): Stacked Horizontal Bar Chart with Real X-Axis ----------------
    ax1 = fig.add_subplot(gs[0])
    _style_axis(ax1, grid_axis="x")

    fee_n = p["charge_eligible"]          # 68
    fee_chg = p["changes_with_charge"]    # 16
    fee_unc = fee_n - fee_chg             # 52

    nofee_n = p["eligible"] - fee_n       # 60
    cp_inter = p["order_interaction"]     # 15
    cp_other = p["order_cross_checked"] - cp_inter  # 23
    fix_adm = data["fixed_admission"]     # 5
    nofee_unc = nofee_n - p["changes_without_charge"]  # 17

    assert cp_inter + cp_other + fix_adm == p["changes_without_charge"]

    y_pos = [1, 0]
    bar_h = 0.56

    ax1.barh(1, fee_chg, height=bar_h, left=0, color=NAVY, edgecolor="white", linewidth=0.7)
    ax1.barh(1, fee_unc, height=bar_h, left=fee_chg, color=GRID, edgecolor="#94A3B8", linewidth=0.65)
    ax1.text(fee_chg / 2, 1, str(fee_chg), ha="center", va="center", color="white", fontsize=8.1, fontweight="bold")
    ax1.text(fee_chg + fee_unc / 2, 1, str(fee_unc), ha="center", va="center", color=INK, fontsize=8.1, fontweight="bold")
    ax1.text(fee_n + 1.5, 1, f"n = {fee_n}", ha="left", va="center", color=MUTED, fontsize=8.0)

    segs = [
        (0, cp_inter, ORANGE, "white", str(cp_inter)),
        (cp_inter, cp_other, AMBER, "white", str(cp_other)),
        (cp_inter + cp_other, fix_adm, SAGE_LIGHT, DARK_INK, str(fix_adm)),
        (cp_inter + cp_other + fix_adm, nofee_unc, GRID, INK, str(nofee_unc)),
    ]
    for left, width, col, fg, lbl in segs:
        ec = "#94A3B8" if col == GRID else "white"
        ax1.barh(0, width, height=bar_h, left=left, color=col, edgecolor=ec, linewidth=0.65)
        ax1.text(left + width / 2, 0, lbl, ha="center", va="center", color=fg, fontsize=8.0, fontweight="bold")
    ax1.text(nofee_n + 1.5, 0, f"n = {nofee_n}", ha="left", va="center", color=MUTED, fontsize=8.0)

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(["Qualifying fee", "No qualifying fee"], fontsize=8.1)
    ax1.set_xlim(0, 77)
    ax1.set_xticks([0, 10, 20, 30, 40, 50, 60, 70])
    ax1.set_xlabel("Opening–controller pairs (total = 128 across 5 histories)", fontsize=8.0, labelpad=3)
    ax1.set_ylim(-0.52, 1.52)

    ax1.text(-0.27, 1.14, "(a) P3 delivery-set changes under receipt restoration",
             transform=ax1.transAxes, fontsize=9.6, fontweight="bold", fontfamily="STIXGeneral",
             ha="left", va="bottom", color=INK)

    legend_handles = [
        Patch(facecolor=NAVY, edgecolor="white", label="Fee waiver matches (16)"),
        Patch(facecolor=ORANGE, edgecolor="white", label="Order interaction (15)"),
        Patch(facecolor=AMBER, edgecolor="white", label="Other cost-priority (23)"),
        Patch(facecolor=SAGE_LIGHT, edgecolor=SAGE, linewidth=0.5, label="Fixed-order quote (5)"),
        Patch(facecolor=GRID, edgecolor="#94A3B8", label="Unchanged (69)"),
    ]
    ax1.legend(
        handles=legend_handles, loc="upper center", bbox_to_anchor=(0.44, -0.36),
        ncol=3, frameon=False, fontsize=7.6, handlelength=1.1, handletextpad=0.45,
        columnspacing=0.95, labelspacing=0.3,
    )

    # ---------------- Panel (b): Backup T08 Budget-vs-Threshold Trajectory Plot ----------------
    ax2 = fig.add_subplot(gs[1])
    _style_axis(ax2, grid_axis="y")

    pos2 = ax2.get_position()
    ax2.set_position([0.145, pos2.y0 - 0.02, 0.820, pos2.height - 0.03])

    ax2.text(-0.155, 1.09, "(b) Backup Recovery T08: budget trajectory under a 20-unit fee waiver",
             transform=ax2.transAxes, fontsize=9.6, fontweight="bold", fontfamily="STIXGeneral",
             ha="left", va="bottom", color=INK)

    ax2.axhline(b["entry"], color=CRIMSON_EDGE, lw=0.9, ls=":", zorder=1.5)
    ax2.axhline(b["later_floor"], color=NAVY_EDGE, lw=0.9, ls=":", zorder=1.5)
    ax2.axhspan(0, b["later_floor"], color="#F1F5F9", alpha=0.65, zorder=0.5)

    xs = [0.0, 1.0, 2.0]
    y_loss = [b["loss_balance"], b["loss_balance"], b["loss_balance"]]
    y_fee = [b["fee_balance"], b["later_balance"], b["later_balance"]]

    ax2.plot(xs, y_loss, color=INK, lw=1.65, ls="--", marker="s", markersize=5.2,
             markerfacecolor="white", markeredgewidth=1.3, zorder=4,
             label=f"Original fee ({b['loss_completions']}/4 delivered)")
    ax2.plot(xs, y_fee, color=CRIMSON, lw=1.85, ls="-", marker="o", markersize=5.5,
             markerfacecolor=CRIMSON, markeredgecolor="white", markeredgewidth=0.7, zorder=5,
             label=f"Waive {b['waived']} units ({b['fee_completions']}/4 delivered)")

    # Threshold right-edge labels (placed cleanly in open space x > 2.08)
    ax2.text(2.10, b["entry"] + 1.5, f"Req. A floor ({b['entry']})",
             fontsize=7.6, color=CRIMSON, ha="left", va="bottom", fontweight="bold")
    ax2.text(2.10, b["later_floor"] + 1.5, f"Req. B floor ({b['later_floor']})",
             fontsize=7.6, color=NAVY, ha="left", va="bottom", fontweight="bold")

    # Crisp non-overlapping quantitative annotations
    ax2.annotate(
        f"{b['fee_balance']} (starts A)", xy=(0, b["fee_balance"]), xytext=(0.07, b["fee_balance"] + 2.0),
        fontsize=7.8, fontweight="bold", color=CRIMSON, ha="left", va="bottom",
    )
    ax2.annotate(
        f"{b['loss_balance']} (skips A)", xy=(0, b["loss_balance"]), xytext=(0.04, b["loss_balance"] - 7.5),
        fontsize=7.8, fontweight="bold", color=INK, ha="left", va="top",
    )
    # Place -40 spent callout cleanly in the upper-middle white pocket (x=0.62..1.18, y=49..62)
    ax2.annotate(
        f"−{b['fee_balance'] - b['later_balance']} spent\n(A rejected)",
        xy=(0.45, 41.0), xytext=(0.68, 53.5),
        fontsize=7.6, color=CRIMSON, ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.24", facecolor=CRIMSON_FILL, edgecolor=CRIMSON_EDGE, lw=0.65),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=0.85, connectionstyle="arc3,rad=0.14"),
        zorder=6,
    )
    # End-of-trace annotations cleanly centered between x=1 and x=2, zero overlap!
    ax2.text(1.52, b["loss_balance"] + 3.2, f"{b['loss_balance']} ≥ {b['later_floor']}: B finishes",
             fontsize=7.8, fontweight="bold", color=INK, ha="center", va="bottom")
    ax2.text(1.52, b["later_balance"] - 4.2, f"{b['later_balance']} < {b['later_floor']}: B skipped",
             fontsize=7.8, fontweight="bold", color=CRIMSON, ha="center", va="top")

    ax2.set_xlim(-0.16, 2.75)
    ax2.set_ylim(0, 70)
    ax2.set_yticks([0, 20, 40, 60])
    ax2.set_ylabel("Remaining budget (units)", fontsize=8.1)
    ax2.set_xticks([0, 1, 2])
    ax2.set_xticklabels(["Entry to Req. A", "After Req. A", "Entry to Req. B"], fontsize=8.0)

    ax2.legend(
        loc="upper right", frameon=True, facecolor="white", edgecolor=BORDER,
        framealpha=0.95, fontsize=7.6, borderpad=0.32, handlelength=1.7,
    )

    return fig


def figure_three(data):
    """Top-venue 2x3 quantitative subplot grid: uniform Row-1 rate bars + non-clashing Row-2 completion bars."""
    p4 = data["p4"]
    has_railway = "railway" in data
    model_names = ["Qwen", "Llama", "Mistral"]

    fig = plt.figure(figsize=(WIDTH_IN, 366.0 / 72.0), facecolor="white")
    gs = gridspec.GridSpec(
        2, 3, figure=fig,
        height_ratios=[0.94, 1.14],
        width_ratios=[1.0, 1.0, 1.0],
        left=0.125, right=0.985, top=0.910, bottom=0.105,
        wspace=0.25, hspace=0.60,
    )

    # ---------------- Row 1: Panels (a), (b), (c) — Opening-level rates ----------------
    row1_specs = [
        ("a", "Paid reread\n(keep arm)", [r["reread"] for r in p4], [12, 12, 12]),
        ("b", "Outside change\n(strict controls)", [r["outside"] for r in p4], [12, 12, 12]),
        ("c", "Outside gain\n(after waiver)", [r["fee_added"] for r in p4], [r["fee_eligible"] for r in p4]),
    ]
    for col, (letter, title, nums, dens) in enumerate(row1_specs):
        ax = fig.add_subplot(gs[0, col])
        _style_axis(ax, grid_axis="y")
        x = [0, 1, 2]
        vals = [100.0 * a / b for a, b in zip(nums, dens)]
        bars = ax.bar(x, vals, width=0.55, color=STEEL, edgecolor=NAVY, linewidth=0.7, zorder=3)
        for rect, a, b in zip(bars, nums, dens):
            h = rect.get_height()
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                h + 3.5,
                f"{a}/{b}",
                ha="center", va="bottom", fontsize=7.8, fontweight="bold", color=INK,
            )
        ax.set_ylim(0, 124)
        ax.set_yticks([0, 25, 50, 75, 100])
        if col == 0:
            ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
            ax.set_ylabel("Share of openings", fontsize=8.0, labelpad=4)
        else:
            ax.set_yticklabels([])
        ax.set_xticks(x)
        ax.set_xticklabels(model_names, fontsize=7.8)
        ax.tick_params(axis="x", length=0, pad=3.5)
        ax.set_title(f"({letter}) {title}", loc="left", fontsize=8.4, fontweight="bold",
                     fontfamily="STIXGeneral", pad=5)

    # ---------------- Row 2: Panels (d), (e) Grouped Bars + Panel (f) Interface ----------------
    gs_row2 = gridspec.GridSpecFromSubplotSpec(
        1, 3, subplot_spec=gs[1, :], width_ratios=[1.22, 1.36, 0.75], wspace=0.26
    )

    arm_meta = [
        ("keep", "Keep", BAR_KEEP, DARK_INK, None),
        ("remove", "Remove", BAR_REMOVE, "#475569", "///"),
        ("archive", "Archive", BAR_ARCHIVE, "#6B3A05", None),
    ]

    def _grouped_bars(ax, letter, title, rows, max_req, yticks, *, show_ylabel=True):
        _style_axis(ax, grid_axis="y")
        x = [0.0, 1.0, 2.0]
        bw = 0.285
        offsets = [-bw, 0.0, bw]
        for (arm_key, arm_lbl, fc, ec, hatch), off in zip(arm_meta, offsets):
            ys = [r[arm_key] for r in rows]
            bars = ax.bar(
                [xi + off for xi in x], ys, width=bw * 0.76,
                facecolor=fc, edgecolor=ec, linewidth=0.65,
                hatch=hatch, label=arm_lbl, zorder=3,
            )
            for rect, val in zip(bars, ys):
                ax.text(
                    rect.get_x() + rect.get_width() / 2.0,
                    val + max_req * 0.028,
                    str(val),
                    ha="center", va="bottom", fontsize=7.5, color=INK, fontweight="bold",
                )
        ax.set_xlim(-0.52, 2.52)
        ax.set_ylim(0, max_req * 1.20)
        ax.set_yticks(yticks)
        ax.set_xticks(x)
        ax.set_xticklabels(model_names, fontsize=7.8)
        ax.tick_params(axis="x", length=0, pad=3.5)
        if show_ylabel:
            ax.set_ylabel("Completed requests", fontsize=8.0, labelpad=4)
        ax.set_title(f"({letter}) {title}", loc="left", fontsize=8.4, fontweight="bold",
                     fontfamily="STIXGeneral", pad=5)

    ax_d = fig.add_subplot(gs_row2[0])
    _grouped_bars(ax_d, "d", "Forms (of 24)", [r["forms"] for r in p4], 24, [0, 8, 16, 24], show_ylabel=True)

    ax_e = fig.add_subplot(gs_row2[1])
    if has_railway:
        railway = data["railway"]
        rail_req, = {r["requests"] for r in railway}
        _grouped_bars(ax_e, "e", f"Railway (of {rail_req})", railway, rail_req, [0, 8, 16, 24, 32], show_ylabel=False)
    else:
        ax_e.axis("off")

    # Shared legend positioned dead-center in the gap BETWEEN Row 1 and Row 2
    handles, labels = ax_d.get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="center", bbox_to_anchor=(0.455, 0.524),
        ncol=3, frameon=True, facecolor="white", edgecolor=BORDER,
        fontsize=7.8, handlelength=1.25, handletextpad=0.45, columnspacing=1.15, borderpad=0.28,
    )

    # Panel (f): Qwen on Forms, same weights
    ax_f = fig.add_subplot(gs_row2[2])
    _style_axis(ax_f, grid_axis="y")
    q = p4[0]["forms"]
    bars_f = ax_f.bar(
        [0, 1], [q["menu"], q["keep"]], width=0.52,
        color=[SAGE, BAR_KEEP], edgecolor=["#14533C", DARK_INK], linewidth=0.7, zorder=3,
    )
    for rect, val in zip(bars_f, [q["menu"], q["keep"]]):
        ax_f.text(
            rect.get_x() + rect.get_width() / 2.0,
            val + 24 * 0.028,
            f"{val}/24",
            ha="center", va="bottom", fontsize=7.6, fontweight="bold", color=INK,
        )
    ax_f.set_ylim(0, 24 * 1.20)
    ax_f.set_yticks([0, 8, 16, 24])
    ax_f.set_xticks([0, 1])
    ax_f.set_xticklabels(["Indexed\nmenu", "Native\ntools"], fontsize=7.6)
    ax_f.tick_params(axis="x", length=0, pad=3.5)
    ax_f.set_title("(f) Qwen Forms\n(keep, same wt.)", loc="left", fontsize=8.3, fontweight="bold",
                   fontfamily="STIXGeneral", pad=5)
    ax_f.text(0.5, 25.0, "0/6 sets match", ha="center", va="bottom", fontsize=7.6,
              color=MUTED, style="italic")

    return fig


def audit_figure_geometry(fig):
    """Verify minimum font size, zero overlapping text boxes, and zero canvas clipping."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_w, fig_h = fig.canvas.get_width_height()
    min_pt = 999.0
    boxes = []
    clips = []
    for ax in fig.axes:
        texts = list(ax.texts)
        if ax.axison:
            texts += [ax.title, ax.xaxis.label, ax.yaxis.label]
            texts += list(ax.get_xticklabels()) + list(ax.get_yticklabels())
        for t in texts:
            s = t.get_text().strip()
            if not s or not t.get_visible():
                continue
            fs = float(t.get_fontsize())
            if fs < min_pt:
                min_pt = fs
            bb = t.get_window_extent(renderer=renderer)
            if bb.width > 0 and bb.height > 0:
                boxes.append((s, bb))
                if bb.x0 < -1.0 or bb.x1 > fig_w + 1.0 or bb.y0 < -1.0 or bb.y1 > fig_h + 1.0:
                    clips.append((s, [round(v, 1) for v in (bb.x0, bb.y0, bb.x1, bb.y1)], (fig_w, fig_h)))
    # Also check figure-level legends against axis titles!
    for leg in fig.legends:
        lb = leg.get_window_extent(renderer=renderer)
        boxes.append(("<FIG_LEGEND>", lb))
    collisions = []
    for i in range(len(boxes)):
        s1, b1 = boxes[i]
        for j in range(i + 1, len(boxes)):
            s2, b2 = boxes[j]
            ix = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
            iy = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
            if ix > 1.5 and iy > 1.5:
                collisions.append((s1, s2, round(ix, 1), round(iy, 1)))
    return {
        "min_font_pt": round(min_pt, 2),
        "text_boxes": len(boxes),
        "collisions": collisions,
        "clips": clips,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data", type=Path, help="Regenerate figures from the distributed aggregate record")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.data:
        data = read(args.data)
    else:
        local_data = Path(__file__).resolve().parent / "FIGURE_DATA.json"
        if not local_data.exists():
            local_data = Path(__file__).resolve().parents[1] / "tables/FIGURE_DATA.json"
        if (EVIDENCE / "20261121-manuscript-audit-tables/P3_NATIVE_CONTROLS.csv").exists():
            data = collect()
        elif local_data.exists():
            data = read(local_data)
        else:
            raise FileNotFoundError("Pass --data FIGURE_DATA.json to regenerate figures outside the full workspace.")
    (args.out / "FIGURE_DATA.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    summary = {}
    for title, render in (
        ("fig1_protocol_paths", figure_one),
        ("fig2_p3_and_backup", figure_two),
        ("fig3_p4_native_models", figure_three),
    ):
        fig = render(data)
        geom = audit_figure_geometry(fig)
        summary[title] = geom
        bounds = [list(ax.get_position().bounds) for ax in fig.axes]
        (args.out / f"{title}.alignment.json").write_text(json.dumps(bounds) + "\n", encoding="utf-8")
        fig.savefig(args.out / f"{title}.pdf", facecolor="white")
        fig.savefig(args.out / f"{title}.svg", facecolor="white")
        fig.savefig(args.out / f"{title}.png", dpi=600, facecolor="white")
        plt.close(fig)
    (args.out / "figure-geometry-audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
