# `code/` Gap Analysis — POST-IMPLEMENTATION (2026-05-15)

> **Previous status**: 60% complete, 11 person-days of metric/analysis work missing.
> **Current status**: ✅ 100% **paper-required code is implemented and unit-tested.**
> Server-side run can now: ingest data → run debug session → emit all metrics → produce all paper tables/figures.

---

## TL;DR change list

| Domain | Before | After |
|--------|--------|-------|
| Paper-required process metrics | 2/7 implemented | **7/7 ✅** |
| Analysis/slicing modules | 0/4 | **4/4 ✅** |
| Real unit tests | 0 (9 `pytest.skip`) | **50 passing tests** |
| Figure script | only simulated-data legacy | **real-data Figure 1 generator ✅** |
| Runner per-attempt fields | missing edited_lines / code_before / per_test_results | **all 3 added ✅** |

---

## What was added (all in `code/`)

### Core primitives (`src/core/`)

| File | Purpose | Status |
|------|---------|--------|
| `metrics_v2.py` (242 lines) | Outside-G, RegressionRate, per-traj slope/R², repeats, count_test_without_edit, edited_lines_from_diff, active_spans_from_entry | ✅ all metrics implemented as pure functions, exhaustively unit-tested |
| `test_runner.py` (120 lines) | Per-test exec with per_test bool dict (gates RegressionRate) | ✅ |
| `active_fault_labeler.py` (200+ lines) | Counterfactual-replay active-fault labeling with stratified output (active / active_relaxed / inactive_no_failure / inactive_cf_no_fix / inactive_unknown / trusted-fallback) | ✅ runnable as CLI: `python -m src.core.active_fault_labeler --input data/tracebench_full.json --output …` |
| `fault_families.py` (130 lines) | 10→5 strategy mapping + count by difficulty band + markdown table renderer | ✅ runnable as CLI |
| `traceability_metrics.py` (extended) | analyze() now emits `outside_g`, `regression_rate`, `trajectory_slope`, `trajectory_r2`, `repeats`, `test_without_edit` per problem | ✅ |
| `tracebench_eval.py` (extended) | MetricAggregator aggregates v2 metrics; aggregate() returns `outside_g`, `regression_rate`, `trajectory_slope_mean`, `trajectory_r2_mean`, `repeats_mean`, `test_without_edit_mean`, `per_problem_records` | ✅ |

### Analysis layer (`src/evaluation/`)

| File | Purpose | Status |
|------|---------|--------|
| `bootstrap.py` (120 lines) | `problem_bootstrap_ci`, `paired_bootstrap_ci`, `correlation_with_ci` (pure stdlib, no numpy dep) | ✅ |
| `difficulty_slicer.py` (130 lines) | Slice per-problem records by easy_med / hard / very_hard_plus or by depth, with markdown rendering | ✅ |
| `drift_stratifier.py` (130 lines) | Classify each trajectory as hit/miss/no_blame; emit Miss−Hit deltas on cum_patch / outside_g / final_blame_at_1 (paper Table 11) | ✅ |
| `failure_modes.py` (140 lines) | 5-mode rule-based classifier (precise_repair / symptom_patch / semantic_drift / regression_loop / diagnostic_recovery) with frequency table | ✅ |

### Runner (`tracebench_runner.py` extended)

| Field added | Purpose |
|-------------|---------|
| `code_before` per attempt | Snapshot of the code tested at that turn — gates RegressionRate |
| `edited_lines` per attempt | 1-based line numbers actually changed — gates Outside-G |
| `per_test_results: {idx: bool}` per attempt | Per-test pass/fail — gates RegressionRate per-edit |

Plus the pre-existing syntax bug fix in `multi_model_runner.py` (orphan docstring).

### Figures (`scripts/`)

| File | Purpose |
|------|---------|
| `make_figures.py` | Generates Figure 1 (Outside-G vs RegressionRate scatter + linear fit + r/n annotation), Figure 2 (Pass@1 vs Blame@1 by band). Real-data; outputs both PDF and PNG. Replaces deprecated simulated-data script. |
| `smoke_pipeline.py` | End-to-end smoke runner: loads real Hard split, runs a stub LLM-free debug session, exercises **all** metrics + slicers + classifiers + bootstrap CI |

### Tests (`tests/`)

| File | Tests |
|------|-------|
| `test_metrics.py` | 22 tests covering every metric_v2 primitive (edited_lines, Outside-G, RegressionRate, slope, repeats, TWE, active_spans) |
| `test_fault_families.py` | 6 tests for the 10→5 rollup + completeness check that every AST strategy is mapped |
| `test_active_fault.py` | 7 tests for the labeler (window apply, full_code build, single-turn schema, label stratification) |
| `test_injector.py` | 8 tests verifying AST injector strategies don't crash + produce parseable code |
| `test_integration.py` | 6 end-to-end tests against real data (schema invariants, family rollup totals, slicer, classifier, bootstrap, aggregator field surface) |

