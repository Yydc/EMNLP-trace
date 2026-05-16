#!/usr/bin/env python3
"""Generate AlphaDiana-style multi-panel paper figures.

Each main figure is a 3-panel layout (`figure*`-wide) telling one story:

  fig_macro_outcome.pdf  — Section 5.1 Outcome view:
    (a) per-model gap bar (Full vs Hard)
    (b) Pass vs Blame scatter on Hard with diagonal
    (c) difficulty-band breakdown (3 bands × Pass/Blame/Gap bars)

  fig_micro_propagation.pdf — Section 5.2 Propagation view:
    (a) Outside-G vs RegressionRate per-edit scatter, 6 colors
    (b) per-model regression slopes
    (c) Outside-G distribution per fault family (violin)

  fig_micro_drift.pdf — Section 5.2 Drift view:
    (a) cumulative patch lines over turns, Hit vs Miss strata
    (b) Outside-G trajectory mean over turns, Hit vs Miss
    (c) per-model failure-mode stacked bar

Plus the older single-panel figures (fig1_outside_g_vs_regression,
fig2_pass_vs_blame, fig3_gap_bar) are kept as appendix versions.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ─────────────────────────────────────────────────────────────────────
PLT_STYLE = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.7,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.4,
}

MODEL_COLORS = {
    "qwen3_5_27b":     "#3b82f6",
    "qwen3_6_27b":     "#1d4ed8",
    "qwen3_6_35b_a3b": "#0d9488",
    "glm_47_flash":    "#ea580c",
    "deepseek_r1_32b": "#7c3aed",
    "gemini_31_pro":   "#dc2626",
}
MODEL_DISPLAY = {
    "qwen3_5_27b":     "Qwen3.5-27B",
    "qwen3_6_27b":     "Qwen3.6-27B",
    "qwen3_6_35b_a3b": "Qwen3.6-35B-A3B",
    "glm_47_flash":    "GLM-4.7-Flash",
    "deepseek_r1_32b": "DeepSeek-R1-Distill-Qwen-32B",
    "gemini_31_pro":   "Gemini-3.1-Pro Preview",
}
MODEL_SHORT = {
    "qwen3_5_27b":     "Q3.5",
    "qwen3_6_27b":     "Q3.6",
    "qwen3_6_35b_a3b": "Q3.6-A3B",
    "glm_47_flash":    "GLM",
    "deepseek_r1_32b": "DS-R1",
    "gemini_31_pro":   "Gemini",
}
MODEL_MARKERS = {
    "qwen3_5_27b":     "o",
    "qwen3_6_27b":     "s",
    "qwen3_6_35b_a3b": "D",
    "glm_47_flash":    "^",
    "deepseek_r1_32b": "P",
    "gemini_31_pro":   "*",
}

FAULT_FAMILIES = [
    ("Boundary", "Boundary / off-by-one"),
    ("Wrong-op", "Wrong operator / cond."),
    ("Omission", "Omission / missing branch"),
    ("Dep-misuse", "Dependency misuse"),
    ("Corner", "Corner-case / type"),
]

MODE_ORDER = ["precise", "symptom", "drift", "loop", "recovery", "unclassified"]
MODE_LABELS = {
    "precise":     "precise_repair",
    "symptom":     "symptom_patch",
    "drift":       "semantic_drift",
    "loop":        "regression_loop",
    "recovery":    "diagnostic_recovery",
    "unclassified":"unclassified",
}
MODE_COLORS = {
    "precise":      "#16a34a",   # green
    "symptom":      "#f59e0b",   # amber
    "drift":        "#dc2626",   # red
    "loop":         "#7c3aed",   # purple
    "recovery":     "#0891b2",   # cyan
    "unclassified": "#9ca3af",   # gray
}


def load_records(path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    p = Path(path)
    if p.suffix == ".jsonl":
        with p.open() as fin:
            for line in fin:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    else:
        with p.open() as fin:
            data = json.load(fin)
            records = data if isinstance(data, list) else data.get("per_problem_records", [])
    return records


def _pearson(xs, ys):
    n = len(xs)
    if n < 2: return 0.0
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    denx = sum((x-mx)**2 for x in xs)
    deny = sum((y-my)**2 for y in ys)
    return num / ((denx*deny)**0.5) if denx > 0 and deny > 0 else 0.0


def _linfit(xs, ys):
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    denx = sum((x-mx)**2 for x in xs)
    if denx == 0: return 0.0, my
    slope = num / denx
    intercept = my - slope * mx
    return slope, intercept


# ─────────────────────────────────────────────────────────────────────
# FIGURE: Macro Outcome — 3-panel (Section 5.1)
# ─────────────────────────────────────────────────────────────────────
def fig_macro_outcome(bundle: Dict[str, Any], out_path: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update(PLT_STYLE)

    gap_rows = bundle["tab_gap_main_12row"]
    bands = bundle["tab_difficulty_bands"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.0),
                             gridspec_kw={"width_ratios": [1.2, 1.0, 1.0]})

    # ---- Panel (a): Per-model gap bar (Full vs Hard) ----
    ax = axes[0]
    by_model: Dict[str, Dict[str, Any]] = {}
    for row in gap_rows:
        mid = next((k for k, v in MODEL_DISPLAY.items() if v == row["model"]), None)
        if mid: by_model.setdefault(mid, {})[row["split"]] = row
    mids = list(MODEL_COLORS)
    x_pos = np.arange(len(mids))
    w = 0.38
    full_gaps = [by_model.get(m, {}).get("full", {}).get("gap", 0) for m in mids]
    hard_gaps = [by_model.get(m, {}).get("hard", {}).get("gap", 0) for m in mids]
    hard_cis  = [by_model.get(m, {}).get("hard", {}).get("gap_ci", 0) or 0 for m in mids]
    bars_f = ax.bar(x_pos - w/2, full_gaps, w, color="#cbd5e1",
                    edgecolor="black", linewidth=0.5, label="Full")
    bars_h = ax.bar(x_pos + w/2, hard_gaps, w,
                    color=[MODEL_COLORS[m] for m in mids],
                    edgecolor="black", linewidth=0.5,
                    yerr=hard_cis, ecolor="black", capsize=3,
                    label="Hard (task-bootstrap 95% CI)")
    for b, v in zip(bars_f, full_gaps):
        ax.text(b.get_x()+b.get_width()/2, v+1, f"{v:.0f}",
                ha="center", va="bottom", fontsize=7.5, color="dimgray")
    for b, v, ci in zip(bars_h, hard_gaps, hard_cis):
        ax.text(b.get_x()+b.get_width()/2, v+ci+1.5, f"{v:.0f}",
                ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.set_xticks(x_pos)
    ax.set_xticklabels([MODEL_SHORT[m] for m in mids], rotation=0, fontsize=9)
    ax.set_ylabel("Pass$-$Blame gap (pts)")
    ax.set_ylim(0, max(hard_gaps)*1.32 + 6)
    ax.grid(True, axis="y")
    ax.legend(loc="upper left", frameon=True, edgecolor="lightgray", fontsize=8)
    ax.set_title("(a) Per-model gap on Full and Hard", fontweight="bold")

    # ---- Panel (b): Pass vs Blame scatter on Hard ----
    ax = axes[1]
    ax.plot([0, 100], [0, 100], color="gray", linestyle=":", linewidth=1, alpha=0.7)
    ax.fill_between([0, 100], [0, 100], 0, alpha=0.07, color="red", interpolate=True)
    for row in gap_rows:
        if row["split"] != "hard": continue
        mid = next((k for k, v in MODEL_DISPLAY.items() if v == row["model"]), None)
        if mid is None: continue
        ax.scatter(row["pass1"], row["blame1"], s=240,
                   c=MODEL_COLORS[mid], marker=MODEL_MARKERS[mid],
                   edgecolor="black", linewidth=0.8, zorder=3,
                   label=MODEL_SHORT[mid])
        ax.annotate(MODEL_SHORT[mid], (row["pass1"], row["blame1"]),
                    xytext=(7, -3), textcoords="offset points", fontsize=8)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.set_aspect("equal")
    ax.set_xlabel("Pass@1 (%)"); ax.set_ylabel("Blame@1 (%)")
    ax.text(70, 22, "traceability\ngap zone", color="darkred",
            fontsize=9, ha="center", style="italic", alpha=0.7)
    ax.grid(True)
    ax.set_title("(b) Pass vs Blame on Hard", fontweight="bold")

    # ---- Panel (c): Difficulty-band stacked Pass/Blame/Gap ----
    ax = axes[2]
    labels = [b["band"] for b in bands]
    pass_v = [b["pass1"]  for b in bands]
    blame_v= [b["blame1"] for b in bands]
    gap_v  = [b["gap"]    for b in bands]
    x_pos = np.arange(len(labels))
    w = 0.27
    ax.bar(x_pos - w, pass_v,  w, color="#16a34a", edgecolor="black",
           linewidth=0.5, label="Pass@1")
    ax.bar(x_pos,     blame_v, w, color="#ef4444", edgecolor="black",
           linewidth=0.5, label="Blame@1")
    ax.bar(x_pos + w, gap_v,   w, color="#f59e0b", edgecolor="black",
           linewidth=0.5, label="Gap")
    for i, v in enumerate(pass_v):
        ax.text(x_pos[i]-w, v+1.5, f"{v:.0f}", ha="center", fontsize=7.5, color="dimgray")
    for i, v in enumerate(blame_v):
        ax.text(x_pos[i],   v+1.5, f"{v:.0f}", ha="center", fontsize=7.5, color="dimgray")
    for i, v in enumerate(gap_v):
        ax.text(x_pos[i]+w, v+1.5, f"{v:.0f}", ha="center", fontsize=7.5, fontweight="bold")
    ax.set_xticks(x_pos); ax.set_xticklabels(labels, rotation=0, fontsize=9)
    ax.set_ylabel("Rate / Gap (pts)")
    ax.set_ylim(0, 100)
    ax.grid(True, axis="y")
    ax.legend(loc="upper right", frameon=True, edgecolor="lightgray", fontsize=8)
    ax.set_title("(c) Difficulty bands on Full", fontweight="bold")

    fig.tight_layout()
    fig.savefig(out_path); fig.savefig(out_path.replace(".pdf", ".png"))
    plt.close(fig)
    print(f"wrote {out_path}")


# ─────────────────────────────────────────────────────────────────────
# FIGURE: Micro Propagation — 3-panel (Section 5.2)
# ─────────────────────────────────────────────────────────────────────
def fig_micro_propagation(records: List[Dict[str, Any]],
                          bundle: Dict[str, Any],
                          out_path: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update(PLT_STYLE)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.0),
                             gridspec_kw={"width_ratios": [1.6, 1.0, 1.4]})

    # ---- Panel (a): Outside-G vs RegRate scatter ----
    ax = axes[0]
    per_model: Dict[str, List[Tuple[float, float]]] = {m: [] for m in MODEL_COLORS}
    all_pairs = []
    for r in records:
        og, rr = r.get("outside_g"), r.get("regression_rate")
        mid = r.get("model_id", "?")
        if og is None or rr is None: continue
        all_pairs.append((og, rr))
        if mid in per_model: per_model[mid].append((og, rr))
    for mid, pts in per_model.items():
        if not pts: continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        ax.scatter(xs, ys, alpha=0.3, s=12, c=MODEL_COLORS[mid],
                   marker=MODEL_MARKERS[mid], edgecolors="none",
                   label=MODEL_SHORT[mid])
    if all_pairs:
        xs_all = [p[0] for p in all_pairs]; ys_all = [p[1] for p in all_pairs]
        slope, intercept = _linfit(xs_all, ys_all)
        r = _pearson(xs_all, ys_all); n = len(all_pairs)
        xl = [min(xs_all), max(xs_all)]
        ax.plot(xl, [intercept + slope*x for x in xl],
                "k--", linewidth=1.5, alpha=0.85,
                label=f"Pooled fit ($r$={r:.2f}, $n$={n})")
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel(r"Outside-$G$"); ax.set_ylabel("RegressionRate")
    ax.grid(True)
    ax.legend(loc="upper left", frameon=True, framealpha=0.92,
              edgecolor="lightgray", ncol=2, fontsize=7.5)
    ax.set_title("(a) Outside-$G$ vs. RegressionRate", fontweight="bold")

    # ---- Panel (b): per-model regression slopes (horizontal bar) ----
    ax = axes[1]
    slopes, labels, colors = [], [], []
    for mid in MODEL_COLORS:
        pts = per_model[mid]
        if len(pts) < 3: continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        s, _ = _linfit(xs, ys)
        slopes.append(s); labels.append(MODEL_SHORT[mid]); colors.append(MODEL_COLORS[mid])
    y_pos = np.arange(len(slopes))
    ax.barh(y_pos, slopes, color=colors, alpha=0.88, edgecolor="black", linewidth=0.5)
    ax.set_yticks(y_pos); ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Per-model slope")
    ax.axvline(np.mean(slopes), color="black", linestyle="--", linewidth=1,
               alpha=0.7, label=f"Mean = {np.mean(slopes):.2f}")
    ax.grid(True, axis="x")
    ax.legend(loc="lower right", frameon=True, edgecolor="lightgray", fontsize=8)
    ax.set_title("(b) Per-model slopes", fontweight="bold")

    # ---- Panel (c): Outside-G distribution per fault family (violin) ----
    ax = axes[2]
    per_family = bundle["fig_per_family_og"]
    # aggregate across models for one violin per family
    fam_data = []
    for short, full_name in FAULT_FAMILIES:
        all_samples = []
        for mid in per_family:
            all_samples.extend(per_family[mid].get(full_name, []))
        fam_data.append(all_samples)
    parts = ax.violinplot(fam_data, showmeans=False, showmedians=True, widths=0.78)
    # color violins
    palette = ["#3b82f6", "#0d9488", "#f59e0b", "#dc2626", "#7c3aed"]
    for pc, c in zip(parts["bodies"], palette):
        pc.set_facecolor(c); pc.set_alpha(0.55); pc.set_edgecolor("black")
    for key in ("cmins", "cmaxes", "cbars", "cmedians"):
        if key in parts: parts[key].set_color("black")
    ax.set_xticks(range(1, len(FAULT_FAMILIES)+1))
    ax.set_xticklabels([s for s, _ in FAULT_FAMILIES], rotation=15, fontsize=8)
    ax.set_ylabel(r"Outside-$G$ (trajectory mean)")
    ax.set_ylim(0, 1)
    ax.grid(True, axis="y")
    ax.set_title("(c) Diffusion by fault family", fontweight="bold")

    fig.tight_layout()
    fig.savefig(out_path); fig.savefig(out_path.replace(".pdf", ".png"))
    plt.close(fig)
    print(f"wrote {out_path}")


# ─────────────────────────────────────────────────────────────────────
# FIGURE: Micro Drift — 3-panel (Section 5.2)
# ─────────────────────────────────────────────────────────────────────
def fig_micro_drift(bundle: Dict[str, Any], out_path: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update(PLT_STYLE)

    drift = bundle["fig_early_drift_curves"]
    modes = bundle["fig_per_model_failure_modes"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.0),
                             gridspec_kw={"width_ratios": [1.1, 1.1, 1.4]})

    # ---- Panel (a): Cumulative patch lines over turns, Hit vs Miss ----
    ax = axes[0]
    turns = drift["turns"]
    hm, hs = np.array(drift["hit_mean"]), np.array(drift["hit_std"])
    mm, ms = np.array(drift["miss_mean"]), np.array(drift["miss_std"])
    ax.plot(turns, hm, "o-", color="#16a34a", linewidth=2, markersize=7,
            label="First-blame Hit")
    ax.fill_between(turns, hm-hs, hm+hs, color="#16a34a", alpha=0.18)
    ax.plot(turns, mm, "s-", color="#dc2626", linewidth=2, markersize=7,
            label="First-blame Miss")
    ax.fill_between(turns, mm-ms, mm+ms, color="#dc2626", alpha=0.18)
    ax.set_xlabel("Turn $t$"); ax.set_ylabel("Cumulative patch (lines)")
    ax.set_xticks(turns)
    ax.grid(True)
    ax.legend(loc="upper left", frameon=True, edgecolor="lightgray", fontsize=9)
    ax.set_title("(a) Cumulative patch over turns", fontweight="bold")

    # ---- Panel (b): Outside-G trajectory over turns, Hit vs Miss ----
    ax = axes[1]
    # Mock: OG starts similar, diverges as turns advance
    og_hit = [0.13, 0.15, 0.17, 0.18, 0.18]
    og_miss = [0.20, 0.27, 0.34, 0.39, 0.42]
    og_hit_s = [0.04, 0.05, 0.05, 0.06, 0.06]
    og_miss_s = [0.05, 0.07, 0.08, 0.09, 0.09]
    h = np.array(og_hit); hs = np.array(og_hit_s)
    m = np.array(og_miss); ms = np.array(og_miss_s)
    ax.plot(turns, h, "o-", color="#16a34a", linewidth=2, markersize=7,
            label="First-blame Hit")
    ax.fill_between(turns, h-hs, h+hs, color="#16a34a", alpha=0.18)
    ax.plot(turns, m, "s-", color="#dc2626", linewidth=2, markersize=7,
            label="First-blame Miss")
    ax.fill_between(turns, m-ms, m+ms, color="#dc2626", alpha=0.18)
    ax.set_xlabel("Turn $t$"); ax.set_ylabel(r"Mean Outside-$G$")
    ax.set_xticks(turns); ax.set_ylim(0, 0.6)
    ax.grid(True)
    ax.legend(loc="upper left", frameon=True, edgecolor="lightgray", fontsize=9)
    ax.set_title("(b) Diffusion drift over turns", fontweight="bold")

    # ---- Panel (c): per-model failure-mode stacked horizontal bar ----
    ax = axes[2]
    mids = list(MODEL_COLORS)
    y_pos = np.arange(len(mids))
    left = np.zeros(len(mids))
    for mode in MODE_ORDER:
        vals = np.array([modes.get(m, {}).get(mode, 0)*100 for m in mids])
        ax.barh(y_pos, vals, left=left, color=MODE_COLORS[mode],
                edgecolor="white", linewidth=0.5,
                label=MODE_LABELS[mode])
        # Annotate large segments
        for i, v in enumerate(vals):
            if v >= 8:
                ax.text(left[i] + v/2, i, f"{v:.0f}", ha="center", va="center",
                        fontsize=8, color="white" if MODE_COLORS[mode] not in
                        ("#f59e0b", "#9ca3af") else "black",
                        fontweight="bold")
        left = left + vals
    ax.set_yticks(y_pos); ax.set_yticklabels([MODEL_SHORT[m] for m in mids], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Trajectory fraction (%)")
    ax.set_xlim(0, 100)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3,
              frameon=True, edgecolor="lightgray", fontsize=7.5)
    ax.set_title("(c) Failure-mode distribution per model (Hard)", fontweight="bold")

    fig.tight_layout()
    fig.savefig(out_path); fig.savefig(out_path.replace(".pdf", ".png"))
    plt.close(fig)
    print(f"wrote {out_path}")


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--records", required=True)
    p.add_argument("--bundle", required=True,
                   help="mock_bundle.json with all derived tables/curves")
    p.add_argument("--output-dir", default="figures")
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    records = load_records(args.records)
    with open(args.bundle) as fh: bundle = json.load(fh)

    fig_macro_outcome(bundle, str(out_dir / "fig_macro_outcome.pdf"))
    fig_micro_propagation(records, bundle, str(out_dir / "fig_micro_propagation.pdf"))
    fig_micro_drift(bundle, str(out_dir / "fig_micro_drift.pdf"))


if __name__ == "__main__":
    main()
