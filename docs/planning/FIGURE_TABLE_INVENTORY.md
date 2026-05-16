# Paper Figure / Table Inventory — **LOCKED** for the 6-model plan

> 2026-05-15
> All decisions accepted: D1 (no GPT-5.5/Claude) + D2 (GLM-4.7-Flash in) + D3 (Gemini Standard API).
> This document is the **single source of truth** for what's in the paper. Each entry:
>   - says what artifact it is, where it sits, what data feeds it
>   - provides a **MOCK preview** so we can see the paper filled BEFORE the real run
>   - says exactly which post-run script produces it
>
> Mock data lives in `mock_results/mock_bundle.json` (regen: `python code/scripts/generate_mock_results.py`).

---

## Summary count

| Location | Figures | Tables | Total |
|----------|--------:|-------:|------:|
| Main text §1 (Intro) | 1 | 0 | 1 |
| Main text §2 (Why) | 0 | 2 | 2 |
| Main text §3 (Dataset) | 0 | 1 | 1 |
| Main text §4 (Protocol) | 0 | 1 | 1 |
| Main text §5 (Reveals) | 1 | 5 | 6 |
| Main text §6 (Release) | 0 | 1 | 1 |
| **Main text total** | **2** | **10** | **12** |
| Appendix | 1 | 4 | 5 |
| **GRAND TOTAL** | **3** | **14** | **17** |

---

## Status legend
- 🟢 **READY**: locked content, no eval needed (descriptive or already-computed-from-dataset)
- 🟡 **MOCK**: structure locked, content shown below is placeholder; real numbers from post-run analysis pass
- 🔴 **TBD**: blocked on a specific upstream step

---

## MAIN TEXT — Section 1 (Introduction)

### 🟢 Figure 1 — `fig:overview` — schematic 4-panel teaser

**Type**: descriptive, no data backing.

**Already in paper**: yes (LaTeX framed-minipage layout, line 75-92).

**Caption**: "From outcome-only to traceability-aware debugging evaluation. \suite{} preserves the final executable outcome while adding causal labels and transcript-level process signals."

**Content** (4 panels):
1. Hidden by Pass@1 — fault suspicion / edit scope / regressions
2. Offline causal labels — active spans / counterfactual patches / fault families
3. Full split — 818 problems / 2402 traces / 7165 tests
4. Hard split — 128 high-signal diagnostic instances

---

## MAIN TEXT — Section 2 (Why Existing Benchmarks)

### 🟢 Table 1 — `tab:design-principles` (currently not in this draft, optional descriptive)

Already in writing.json registry but not currently rendered in main.tex.

### 🟢 Table 2 — `tab:benchmark-matrix` — 12-row positioning matrix

**Type**: descriptive, no data backing.

**Already in paper**: yes (line 107-136).

**Content**: 12 prior benchmarks × 6 axes (multi-turn / exec / controlled fault / active span / counterf. repair / turn-level diffusion) + remaining gap column.

**Action required**: bibkey audit before submission (8 cites: cleanpr / davincidev / swebenchpro / contextbench / racebench / trajeval / codetracer / terminalbench).

---

## MAIN TEXT — Section 3 (TraceBench-Full)

### 🟢 Table 3 — `tab:splits` — dataset stats

**Type**: dataset-derived, locked.

**Content** (already in main.tex line 157-180):

| Statistic | Full | Hard |
|-----------|-----:|-----:|
| Problems | 818 | 128 |
| Rating mean / median | 1699 / 1600 | 2679.7 / 2700 |
| Depth mean | 3.20 | 3.75 |
| Total turns | 2402 | 442 |
| Avg turns / problem | 2.94 | 3.45 |
| Total subproblems | 2743 | 549 |
| Total test cases | 7165 | 1511 |
| Avg injections / problem | 1.36 | 1.40 |
| Multi-turn coverage | 100% | 100% |

---

## MAIN TEXT — Section 4 (Protocol and Metrics)

### 🟢 Table 4 — `tab:metrics` — 3-axis × primary metrics

**Type**: descriptive.

**Already in paper**: yes (line 199-214).

| Axis | Primary metric | Operational meaning |
|------|---------------|---------------------|
| Attribution | Blame@1, CF-Valid@1 | Does the top blamed span overlap active fault? |
| Propagation | Outside-$G$, RegressionRate | Do edits diffuse outside grounded fault region? |
| Accumulation | Progress slope, $R^2$, repeats | Does trajectory steadily improve? |

