#!/usr/bin/env python3
"""Generate plausible MOCK results for the 6-model × 2-split paper matrix.

These numbers are SYNTHETIC PLACEHOLDERS. They are designed to be:
  1. Internally consistent (Gap = Pass - Blame; OG correlates with RR)
  2. Plausible given the paper narrative (gap persists; frontier shows gap;
     reasoning model has better attribution)
  3. Self-consistent across all derived tables (band/family/taxonomy use the
     same per-problem distribution under the hood)

Used to:
  - preview the paper layout filled
  - test analysis scripts (make_figures.py, slicers) end-to-end
  - sanity baseline to compare REAL numbers against post-run

Usage::
  python scripts/generate_mock_results.py --output-dir mock_results/
"""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path

# Model definitions (final 6-model plan, 2026-05-15)
MODELS = [
    # (id, display, access, family)
    ("qwen3_5_27b",     "Qwen3.5-27B",                  "local", "dense"),
    ("qwen3_6_27b",     "Qwen3.6-27B",                  "local", "dense"),
    ("qwen3_6_35b_a3b", "Qwen3.6-35B-A3B",              "local", "moe"),
    ("glm_47_flash",    "GLM-4.7-Flash",                "local", "moe"),
    ("deepseek_r1_32b", "DeepSeek-R1-Distill-Qwen-32B", "local", "reasoning"),
    ("gemini_31_pro",   "Gemini-3.1-Pro Preview",       "api",   "frontier"),
]

# Plausible Pass@1 / Blame@1 / Outside-G / RegressionRate / AvgTurns per model × split.
# Story to encode in the mocks:
#   - Frontier (Gemini) highest Pass@1 but gap STILL large (paper's main claim)
#   - Reasoning-distilled model has the BEST Blame@1 (more careful attribution)
#   - Smaller / older Qwen has the LOWEST Pass@1
#   - Hard amplifies the gap for everyone
#   - Outside-G and AvgTurns rise on Hard (more drift, more iterations)
MOCK_MAIN_TABLE = {
    # model_id: {split: {pass@1, blame@1, blame@3, cf_valid@1, outside_g, reg_rate,
    #                    avg_turns, repeats, slope, gap_ci_halfwidth}}
    "qwen3_5_27b": {
        "full": dict(pass1=72.4, blame1=38.2, blame3=51.7, cf_valid=22.4, outside_g=18.3,
                     reg_rate=12.1, avg_turns=2.81, repeats=0.42, slope=0.118, gap_ci=None),
        "hard": dict(pass1=51.6, blame1=17.4, blame3=27.3, cf_valid=10.5, outside_g=29.7,
                     reg_rate=18.5, avg_turns=3.40, repeats=0.61, slope=0.085, gap_ci=6.1),
    },
    "qwen3_6_27b": {
        "full": dict(pass1=81.5, blame1=42.7, blame3=58.4, cf_valid=26.1, outside_g=16.9,
                     reg_rate=10.4, avg_turns=2.62, repeats=0.35, slope=0.137, gap_ci=None),
        "hard": dict(pass1=64.8, blame1=21.2, blame3=32.6, cf_valid=12.8, outside_g=27.4,
                     reg_rate=16.8, avg_turns=3.29, repeats=0.54, slope=0.094, gap_ci=5.3),
    },
    "qwen3_6_35b_a3b": {
        "full": dict(pass1=83.2, blame1=44.1, blame3=60.2, cf_valid=27.8, outside_g=15.8,
                     reg_rate=9.7, avg_turns=2.58, repeats=0.31, slope=0.142, gap_ci=None),
        "hard": dict(pass1=66.2, blame1=19.6, blame3=30.4, cf_valid=11.7, outside_g=25.9,
                     reg_rate=14.6, avg_turns=3.24, repeats=0.49, slope=0.103, gap_ci=5.0),
    },
    "glm_47_flash": {
        "full": dict(pass1=76.8, blame1=36.5, blame3=49.1, cf_valid=21.3, outside_g=20.2,
                     reg_rate=13.5, avg_turns=2.75, repeats=0.47, slope=0.121, gap_ci=None),
        "hard": dict(pass1=58.7, blame1=15.8, blame3=24.7, cf_valid=8.9, outside_g=32.1,
                     reg_rate=19.4, avg_turns=3.35, repeats=0.66, slope=0.078, gap_ci=5.8),
    },
    "deepseek_r1_32b": {
        "full": dict(pass1=78.5, blame1=51.3, blame3=66.8, cf_valid=34.2, outside_g=14.2,
                     reg_rate=8.9, avg_turns=3.05, repeats=0.28, slope=0.127, gap_ci=None),
        "hard": dict(pass1=60.4, blame1=28.6, blame3=40.5, cf_valid=18.1, outside_g=21.5,
                     reg_rate=12.7, avg_turns=3.68, repeats=0.43, slope=0.091, gap_ci=5.4),
    },
    "gemini_31_pro": {
        "full": dict(pass1=91.3, blame1=39.8, blame3=53.6, cf_valid=24.7, outside_g=12.6,
                     reg_rate=7.3, avg_turns=2.45, repeats=0.26, slope=0.156, gap_ci=None),
        "hard": dict(pass1=76.2, blame1=14.7, blame3=23.8, cf_valid=8.4, outside_g=23.8,
                     reg_rate=13.2, avg_turns=3.18, repeats=0.41, slope=0.112, gap_ci=4.6),
    },
}


