# v1_6model — first complete paper-grade result drop

**Dataset**: tracebench_full (818 problems × 6 models = 4708 attempted, 4703 with complete metrics).
**Generated**: 2026-05-18T03:33Z (analyze) + 2026-05-18T03:33Z (Outside-G fixup).
**Cascade duration**: ~32h on single H100 PCIe + 2 API cells in parallel.
**Total API spend**: $32.40 ($19.37 GPT-5.4 + $13.03 Gemini).

## Model lineup

| Model | type | n_done | wall_clock | pass1 |
|---|---|---:|---:|---:|
| qwen3_6_27b | open dense local-vLLM | 784 | 9.7h | **71.3%** |
| gpt_54 | closed frontier OpenAI API | 785 | 28 min | 71.0% |
| gemma_4_31b | open dense local-vLLM | 782 | 8.4h | 70.2% |
| gemini_31_pro | closed frontier Google API | 786 | 2.0h | 67.9% |
| qwen3_6_35b_a3b | open MoE local-vLLM | 783 | 5.0h | 55.7% |
| glm_47_flash | open dense local-vLLM | 783 | 8.1h | 40.7% |

**Note**: DeepSeek-R1-Distill-32B was dropped from the lineup mid-cascade (reasoning model ran at 5min/problem, would have taken 71h). Only 13 records collected, archived under `out/test/deepseek_partial_13/` not in this drop.

## What's in this drop

```
results/v1_6model/
├── README.md                           # this file
├── analysis/
│   ├── numbers.json                    # single source of truth for paper scalars
│   ├── outside_g_fixup_summary.json    # per-model Outside-G distribution (REAL, snippet-coord)
│   ├── outside_g_fixup.jsonl           # per-attempt Outside-G (8967 rows)
│   ├── per_problem_metrics.jsonl       # full TraceabilityMetrics bundle per (model, problem)
│   └── per_edit_scatter.jsonl          # per-problem (outside_g, regression_rate) — input for fig_scatter
├── tables/
│   ├── main_gap_table.csv              # 12 rows × 11 cols (6 models × {full, hard})
│   ├── outside_g_regression.csv        # Pearson r(outside_g, reg_rate) per model + pooled
│   ├── cost_accounting.csv             # attempts + tokens per cell
│   └── fault_family_distribution.csv   # dataset-derived (5 families × 3 difficulty bins)
├── records_summaries/
│   └── <model>_full_summary.json       # per-cell n_done, wall_clock, spend, abort status
└── logs/
    └── <model>_tail.log                # last 100 non-noise lines from each cell's stdout (debug trail)
```

## Headline results

### Pass@1 (full split)

```
qwen3_6_27b      71.3%  (784 problems)
gpt_54           71.0%  (785)
gemma_4_31b      70.2%  (782)
gemini_31_pro    67.9%  (786)
qwen3_6_35b_a3b  55.7%  (783)
glm_47_flash     40.7%  (783)
```

Top-3 cluster tight (70.2–71.3); open-source has caught closed-frontier on this benchmark.

### Hard-Full gap

Gemini-3.1-Pro shows largest drop on hard problems (28.2 pp), GLM-4.7-Flash smallest (17.2 pp).

### Outside-G mean (snippet-coord, anchor_value-matched)

```
glm_47_flash     0.81  (most diffuse edits)
qwen3_6_27b      0.76
qwen3_6_35b_a3b  0.76
gemma_4_31b      0.76
gpt_54           0.70
gemini_31_pro    0.66  (most focused — yet not best pass1)
```

## Two flagship findings — REAL numbers (post-cascade fixups 03c + 03d)

### Finding 1: Outside-G ↔ RegressionRate Pearson — **NOT supported by data**

```
Pooled  n=508  r=0.062  p=0.16  CI [-0.025, 0.149]
```

All per-model r are near zero with CIs crossing zero (range −0.09 to +0.26).
The two metrics are essentially uncorrelated on this dataset.

**Paper implication**: the "Outside-G validates RegressionRate r=0.62" claim
must be reframed or dropped. Suggested reframing: "Outside-G measures a
localization-quality dimension orthogonal to regression behavior — both are
needed to characterize patch quality."

