# 完整实验表 + 现有数据盘点

> 编写: 2026-05-15
> 策略: **max H100 (6 local SOTA models) + 2 API SOTA (GPT-5.5 + Gemini-3.1-Pro)**
> 替代 `SERVER_RUN_PLAN.md`，覆盖更准确的 May 2026 SOTA model landscape

---

## Part 1 — SOTA Model Landscape (May 2026)

我用 WebSearch 核对了当前 SOTA。重要事实:

### Closed-source frontier (API):

| 模型 | 发布 | $/MT in | $/MT out | SOTA benchmark |
|------|------|--------:|---------:|-----------------|
| **GPT-5.5** (OpenAI) | Apr 23, 2026 | $5.00 | $30.00 | Terminal-Bench 2.0 **82.7%** ⭐, SWE-bench Pro 58.6% |
| **Gemini-3.1-Pro** (Google) | Apr 2026 | $2.00 | $12.00 | SWE-bench Verified **77.2%** (3 Pro), Terminal-Bench 2.0 54.2% |
| GPT-5 | Earlier 2026 | $1.25 | $10.00 | (older frontier) |
| o4-mini (OpenAI reasoning) | 2026 | $1.10 | $4.40 | budget reasoning baseline |

### Open-source frontier ≤32B (H100 single-GPU):

| 模型 | 类型 | 总参数 | 激活 | SOTA benchmark | 量化建议 |
|------|------|------:|------:|-----------------|----------|
| **Qwen3.6-27B** | dense | 27B | 27B | SWE-bench Verified **77.2%** (= Gemini-3.1-Pro!), HumanEval 91%+ | BF16 fits, AWQ optional |
| **Qwen3-Coder-30B-A3B** | MoE | 30B | 3B | agentic coding focused | BF16 fits (60GB) |
| **Qwen2.5-Coder-32B** | dense | 32B | 32B | HumanEval 91% (= GPT-4o), competitive programming strong | **AWQ-int4 must** |
| **GLM-4.7-Flash** | MoE | 30B | ? | agentic coding 40.7%, low-latency | AWQ-int4 |
| **DeepSeek-R1-Distill-Qwen-32B** | dense reasoning | 32B | 32B | reasoning-distilled baseline | **AWQ-int4 must** |
| **Qwen2.5-Coder-14B** | dense | 14B | 14B | size-curve baseline | BF16 fits |

**关键发现**: Qwen3.6-27B 现在 **dense 27B 已经超越上一代 397B-A17B MoE** on SWE-bench Verified (77.2 vs 76.2). 这意味着我们在 H100 单卡上可以跑到 "API frontier 同 level" 的本地 open-weight model. 对 paper "reproducibility" 卖点非常有利。

---

## Part 2 — 完整实验表

### 2.1 主表 (paper Table 5 — "Pass-Blame gap across 8 models")

| # | Model | Vendor | Access | Size | Quant | Splits | Seeds (Hard) | $ | H100 (h) |
|---|-------|--------|--------|-----:|-------|--------|-------------:|--:|---------:|
| 1 | **Qwen3.6-27B** | Alibaba | local | 27B dense | BF16 | Full + Hard | 3 | $0 | ~2 |
| 2 | **Qwen3-Coder-30B-A3B** | Alibaba | local | 30B MoE (3B act) | BF16 | Full + Hard | 3 | $0 | ~1.5 |
| 3 | **Qwen2.5-Coder-32B** | Alibaba | local | 32B dense | AWQ-int4 | Full + Hard | 3 | $0 | ~2 |
| 4 | **GLM-4.7-Flash** | Zhipu | local | 30B MoE | AWQ-int4 | Full + Hard | 3 | $0 | ~2 |
| 5 | **DeepSeek-R1-Distill-Qwen-32B** | DeepSeek | local | 32B dense reasoning | AWQ-int4 | Full + Hard | 3 | $0 | ~2.5 |
| 6 | **Qwen2.5-Coder-14B** | Alibaba | local | 14B dense | BF16 | Full + Hard | 3 | $0 | ~1 |
| 7 | **GPT-5.5** | OpenAI | API | frontier (closed) | — | Full + Hard | 3 | **$369** | API time |
| 8 | **Gemini-3.1-Pro** | Google | API | frontier (closed) | — | Full + Hard | 3 | **$148** | API time |
| **Σ** | 8 rows | | | | | **8×2 = 16 cells × 3 seeds on Hard = 24 Hard runs + 8 Full runs** | | **$517 + buffer** | **12–15 h** |