def main_gap_table_rows():
    rows = []
    for mid, name, access, family in MODELS:
        for split in ("full", "hard"):
            d = MOCK_MAIN_TABLE[mid][split]
            gap = round(d["pass1"] - d["blame1"], 1)
            row = dict(
                model=name,
                access=access,
                family=family,
                split=split,
                pass1=d["pass1"],
                blame1=d["blame1"],
                blame3=d["blame3"],
                cf_valid=d["cf_valid"],
                outside_g=d["outside_g"],
                reg_rate=d["reg_rate"],
                avg_turns=d["avg_turns"],
                repeats=d["repeats"],
                slope=d["slope"],
                gap=gap,
                gap_ci=d["gap_ci"],
            )
            rows.append(row)
    return rows


def per_family_outside_g_distribution(seed: int = 42):
    """For Figure: distribution of Outside-G per fault family per model.
    Generates ~80 trajectory means per (model, family).
    """
    import random as _rng
    rng = _rng.Random(seed)
    out = {}
    family_offsets = {
        "Boundary / off-by-one":     -0.04,  # easier to localize → lower OG
        "Wrong operator / cond.":    -0.02,
        "Omission / missing branch":  0.02,
        "Dependency misuse":          0.08,  # hardest → highest OG
        "Corner-case / type":         0.05,
    }
    for mid, name, access, family in MODELS:
        d_hard = MOCK_MAIN_TABLE[mid]["hard"]
        og_mean = d_hard["outside_g"] / 100
        for fam, off in family_offsets.items():
            mean = og_mean + off
            samples = [max(0, min(1, rng.gauss(mean, 0.08))) for _ in range(80)]
            out.setdefault(mid, {})[fam] = samples
    return out


def per_model_failure_modes():
    """Per-model failure-mode distribution on Hard, sums to 1.0 each.
    Encodes: reasoning model has more precise_repair; weak open models have more drift/loop.
    """
    return {
        "qwen3_5_27b":     dict(precise=0.27, symptom=0.21, drift=0.27, loop=0.18, recovery=0.05, unclassified=0.02),
        "qwen3_6_27b":     dict(precise=0.32, symptom=0.19, drift=0.24, loop=0.17, recovery=0.06, unclassified=0.02),
        "qwen3_6_35b_a3b": dict(precise=0.34, symptom=0.18, drift=0.22, loop=0.17, recovery=0.07, unclassified=0.02),
        "glm_47_flash":    dict(precise=0.28, symptom=0.20, drift=0.26, loop=0.18, recovery=0.06, unclassified=0.02),
        "deepseek_r1_32b": dict(precise=0.41, symptom=0.16, drift=0.20, loop=0.13, recovery=0.08, unclassified=0.02),
        "gemini_31_pro":   dict(precise=0.36, symptom=0.21, drift=0.23, loop=0.13, recovery=0.05, unclassified=0.02),
    }


def early_drift_curves(seed: int = 7):
    """Cumulative patch size over turns, stratified by Hit vs Miss on first blame.
    For each turn 1..5, returns mean ± std cumulative patch lines.
    """
    # Mock: Hit grows slowly (~3.5 lines/turn), Miss grows faster (~6 lines/turn) + spread.
    hit_means = [3.2, 6.5, 9.4, 11.8, 13.7]
    hit_stds  = [1.1, 1.8, 2.3, 2.7, 3.0]
    miss_means = [4.1, 9.7, 15.6, 21.4, 27.9]
    miss_stds  = [1.4, 2.8, 3.9, 4.8, 5.5]
    return dict(turns=[1,2,3,4,5],
                hit_mean=hit_means, hit_std=hit_stds,
                miss_mean=miss_means, miss_std=miss_stds)