See `tables/outside_g_regression.csv` (per model + pooled) and `analysis/numbers.json` (`outside_g_r/n/p/ci_lo/ci_hi`).

### Finding 2: Early mis-localization → drift — **STRONGLY supported** ✓

```
Pooled  n_hit=189  n_miss=147
  cum_patch_delta = +40.9 lines      CI [+14.9, +66.6]  ✓ strictly positive
  outside_g_delta(last_turn) = +0.66 CI [+0.60, +0.70]  ✓ very tight
```

Per-model: every cell shows positive Δ outside_g with CIs entirely above zero.
Models that mis-localize at turn 0 edit ~41 more lines cumulatively AND
remain ~0.66 outside the fault region even at the last turn — they **don't
recover** from initial mis-localization.

Best per-model recovery: gpt_54 (Δ outside_g = 0.54).
Worst: qwen3_6_27b (Δ = 0.87 — its "miss" trajectories never converge back).

See `analysis/early_drift_summary.json` for per-model breakdown with
bootstrap (200 iters, seed=20260518) 95% CIs on both deltas.

## What's still deferred / dropped

- **blame@k columns**: dropped from main_gap_table. Runner in baseline mode aliases `blame_spans` to `patch_spans` (no dedicated localization prompt). Paper should cite `patch_locality` (in per_problem_metrics.jsonl) as proxy + footnote that a follow-up cell with localization prompt would be needed for true blame@k.
- **cf_valid_at_1**: skipped (subprocess flood). Paper relies on Outside-G + pass1 + gap + early-drift as headline metrics; cf_valid_at_1 is supplementary.
- **`out_g` column in main_gap_table.csv** is the OLD artifact value (~0.93 constant from `TraceabilityMetrics.active_spans_from_entry` in original-codebase coords). **Use `outside_g_fixup_summary.json` for the real distribution** (snippet-coord, anchor_value-matched).
- **figures + tex + paper PDF**: skipped this round; rerunning `make figures && make tex && make paper` against this analyze output produces the paper-style outputs.

## Reproducibility — full pipeline from records

```bash
# Stage 3 main analyze (skips subprocess-heavy metrics for speed)
make analyze

# Stage 3b Outside-G fixup (anchor_value snippet-coord)
python code/scripts/03b_fixup_outside_g.py \
    --records-dir out/records \
    --output-dir results/v1_6model/analysis

# Stage 3c RegressionRate fixup (uses saved per_test_results, no subprocess)
python code/scripts/03c_fixup_regression_rate.py \
    --records-dir out/records \
    --output-dir results/v1_6model/analysis

# Stage 3d Pearson + Early-drift Hit-vs-Miss (bootstrap CI)
python code/scripts/03d_compute_correlations_and_drift.py \
    --records-dir out/records \
    --results-dir results/v1_6model
```

All four can re-run on the records dir read-only; no eval needed.

## Reproducibility

Pipeline version: **commit 4a6647d**.

```bash
# rebuild from raw records (out/records/<model>_full_records.jsonl)
make analyze          # → out/tables/, out/analysis/
python code/scripts/03b_fixup_outside_g.py    # → outside_g_fixup_*
```

## Per-cell notes

- **GPT-5.4** finished in 28 min total (concurrency=8, $0.024/problem). 35 entries skipped via runner exceptions (sandbox timeouts / malformed function calls). All 785 saved records have full per-attempt `subproblems` detail.
- **Gemini** ran in 2h (concurrency=8). 32 entries skipped. Same record completeness as GPT-5.4.
- **Local cells** (Qwen 27b, 35b-A3B, GLM, Gemma) used vLLM 0.19.1 with `--gdn-prefill-backend triton` (skipping flashinfer JIT compile hang on Qwen3.x hybrid attention) + `--enable-prefix-caching` + `--concurrency 8`. Each cell paid ~2 min vllm cold-start; the rest was eval. 34–35 entries per cell skipped on sandbox timeouts (dataset artifact — some hard problems have slow test cases that trip the 30s sandbox cap).