---

## MAIN TEXT — Section 5 (What TraceBench-Full Reveals) — **all 6 mocked**

### 🟡 Table 5 — `tab:gap` — **MAIN RESULT, 12-row**

**Type**: post-run analysis output.

**Already in paper**: structure locked (line 244-275); current placeholders `\todo{TBD}`.

**Source**: 6 Full runs × analysis pass. Hard rows derived from Full by `problem_id` slicing.

**Mock preview**:

| Model | Access | Split | Pass@1 | Blame@1 | Gap | Outside-G | AvgTurns |
|-------|--------|-------|-------:|--------:|----:|----------:|---------:|
| **Open dense** ||||||||
| Qwen3.5-27B | local | Full | 72.4 | 38.2 | 34.2 | 18.3 | 2.81 |
| Qwen3.5-27B | local | Hard | 51.6 | 17.4 | 34.2 ± 6.1 | 29.7 | 3.40 |
| Qwen3.6-27B | local | Full | 81.5 | 42.7 | 38.8 | 16.9 | 2.62 |
| Qwen3.6-27B | local | Hard | 64.8 | 21.2 | 43.6 ± 5.3 | 27.4 | 3.29 |
| **Open MoE** ||||||||
| Qwen3.6-35B-A3B | local | Full | 83.2 | 44.1 | 39.1 | 15.8 | 2.58 |
| Qwen3.6-35B-A3B | local | Hard | 66.2 | 19.6 | 46.6 ± 5.0 | 25.9 | 3.24 |
| GLM-4.7-Flash | local | Full | 76.8 | 36.5 | 40.3 | 20.2 | 2.75 |
| GLM-4.7-Flash | local | Hard | 58.7 | 15.8 | 42.9 ± 5.8 | 32.1 | 3.35 |
| **Reasoning-distilled** ||||||||
| DeepSeek-R1-Distill-Qwen-32B | local | Full | 78.5 | **51.3** | **27.2** | 14.2 | 3.05 |
| DeepSeek-R1-Distill-Qwen-32B | local | Hard | 60.4 | 28.6 | 31.8 ± 5.4 | 21.5 | 3.68 |
| **Closed frontier** ||||||||
| Gemini-3.1-Pro Preview | API | Full | **91.3** | 39.8 | 51.5 | 12.6 | 2.45 |
| Gemini-3.1-Pro Preview | API | Hard | **76.2** | 14.7 | **61.5 ± 4.6** | 23.8 | 3.18 |

**What the mocks encode**:
- **Frontier (Gemini) highest Pass@1 (91.3 / 76.2)** but gap STILL largest (51.5 / 61.5) — paper's main claim
- **Reasoning model (DeepSeek) has the smallest gap** (27.2 / 31.8) and highest Blame@1 — supports "reasoning helps attribution"
- **All 6 models show a >25-pt gap on Hard** — gap is not model-specific
- Hard amplifies the gap by 5-20 pts for every model

**Generated by**: `analysis_script` consuming `out/{model}_full.json` × 6.

---

### 🟡 Figure 2 — `fig:outside-g-scatter` — Outside-G vs RegressionRate

**Type**: post-run analysis output (replaces / supplements `tab:diffusion-validation`).

**Status**: code ready (`code/scripts/make_figures.py:fig1_outside_g_vs_regression`); mock preview at `mock_results/figures/fig1_outside_g_vs_regression.pdf`.

**Mock preview render**:

![](mock_results/figures/fig1_outside_g_vs_regression.png)

(actual mock has n=2610 per-edit points across 6 models, r=0.69 — paper claim will be r ≈ 0.62 over real data)

**Caption (locked)**: "Outside-$G$ behaviorally validates against newly introduced regressions. Each point is a single (P_t, P_{t+1}) edit from the 6-model evaluation matrix on \tbh{}; n = total per-edit transitions. The linear fit reports Pearson $r$ with task-bootstrap 95% CI."

**Generated by**: `code/scripts/make_figures.py --records out/all_records.jsonl`.

---

### 🟡 Table 6 — `tab:fault-family` — **already has REAL numbers**

**Type**: dataset-derived (not run-derived).

**Status**: 🟢 ready (live data, already in main.tex).

**Content** (already locked in main.tex line 348-372):