> 注意: Hard 3-seed = single-seed Full + Hard + 2 extra Hard seeds (paired bootstrap). Full 只跑 single seed (paper Table 5 caption: "Hard-split gaps include paired bootstrap 95% CIs").

### 2.2 Appendix Table A1 (size + cost curve, optional)

| # | Model | Size | Why include |
|---|-------|------|-------------|
| A | Qwen2.5-Coder-7B-Instruct | 7B | bottom of size curve (Hard only) |
| B | StarCoder2-15B | 15B | non-Qwen open baseline (Hard only) |
| C | GPT-5 | API frontier (older) | "previous frontier" comparison (Hard only) |
| D | o4-mini | API reasoning | reasoning-style baseline (Hard only) |

**Appendix cost**: <$30 API + ~2 h H100. Highly optional.

### 2.3 Dataset coverage

每个 model run 都覆盖:

| Dataset | Problems | Turns | Tests | Injections |
|---------|---------:|------:|------:|------------:|
| **TraceBench-Full** | 818 | 2377 | 7165 | 1113 |
| **TraceBench-Hard** | 128 | 438 | 1511 | 179 |

总 LLM API calls per model = 2377 + 438 = **2815 turn-rounds** (single seed both splits).
With 3-seed Hard bootstrap: 2377 + 3×438 = **3691 turn-rounds**.

### 2.4 Run grand-total

```
=== 24 cells in main matrix ===
Local runs:    6 model × 2 split × (single seed + 2 bootstrap on Hard) = 24 local executions
API runs:      2 model × 2 split × (single seed + 2 bootstrap on Hard) =  8 API executions

=== Cost ===
Local (H100):  $0 (electricity / depreciation negligible)
API:           GPT-5.5 + Gemini-3.1-Pro = $517 ($394 single-pass + $123 bootstrap)
Buffer 35%:    $181
GRAND TOTAL:   ~$698

=== Time ===
H100 (sequential):  12-15 h (overnight × 2)
API runs:           parallel to H100, ~3-4 h walltime
Data prep:          ~45 min CPU (active_fault labeling)
TOTAL:              ~2 days from server start to all data collected
```

### 2.5 Run schedule (推荐)

| Day | Phase | Action | Time | Cost |
|-----|-------|--------|------|------|
| **Day 0 PM** | prep | scp tracebench/ to server, install vLLM + google-generativeai, set env vars | 1h | $0 |
| **Day 1 morning** | data prep | `active_fault_labeler` on Full + Hard | 45 min CPU | $0 |
| **Day 1 morning** | sanity | smoke_pipeline.py + 1 model × 10 problems | 30 min | <$1 |
| **Day 1 noon-evening** | local batch 1 | Qwen3.6-27B + Qwen3-Coder-30B-A3B (Full + Hard, 3 seeds each on Hard) | 5-6 h H100 | $0 |
| **Day 1 evening (parallel)** | API batch 1 | GPT-5.5 Full + Hard + 2 extra seeds on Hard | ~3 h API | $369 |
| **Day 2 morning** | local batch 2 | Qwen2.5-Coder-32B + GLM-4.7-Flash + DeepSeek-R1-Distill | 6-7 h H100 | $0 |
| **Day 2 noon (parallel)** | API batch 2 | Gemini-3.1-Pro Full + Hard + 2 extra seeds on Hard | ~3 h API | $148 |
| **Day 2 evening** | local batch 3 | Qwen2.5-Coder-14B (+ appendix models if time) | 1-2 h H100 | $0 |
| **Day 3** | analysis | difficulty bands, drift stratification, taxonomy, Figure 1 | 1 day local | $0 |

**总: 2 天 server time + 1 天分析 = 3 天**.

---

## Part 3 — 现有数据盘点 (data inventory)

### 3.1 Dataset 主体 (✅ ready)