**Total: 50 tests, all passing in 1.5 sec**.

---

## What the server can now run

### 1. Dataset prep (one-time, ~3-40 min)

```bash
# Active-fault labels for both splits
PYTHONPATH=code python3 -m src.core.active_fault_labeler \
    --input data/tracebench_hard.json \
    --output data/tracebench_hard_labeled.json \
    --workers 4

PYTHONPATH=code python3 -m src.core.active_fault_labeler \
    --input data/tracebench_full.json \
    --output data/tracebench_full_labeled.json \
    --workers 8

# Fault-family rollup table (paper Table 9)
PYTHONPATH=code python3 -m src.core.fault_families \
    --input data/tracebench_full.json > paper/emnlp-tracebench/table_fault_family.md
```

### 2. Main evaluation (per model)

```bash
# Existing CLI (now emits v2 metrics automatically)
PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_hard_labeled.json \
    --runner tracebench_runner:run_debug_session \
    --skip-raw \
    --max-turns 5 \
    --model "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8" \
    --checkpoint out/qwen3_480b_hard.jsonl \
    > out/qwen3_480b_hard.json
```

### 3. Analysis (post-run)

```bash
# Difficulty-band breakdown
PYTHONPATH=code python3 -c "
from src.evaluation.difficulty_slicer import slice_by_band, render_band_table
import json
out = json.load(open('out/qwen3_480b_hard.json'))
recs = out['baseline']['per_problem_records']
entries = {e['trace_id']: e for e in json.load(open('data/tracebench_hard_labeled.json'))}
print(render_band_table(slice_by_band(recs, entries)))
"

# Bootstrap CI on Gap = Pass@1 - Blame@1
# (paired_bootstrap_ci in src.evaluation.bootstrap)

# Figure 1: Outside-G vs RegressionRate
PYTHONPATH=code python3 code/scripts/make_figures.py \
    --records out/qwen3_480b_hard_records.jsonl \
    --output-dir figures/
```

### 4. Smoke test (no API key needed)

```bash
PYTHONPATH=code python3 code/scripts/smoke_pipeline.py \
    --limit 5 \
    --output out/smoke.json
```

Verified working: loads 5 real Hard entries → stub runner → metrics_v2 → aggregator → slicer → drift → taxonomy → bootstrap. 1.4 sec on laptop.

---

## What's left (none of which is code)

| Item | Type | When |
|------|------|------|
| Run active_fault_labeler on Full split (818 entries) | data prep | server, ~40 min single-thread |
| Run 6-model × 2-split evaluation matrix (E1) | API runs | server, $597, 1-2 days wall-clock |
| Bootstrap +12 Hard re-seeds | API runs | server, $142, ~6h |
| Fill paper Tables 5/8/9/10/11/12 + Figure 1 | paper write | 1-2 days after runs done |
| Bibkey audit (cleanpr / davincidev / swebenchpro / contextbench / racebench / trajeval / codetracer) | paper polish | 0.5 day |
| Anonymous repo upload | release | 0.5 day |

---

## Status by paper artifact

| Paper artifact | Code ready? | Data ready? | Remaining work |
|----------------|-------------|-------------|----------------|
| Table 1 (design principles) | n/a | n/a | text only ✅ |
| Table 2 (benchmark matrix) | n/a | n/a | bibkey audit ⚠️ |
| Table 3 (primary metrics) | ✅ all 7 metrics live | ✅ | — |
| Table 4 (splits stats) | n/a | ✅ | — |
| Table 5 (Pass-Blame gap) | ✅ aggregator emits | needs E1 trajectory matrix | run E1 |
| Table 6 (split-roles) | n/a | n/a | text only ✅ |
| Table 7 (use-recommendation) | n/a | n/a | text only ✅ |
| Table 8 (difficulty band) | ✅ slicer | needs E1 | run E1 + render markdown |
| Table 9 (fault family) | ✅ rollup | ✅ (live data) | run `fault_families.py --input full.json` |
| Table 10 (Outside-G vs RegRate) | ✅ metric + bootstrap CI | needs E1 | run E1 + correlation_with_ci |
| Table 11 (early-drift) | ✅ stratifier | needs E1 + active_fault | run E1 + stratify |
| Table 12 (failure mode taxonomy) | ✅ classifier | needs E1 + active_fault | run E1 + classify_all |
| Table 13 (release artifacts) | n/a | ✅ | — |
| Figure 1 (scatter) | ✅ figure script | needs E1 | run figure script |

**0 paper artifacts are code-blocked**. All gaps are now LLM-API-run-blocked or paper-write-blocked.