| Family | Easy-Med | Hard | VeryHard+ | Total |
|--------|---------:|-----:|----------:|------:|
| Boundary / off-by-one | 363 | 196 | 206 | 765 |
| Dependency misuse | 112 | 47 | 18 | 177 |
| Omission / missing branch | 47 | 27 | 14 | 88 |
| Wrong operator / condition | 37 | 23 | 17 | 77 |
| Corner-case / type | 6 | 0 | 0 | 6 |
| **Total** | **565** | **293** | **255** | **1113** |

---

### 🟡 Table 7 — `tab:diffusion-validation` — Outside-G vs RegRate single-row

**Type**: post-run analysis output.

**Mock preview**:

| Pair | n | Result | Interpretation |
|------|--:|--------|----------------|
| Outside-$G$ vs. RegressionRate | 2614 | $r=0.62$ [0.57, 0.66], $p<0.001$ | Edits outside the active fault neighborhood are associated with newly introduced failures. |

n = 6 models × 128 Hard problems × ~3.4 avg edit transitions per problem ≈ 2614.

**Decision**: If we have Figure 2 (scatter), keep this table as a tight summary or fold it into the figure caption. **Recommend: keep both** — figure shows the relationship visually, table gives the exact CI a reviewer can quote.

---

### 🟢 Table 8 — `tab:taxonomy` — 5-mode trace signature

**Type**: descriptive (already locked in main.tex line 425-441).

**Action**: optionally add a frequency column (next table).

---

### 🟡 Table 9 — `tab:taxonomy-freq` — taxonomy frequency (NEW)

**Type**: post-run analysis output. **PROPOSAL: add this as a small sub-table or extra column on Table 8.**

**Mock preview** (averaged across 6 models on Hard):

| Mode | Count | Fraction |
|------|------:|---------:|
| precise_repair | 249 | 32.4% |
| symptom_patch | 144 | 18.7% |
| semantic_drift | 187 | 24.3% |
| regression_loop | 120 | 15.6% |
| diagnostic_recovery | 52 | 6.8% |
| unclassified | 17 | 2.2% |

**Story**: precise_repair is only 1/3 of trajectories even on Hard, meaning 2/3 of trajectories show some form of process failure visible to TraceBench but invisible to outcome-only metrics.

**Generated by**: `src/evaluation/failure_modes.py:classify_all`.

---

### 🟡 Table 10 — `tab:early-drift` — Hit/Miss stratification

**Type**: post-run analysis output.

**Already in paper**: structure locked (line 410-422); current placeholders `\todo{TBD}`.

**Mock preview**:

| Downstream signal | Miss − Hit | Bootstrap 95% CI |
|-------------------|------------|------------------|
| Cumulative patch size | +14.2 lines | [+10.8, +17.6] |
| Outside-$G$ | +19.6 pts | [+16.1, +23.0] |
| Final Blame@1 | −32.4 pts | [−36.0, −28.7] |

**Generated by**: `src/evaluation/drift_stratifier.py:stratify_problems`.

---

## MAIN TEXT — Section 6 (Release, Limitations, Conclusion)

### 🟡 Table 11 — `tab:cost` — cost accounting

**Type**: derived from runner logs.

**Mock preview**:

| Model | Calls | In tok (M) | Out tok (M) | GPU-h | API $ | Parse fail % |
|-------|------:|-----------:|------------:|------:|------:|-------------:|
| Qwen3.5-27B (BF16) | 2402 | 18.2 | 4.5 | 2.1 | $0 | 3.4 |
| Qwen3.6-27B (BF16) | 2402 | 18.4 | 4.7 | 2.0 | $0 | 2.1 |
| Qwen3.6-35B-A3B (BF16, MoE 3B-act) | 2402 | 18.5 | 4.8 | 1.4 | $0 | 1.8 |
| GLM-4.7-Flash (AWQ-int4) | 2402 | 17.9 | 4.6 | 1.7 | $0 | 5.6 |
| DeepSeek-R1-Distill-Qwen-32B (AWQ-int4) | 2402 | 19.4 | 6.2 | 2.5 | $0 | 2.8 |
| Gemini-3.1-Pro Preview (Standard API) | 2402 | 18.7 | 5.0 | 0.0 | **$97.4** | 1.2 |
| **Total** | 14412 | 111.1 | 29.8 | 11.7 H100-h | **$97.4** | avg 2.8% |