```
~/Desktop/tracebench/data/
├── tracebench_full.json           49 MB    818 problems    multi-turn ✓     paper Table 4 数字全部对得上
├── tracebench_hard.json           21 MB    128 problems    multi-turn ✓     paper Table 4 数字全部对得上
├── oracle_spans.json              46 KB    128 oracle blame labels (Hard only)
├── splits/
│   ├── manifest_full.json         282 KB   818 metadata    {trace_id, rating, difficulty, depth, num_turns, ...}
│   └── manifest_hard.json         46 KB    128 metadata    同上
└── reference_trajectories/
    └── qwen3_32b_trace/            6 MB     128 files       Qwen3-32B × Hard, CLI 格式 (dev reference, 不入主表)
```

| 字段 | Full | Hard | Status | 用途 |
|------|-----:|-----:|--------|------|
| Problems | 818 | 128 | ✅ | paper Table 4 |
| Turns total | 2377 | 438 | ✅ | paper Table 4 |
| Tests total | 7165 | 1511 | ✅ | paper Table 4 |
| Injections | 1113 | 179 | ✅ | paper Table 4 + Table 9 (rollup) |
| Rating mean/median | 1714 / 1600 | 2680 / 2700 | ✅ | paper Table 4 |
| Depth mean | 3.20 | 3.75 | ✅ | paper Table 4 |
| Difficulty (extreme/very_hard/hard/medium/easy/unrated) | 67/123/210/207/204/7 | 67/46/15/0/0/0 | ✅ | paper Table 8 (3-band slice) |
| Codeforces tags | per-problem | per-problem | ✅ | appendix tag analysis |
| Multi-turn (conversation_history) | 100% | 100% | ✅ | runner reads directly |
| `original_target_code` per turn | ✅ | ✅ | ✅ | active_fault counterfactual |
| `original_code` (full clean reference) | ✅ | ✅ | ⚠️ noisy (27% Hard passes own tests) | label fallback, see §3.2 |

### 3.2 派生数据 (待生成, 全部本地 CPU)

| Artifact | 来源 | 输出位置 | 工作 | 时间 |
|----------|------|---------|------|------|
| `tracebench_full_labeled.json` | + `active_faults_per_turn` field | data/ | `python -m src.core.active_fault_labeler --input data/tracebench_full.json --workers 8` | ~6 min @ 8 workers |
| `tracebench_hard_labeled.json` | + `active_faults_per_turn` field | data/ | 同上 (Hard) | ~1 min |
| `table_fault_family.md` | 10→5 family rollup | out/ | `python -m src.core.fault_families --input data/tracebench_full.json` | <1 sec |

### 3.3 待生成的实验数据 (服务器 run)

**24 个 main matrix cells** (8 model × 2 split + Hard 2-seed bootstrap × 8 model):

```
out/                          # 服务器执行后产生
├── checkpoints/
│   ├── qwen3.6_27b_full.jsonl                      ★ to be generated
│   ├── qwen3.6_27b_hard_seed0.jsonl                ★
│   ├── qwen3.6_27b_hard_seed1.jsonl                ★
│   ├── qwen3.6_27b_hard_seed2.jsonl                ★
│   ├── qwen3_coder_30b_a3b_{full,hard_seed0..2}    ★ × 4
│   ├── qwen2.5_coder_32b_{full,hard_seed0..2}      ★ × 4
│   ├── glm47_flash_{full,hard_seed0..2}            ★ × 4
│   ├── deepseek_r1_distill_32b_{full,hard_seed0..2} ★ × 4
│   ├── qwen2.5_coder_14b_{full,hard_seed0..2}      ★ × 4
│   ├── gpt55_{full,hard_seed0..2}                  ★ × 4
│   └── gemini31_pro_{full,hard_seed0..2}           ★ × 4
└── per_problem_records/      # aggregator output for slicing/figure
    └── *.jsonl                                       ★ x 8 (one per model)
```

每个 `*.jsonl` 包含 per-attempt `{code_before, generated_code, edited_lines, blame_spans, patch_spans, per_test_results, success, ...}`.

### 3.4 Code 现状 (✅ all green)