def difficulty_band_table():
    """3 bands × {Pass, Blame, Gap, OG, RR, AvgTurns}. Average across all 6 models.
    Story: harder bands have lower Pass, lower Blame, similar Gap, higher OG, higher RR, higher AvgTurns.
    """
    return [
        dict(band="Easy / Medium", n=411, pass1=86.3, blame1=46.2, gap=40.1, outside_g=14.7, reg_rate=8.4,  avg_turns=2.21),
        dict(band="Hard",          n=210, pass1=74.5, blame1=33.8, gap=40.7, outside_g=21.2, reg_rate=13.1, avg_turns=3.04),
        dict(band="VeryHard+",     n=190, pass1=61.4, blame1=22.7, gap=38.7, outside_g=27.9, reg_rate=17.5, avg_turns=3.62),
    ]


def fault_family_perf_table():
    """5 families × performance on a representative model (Qwen3.6-35B-A3B Full).
    Story: boundary off-by-one is the easiest to fix and easiest to attribute;
    dependency misuse is hardest to attribute (cross-region confusion).
    """
    return [
        dict(family="Boundary / off-by-one",    count=765, pass1=87.6, blame1=51.8, gap=35.8, outside_g=11.4, reg_rate=6.8),
        dict(family="Dependency misuse",        count=177, pass1=72.3, blame1=29.4, gap=42.9, outside_g=21.7, reg_rate=14.2),
        dict(family="Omission / missing branch", count=88,  pass1=78.4, blame1=35.7, gap=42.7, outside_g=18.6, reg_rate=11.8),
        dict(family="Wrong operator / condition", count=77, pass1=81.2, blame1=44.6, gap=36.6, outside_g=15.3, reg_rate=9.4),
        dict(family="Corner-case / type",        count=6,   pass1=66.7, blame1=33.3, gap=33.4, outside_g=24.8, reg_rate=16.7),
    ]


def diffusion_validation_table():
    """Outside-G vs RegRate correlation. n = per-edit transitions across all 6 models on Hard."""
    # 6 models × ~128 problems × avg 3.4 attempts that count as edits ≈ 2600 events
    n_total = 2614
    r_point = 0.62
    r_ci_lo = 0.57
    r_ci_hi = 0.66
    return dict(n=n_total, r=r_point, r_ci=(r_ci_lo, r_ci_hi), p_value="< 0.001")


def taxonomy_frequency_table():
    """5 failure modes × frequency, averaged across all 6 models on Hard."""
    return [
        dict(mode="precise_repair",      count=249, frac=0.324),  # 32.4% of 6 × 128
        dict(mode="symptom_patch",       count=144, frac=0.187),
        dict(mode="semantic_drift",      count=187, frac=0.243),
        dict(mode="regression_loop",     count=120, frac=0.156),
        dict(mode="diagnostic_recovery", count=52,  frac=0.068),
        dict(mode="unclassified",        count=17,  frac=0.022),
    ]


def early_drift_table():
    """Miss − Hit deltas on downstream signals (averaged across all 6 models on Hard)."""
    return [
        dict(signal="Cumulative patch size", miss_minus_hit="+14.2 lines",  ci="[+10.8, +17.6]"),
        dict(signal="Outside-G",             miss_minus_hit="+19.6 pts",    ci="[+16.1, +23.0]"),
        dict(signal="Final Blame@1",         miss_minus_hit="−32.4 pts",    ci="[−36.0, −28.7]"),
    ]


def cost_accounting_table():
    """Per-model cost / wall-clock. Local = H100, API = Gemini Standard."""
    return [
        dict(model="Qwen3.5-27B (BF16)",                  calls=2402, in_tok_M=18.2, out_tok_M=4.5, gpu_h=2.1,  api_usd=0.0,    parse_fail_pct=3.4),
        dict(model="Qwen3.6-27B (BF16)",                  calls=2402, in_tok_M=18.4, out_tok_M=4.7, gpu_h=2.0,  api_usd=0.0,    parse_fail_pct=2.1),
        dict(model="Qwen3.6-35B-A3B (BF16, MoE 3B-act)",  calls=2402, in_tok_M=18.5, out_tok_M=4.8, gpu_h=1.4,  api_usd=0.0,    parse_fail_pct=1.8),
        dict(model="GLM-4.7-Flash (AWQ-int4)",            calls=2402, in_tok_M=17.9, out_tok_M=4.6, gpu_h=1.7,  api_usd=0.0,    parse_fail_pct=5.6),
        dict(model="DeepSeek-R1-Distill-Qwen-32B (AWQ-int4)", calls=2402, in_tok_M=19.4, out_tok_M=6.2, gpu_h=2.5, api_usd=0.0, parse_fail_pct=2.8),
        dict(model="Gemini-3.1-Pro Preview (Standard API)",   calls=2402, in_tok_M=18.7, out_tok_M=5.0, gpu_h=0.0, api_usd=97.4, parse_fail_pct=1.2),
    ]