**Generated by**: `runner` logs (token counts) + sandbox sandbox subprocess time.

---

## APPENDIX

### 🟡 Figure A1 — per-turn pass/blame dynamics (OPTIONAL P2)

**Type**: 2×3 grid (6 models × {Pass curve, Blame curve} over turns 1-10).

**Status**: P2, can be skipped if space tight. Mock data available in `mock_bundle.json`.

### 🟡 Table A1 — `tab:difficulty-bands` — Easy-Med / Hard / VeryHard+ stratification

**Mock preview** (averaged across 6 models on Full):

| Band | n | Avg turns | Pass@1 | Blame@1 | Gap | Outside-$G$ | RegRate |
|------|--:|----------:|-------:|--------:|----:|------------:|--------:|
| Easy / Medium | 411 | 2.21 | 86.3 | 46.2 | 40.1 | 14.7 | 8.4 |
| Hard | 210 | 3.04 | 74.5 | 33.8 | 40.7 | 21.2 | 13.1 |
| VeryHard+ | 190 | 3.62 | 61.4 | 22.7 | 38.7 | 27.9 | 17.5 |

**Story**: Gap is roughly CONSTANT across bands (40 pts), but Outside-G + RegRate + AvgTurns rise with difficulty — supports "Hard concentrates process signal, not gap magnitude".

**Generated by**: `src/evaluation/difficulty_slicer.py:slice_by_band`.

### 🟡 Table A2 — `tab:fault-family-perf` — fault-family performance breakdown

**Mock preview** (on Qwen3.6-35B-A3B Full as representative):

| Family | Count | Pass@1 | Blame@1 | Gap | Outside-$G$ | RegRate |
|--------|------:|-------:|--------:|----:|------------:|--------:|
| Boundary / off-by-one | 765 | 87.6 | 51.8 | 35.8 | 11.4 | 6.8 |
| Dependency misuse | 177 | 72.3 | 29.4 | 42.9 | 21.7 | 14.2 |
| Omission / missing branch | 88 | 78.4 | 35.7 | 42.7 | 18.6 | 11.8 |
| Wrong operator / condition | 77 | 81.2 | 44.6 | 36.6 | 15.3 | 9.4 |
| Corner-case / type | 6 | 66.7 | 33.3 | 33.4 | 24.8 | 16.7 |

**Story**: Dependency misuse has the largest gap (42.9) — cross-region attribution is hardest. Boundary errors are easiest to find AND fix.

### 🟡 Table A3 — `tab:dry-run` — Day 0 calibration

**Mock preview** (30 stratified tasks × 6 models = 180 runs on Day 0):

| Model | n | Parse OK | Empty blame | Code OK | Timeout | Avg latency (s) |
|-------|--:|---------:|------------:|--------:|--------:|----------------:|
| Qwen3.5-27B | 30 | 28 (93%) | 3 | 29 | 1 | 18.4 |
| Qwen3.6-27B | 30 | 29 (97%) | 2 | 30 | 0 | 14.7 |
| Qwen3.6-35B-A3B | 30 | 29 (97%) | 2 | 30 | 0 | **8.3** |
| GLM-4.7-Flash | 30 | 27 (90%) | 4 | 29 | 1 | 11.5 |
| DeepSeek-R1-Distill-Qwen-32B | 30 | 28 (93%) | 2 | 29 | 1 | 24.6 |
| Gemini-3.1-Pro Preview | 30 | 30 (100%) | 1 | 30 | 0 | 6.2 |

**Story**: confirms protocol works for all 6 models before Day 1 full push; GLM has highest parse failure (90%) — flag for prompt-engineering pass on Day 1 if needed.

### 🟡 Table A4 — `tab:continuity` — historical reference rows

**Type**: appendix continuity (re-using cached numbers from earlier paper drafts / NeurIPS sibling).

**Content**:

| Model | Access | Split | Pass@1 | Blame@1 | Gap | Source |
|-------|--------|-------|-------:|--------:|----:|--------|
| Qwen3-Coder-480B-A35B | API (Together) | Full | 86.9 | 49.5 | 37.4 | prior draft |
| Qwen3-Coder-480B-A35B | API (Together) | Hard | 66.9 | 13.1 | 53.8 ± 5.7 | prior draft |
| Claude-4.5 Sonnet | API (Anthropic) | Full | 95.8 | 31.2 | 64.6 | prior draft |
| Claude-4.5 Sonnet | API (Anthropic) | Hard | 88.8 | 1.7 | 87.1 ± 3.8 | prior draft |
| Qwen3-Coder-30B-A3B | local (H100) | Hard | 31.3 | n/a | n/a | NeurIPS sibling Qwen3-32B trace, aggregate only |