| 模块 | 用途 | 状态 |
|------|------|------|
| `src/core/metrics_v2.py` | Outside-G / RegressionRate / per-traj slope / repeats | ✅ |
| `src/core/active_fault_labeler.py` | counterfactual replay labeling | ✅ CLI |
| `src/core/fault_families.py` | 10→5 rollup | ✅ CLI |
| `src/core/test_runner.py` | per-test bool exec | ✅ |
| `src/core/traceability_metrics.py` | analyze() emits all v2 metrics | ✅ |
| `src/core/tracebench_eval.py` | MetricAggregator aggregates v2 | ✅ |
| `src/evaluation/bootstrap.py` | paired bootstrap CI | ✅ |
| `src/evaluation/difficulty_slicer.py` | easy_med/hard/very_hard_plus 切片 | ✅ |
| `src/evaluation/drift_stratifier.py` | Hit/Miss 分组 | ✅ |
| `src/evaluation/failure_modes.py` | 5-mode 分类器 | ✅ |
| `scripts/make_figures.py` | Figure 1 真数据生成 | ✅ |
| `scripts/smoke_pipeline.py` | LLM-free 端到端 smoke | ✅ |
| `tracebench_runner.py` | multi-turn 调度 + edited_lines + per_test_results 输出 | ✅ |
| `multi_model_runner.py` | OpenAI / Anthropic / Google (Gemini) / local (vLLM) / Together (qwen) | ✅ |
| `tests/` | 50 个 unit + integration tests | ✅ all pass |

---

## Part 4 — Server 启动 Checklist

### Day 0 PM: server prep
```bash
# 1. Push code + data
rsync -av ~/Desktop/tracebench/ user@server:/data/tracebench/

# 2. Server env
ssh user@server
cd /data/tracebench/
python3 -m venv .venv && source .venv/bin/activate
pip install -r code/requirements-eval.txt
pip install vllm>=0.6.2                   # 服务器需要 vllm
pip install google-generativeai>=0.8      # Gemini API
huggingface-cli login                     # 拉量化 model

# 3. Env vars
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=AIza...

# 4. Smoke test
PYTHONPATH=code python3 code/scripts/smoke_pipeline.py --limit 3 --output out/smoke_check.json
# → 应看到 5 项 metric 都 emit 非 None 值
```

### Day 1 AM: data prep
```bash
# Active-fault label both splits
PYTHONPATH=code python3 -m src.core.active_fault_labeler \
    --input  data/tracebench_hard.json \
    --output data/tracebench_hard_labeled.json \
    --workers 8

PYTHONPATH=code python3 -m src.core.active_fault_labeler \
    --input  data/tracebench_full.json \
    --output data/tracebench_full_labeled.json \
    --workers 8

# Fault family table for paper
PYTHONPATH=code python3 -m src.core.fault_families \
    --input data/tracebench_full_labeled.json \
    > out/table_fault_family.md
```

### Day 1-2: launch evaluation runs

**Local (vLLM serve in one terminal, evaluate in another):**
```bash
# Terminal 1: vLLM server
vllm serve Qwen/Qwen3.6-27B \
    --port 8000 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.92

# Terminal 2: TraceBench runner (使用 multi_model_runner 的 local provider)
export OPENAI_API_BASE=http://localhost:8000/v1
export TRACEBENCH_LOCAL_MODEL="Qwen/Qwen3.6-27B"
for seed in 0 1 2; do
    TRACEBENCH_SEED=$seed PYTHONPATH=code python3 code/evaluate.py \
        --tracebench data/tracebench_hard_labeled.json \
        --runner multi_model_runner:run_debug_session \
        --skip-raw --max-turns 5 \
        --checkpoint out/checkpoints/qwen36_27b_hard_seed${seed}.jsonl \
        > out/qwen36_27b_hard_seed${seed}.json
done

# Full split (single seed)
PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_full_labeled.json \
    --runner multi_model_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --checkpoint out/checkpoints/qwen36_27b_full.jsonl \
    > out/qwen36_27b_full.json

# Restart vLLM with next model and repeat
```

**API:**
```bash
# GPT-5.5
PROVIDER=openai MODEL=gpt-5.5 \
    PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_hard_labeled.json \
    --runner multi_model_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --model gpt-5.5 \
    --checkpoint out/checkpoints/gpt55_hard.jsonl \
    > out/gpt55_hard.json

# Gemini-3.1-Pro
PROVIDER=google PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_hard_labeled.json \
    --runner multi_model_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --model gemini-3.1-pro \
    --checkpoint out/checkpoints/gemini31pro_hard.jsonl \
    > out/gemini31pro_hard.json
```