def per_edit_scatter_data(seed: int = 12345):
    """Generate synthetic (Outside-G, RegressionRate) per-edit points for Figure 2.
    Designed to match the validation table's r ≈ 0.62.
    """
    rng = random.Random(seed)
    points = []  # (outside_g, regression_rate, model_id)
    for mid, name, access, family in MODELS:
        # Number of edits per model on Hard ≈ 128 problems × avg 3.4 attempts = 435
        n = 435
        d_hard = MOCK_MAIN_TABLE[mid]["hard"]
        og_mean = d_hard["outside_g"] / 100
        rr_mean = d_hard["reg_rate"] / 100
        for _ in range(n):
            # Generate correlated point: og ∈ [0, 1], rr = 0.55*og + noise
            og = max(0, min(1, rng.gauss(og_mean, 0.12)))
            rr = max(0, min(1, 0.55 * og + rng.gauss(0, 0.07)))
            points.append((og, rr, mid))
    return points


def dry_run_calibration():
    """Day 0 dry-run on 30 stratified tasks × 6 models = 180 runs.
    Output: parse failure / empty blame / timeout rates per model.
    """
    return [
        dict(model="Qwen3.5-27B",                  n=30, parse_ok=28, blame_empty=3, code_ok=29, timeout=1, avg_latency_s=18.4),
        dict(model="Qwen3.6-27B",                  n=30, parse_ok=29, blame_empty=2, code_ok=30, timeout=0, avg_latency_s=14.7),
        dict(model="Qwen3.6-35B-A3B",              n=30, parse_ok=29, blame_empty=2, code_ok=30, timeout=0, avg_latency_s=8.3),
        dict(model="GLM-4.7-Flash",                n=30, parse_ok=27, blame_empty=4, code_ok=29, timeout=1, avg_latency_s=11.5),
        dict(model="DeepSeek-R1-Distill-Qwen-32B", n=30, parse_ok=28, blame_empty=2, code_ok=29, timeout=1, avg_latency_s=24.6),
        dict(model="Gemini-3.1-Pro Preview",       n=30, parse_ok=30, blame_empty=1, code_ok=30, timeout=0, avg_latency_s=6.2),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="mock_results")
    args = parser.parse_args()
    out = Path(args.output_dir)
    if not out.is_absolute():
        out = Path("/Users/apple/Desktop/tracebench") / out
    out.mkdir(parents=True, exist_ok=True)

    bundle = {
        "_meta": {
            "version": "mock-v2-2026-05-15",
            "note": "Synthetic placeholder data — DO NOT cite. Replace with real eval matrix output.",
        },
        "tab_gap_main_12row": main_gap_table_rows(),
        "tab_difficulty_bands": difficulty_band_table(),
        "tab_fault_family_perf": fault_family_perf_table(),
        "tab_diffusion_validation": diffusion_validation_table(),
        "tab_taxonomy_frequency": taxonomy_frequency_table(),
        "tab_early_drift": early_drift_table(),
        "tab_cost_accounting": cost_accounting_table(),
        "tab_dry_run_calibration": dry_run_calibration(),
        "fig_per_family_og": per_family_outside_g_distribution(),
        "fig_per_model_failure_modes": per_model_failure_modes(),
        "fig_early_drift_curves": early_drift_curves(),
        "fig2_scatter_points": [
            dict(outside_g=og, reg_rate=rr, model_id=mid)
            for og, rr, mid in per_edit_scatter_data()
        ],
    }

    out_file = out / "mock_bundle.json"
    with out_file.open("w") as fh:
        json.dump(bundle, fh, indent=2)
    print(f"Wrote {out_file} ({len(bundle['fig2_scatter_points'])} scatter pts)")

    # Also write a per-figure-2 records.jsonl that make_figures.py can consume
    scatter_records = []
    for og, rr, mid in per_edit_scatter_data():
        scatter_records.append({
            "trace_id": f"mock_{mid}_{len(scatter_records)}",
            "outside_g": og,
            "regression_rate": rr,
            "solved": rr < 0.15,  # arbitrary mock pass label
            "blame_at_1": 1 if og < 0.25 else 0,
            "model_id": mid,
        })
    rec_file = out / "mock_per_problem_records.jsonl"
    with rec_file.open("w") as fh:
        for r in scatter_records:
            fh.write(json.dumps(r) + "\n")
    print(f"Wrote {rec_file} ({len(scatter_records)} records)")


if __name__ == "__main__":
    main()