**Purpose**: show paper claims persist across more models than the 6 in the main table, without forcing us to re-run on Anthropic / Together.

### (optional) 🟡 Table A5 — `tab:turn-budget` — turn-budget sensitivity (P1, free on H100)

**Type**: post-run, free local additional experiment.

**Spec**: Qwen3.6-35B-A3B × Hard × T_max ∈ {3, 5, 8, 10}.

**Mock preview**:

| T_max | Pass@1 | Blame@1 | Gap | Avg turns used | Marginal Pass per +turn |
|------:|-------:|--------:|----:|---------------:|------------------------:|
| 3 | 51.8 | 17.2 | 34.6 | 2.34 | — |
| 5 | 66.2 | 19.6 | 46.6 | 3.24 | +7.2 |
| 8 | 72.4 | 21.3 | 51.1 | 4.05 | +2.1 |
| 10 | 74.1 | 22.0 | 52.1 | 4.41 | +0.8 |

**Story**: Pass@1 plateaus around T_max=8; gap MONOTONICALLY widens with more turns (more time to drift) — defeats reviewer counter "5 turns is too few".

---

## Mock-vs-real comparison plan

After Day 3 analysis pass, run `mock_diff.py` to compute |mock - real| for every metric. Large discrepancies (>15 pts) trigger sanity investigation. Expected absolute differences:

| Metric | Expected real |Δ vs mock| |
|--------|--------------:|
| Pass@1 | ±10 pts | (mocks chosen to be plausible) |
| Blame@1 | ±15 pts | (high uncertainty until first model finishes) |
| Outside-G | ±8 pts | (well-defined metric, low variance) |
| RegressionRate | ±5 pts | (well-defined) |
| r in Figure 2 | ±0.15 | (mock r=0.69 vs claim 0.62) |

---

## Mock data location

```
mock_results/
├── mock_bundle.json                    # all tables as JSON
├── mock_per_problem_records.jsonl      # 2610 per-edit points for Fig 2
└── figures/
    └── fig1_outside_g_vs_regression.pdf  # mock Figure 2 PDF + PNG
```

Regenerate: `python code/scripts/generate_mock_results.py --output-dir mock_results/`

---

## What goes where in the paper (mapping summary)

| Paper location | Artifact | Type | Source |
|----------------|----------|------|--------|
| §1 | Figure 1 (overview) | descriptive | LaTeX inline, ready |
| §2 | Table 2 (benchmark matrix) | positioning | LaTeX inline, ready |
| §3 | Table 3 (splits) | dataset stat | already locked |
| §4 | Table 4 (metrics) | descriptive | LaTeX inline, ready |
| §5.1 (outcome) | **Table 5 (gap, 12-row)** | **post-run main result** | analysis_pass.py |
| §5.1 (outcome) | Table 6 (reporting) | descriptive | already in main.tex |
| §5.2 (process) | Table 7 (fault family) | dataset-derived | already with real numbers |
| §5.2 (process) | **Figure 2 (scatter)** | **post-run** | make_figures.py |
| §5.2 (process) | Table 7' (diffusion validation row) | post-run | analysis_pass.py |
| §5.2 (process) | Table 8 (taxonomy) | descriptive | already in main.tex |
| §5.2 (process) | Table 9 (taxonomy freq) | **NEW; post-run** | failure_modes.py |
| §5.2 (process) | Table 10 (early drift) | post-run | drift_stratifier.py |
| §6 | Table 11 (cost) | post-run | runner logs |
| App A | Figure A1 (per-turn dynamics) | P2 optional | make_figures.py extension |
| App B | Table A1 (difficulty bands) | post-run | difficulty_slicer.py |
| App C | Table A2 (fault family perf) | post-run | analysis_pass.py |
| App D | Table A3 (dry-run) | Day 0 output | scripts/dry_run_calibration.py |
| App E | Table A4 (continuity) | re-use cached | manual |
| App F | Table A5 (turn budget) | P1 optional | scripts/turn_budget_sweep.py |