### Day 3: analysis & figures
```bash
# Concat all per-problem records
cat out/*_records.jsonl > out/all_records.jsonl

# Figure 1
PYTHONPATH=code python3 code/scripts/make_figures.py \
    --records out/all_records.jsonl \
    --dataset data/tracebench_full_labeled.json \
    --output-dir paper/emnlp-tracebench/figures/

# All tables (using the helpers in src/evaluation/)
PYTHONPATH=code python3 -c "
from src.evaluation.difficulty_slicer import slice_by_band, render_band_table
from src.evaluation.failure_modes import classify_all, render_taxonomy_table
from src.evaluation.drift_stratifier import stratify_problems
from src.core.metrics_v2 import active_spans_from_entry
import json
# ... (see scripts/build_paper_tables.py — TODO)
"
```

---

## Part 5 — 风险 + 应对 (server 端)

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Qwen3.6-27B BF16 OOM @ 80GB H100 | 中 | 跑挂 | 用 AWQ Q4_K_M (~16.8 GB) — Q4 量化质量损失 minimal |
| 32B 模型 BF16 必然 OOM | 高 | 跑不起来 | 全部 AWQ-int4 量化, vLLM 用 `--quantization awq_marlin` |
| GPT-5.5 在 long-context 翻倍涨价 (>200K) | 低 | cost 2× | TraceBench max prompt < 30K, 不会触发 |
| Gemini-3.1-Pro thinking tokens 偷涨 output | 中 | cost overshoot | Gemini 3.1 没有强制 thinking, output cap=4K 已限制 |
| vLLM blame_spans JSON parse 失败 (open model) | 中 | Blame@1 偏低 | 保留 fallback to empty; paper footnote "JSON adherence is part of the benchmark" |
| API rate-limit (TPM/RPM) | 中 | wall-clock ×2-3 | OpenAI Tier 3+ 账号; Google 默认 ≥60 RPM 足够 |
| 单 model run 卡死 sandbox | 低 | 单 task fail, run 继续 | harness.py 已有 60s timeout |

---

## Part 6 — 关键决策 (你拍板)

| 决策 | 选项 | 推荐 | 理由 |
|------|------|------|------|
| API 模型 | (a) 仅 GPT-5.5 + Gemini-3.1-Pro / (b) +o4-mini / (c) 全跑 | **(a)** | 总 $517 controlled |
| Local 量化 | (a) 全 BF16 / (b) 大 model AWQ-int4, 小 model BF16 (推荐) | **(b)** | 32B BF16 OOM 风险 |
| Bootstrap | (a) Hard 3-seed (8 model) / (b) 仅 main 4 model | **(a)** | paper claim "include CI" 必须 cover 所有主表 row |
| Appendix 加几行 | (a) 0 / (b) 2-3 行 / (c) 4 行 | **(b)** | 性价比 (含 Qwen 7B + StarCoder2) |
| 7B/14B 跑哪个 split | (a) Hard only / (b) Full+Hard | **(a)** | small models 在 Hard 上信号最强 |

---

## Part 7 — 一行总结

✅ **8 主表 row (6 local + 2 API SOTA) + 3-seed Hard bootstrap = $517 API + 12-15 h H100 + 2 天 wall-clock**.
✅ **Data 现状 100% ready** for prep step (active_fault label) + **6 个 local SOTA model 全部能在 H100 80GB 上跑**.
✅ **Paper 主表 8 行 (4 open + 2 closed frontier + 2 reasoning/agentic)** — 比之前 GPT 建议的 6 行还多.

Sources:
- [Introducing GPT-5.5 | OpenAI](https://openai.com/index/introducing-gpt-5-5/)
- [Gemini 3.1 Pro Complete Guide 2026 | NxCode](https://www.nxcode.io/resources/news/gemini-3-1-pro-complete-guide-benchmarks-pricing-api-2026)
- [Gemini 3.1 Pro API Pricing May 2026 | DevTK](https://devtk.ai/en/models/gemini-3-1-pro/)
- [Qwen3.6-27B blog](https://qwen.ai/blog?id=qwen3.6-27b)
- [Qwen3-Coder-30B-A3B-Instruct HF](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)
- [GLM-4.7-Flash vs Qwen3-Coder-30B comparison](https://blogs.novita.ai/glm-4-7-flash-vs-qwen3-coder-30b/)
- [OpenAI API Pricing 2026 | ModelPricing.ai](https://modelpricing.ai/models/openai)
