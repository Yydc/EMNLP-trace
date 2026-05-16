# Server Run Plan — H100 + OpenAI/Google APIs

> 编写: 2026-05-15
> 约束:
> - **1 × H100 80GB** for local inference
> - **OpenAI + Google API** for closed-source baselines (无 Anthropic Claude, 无 Together-hosted 480B)
> - 目标: 在最低成本下产出 paper Table 5 + 4 个派生表 + Figure 1

---

## TL;DR — 推荐方案（一句话）

**4 main rows + 2 appendix rows + 3-seed bootstrap on Hard**, 总成本 **≈ $260 + 6h H100**，主表里两个 closed-frontier + 两个 open，足以打掉 reviewer "全靠闭源 API" 的质疑。

---

## 1. 价格表 (2026-05 listing price, $ per 1M tokens)

per-model cost @ assumed 8K input + 2K output per call × turn-round count (Full=2377, Hard=438):

| Model | Vendor | Tier | Input / Output | **Full** | **Hard** | Hard ×3 (CI) |
|-------|--------|------|---------------|---------:|---------:|------------:|
| GPT-4o | OpenAI | frontier | $2.50 / $10.00 | $95.08 | $17.52 | $52.56 |
| GPT-4.1 | OpenAI | frontier | $2.00 / $8.00 | $76.06 | $14.02 | $42.05 |
| GPT-4o-mini | OpenAI | mini | $0.15 / $0.60 | $5.70 | $1.05 | $3.15 |
| GPT-4.1-mini | OpenAI | mini | $0.40 / $1.60 | $15.21 | $2.80 | $8.41 |
| GPT-4.1-nano | OpenAI | nano | $0.10 / $0.40 | $3.80 | $0.70 | $2.10 |
| o4-mini | OpenAI | reasoning | $1.10 / $4.40 | $41.84 | $7.71 | $23.13 |
| Gemini-2.5-Pro | Google | frontier | $1.25 / $10.00 | $71.31 | $13.14 | $39.42 |
| Gemini-2.5-Flash | Google | mini | $0.30 / $2.50 | $17.59 | $3.24 | $9.72 |
| Gemini-2.5-Flash-Lite | Google | nano | $0.10 / $0.40 | $3.80 | $0.70 | $2.10 |

**Notes**:
- "Hard ×3" = 3 seeds on Hard for paired-bootstrap CI (paper's Table 5 claim)
- Reasoning models (o-series) cost the same per output token, but their hidden CoT can balloon output → assume 1.5–2× higher than listed if used

---

## 2. H100 throughput (local, $0 API cost)

vLLM 0.6+ continuous batching, single H100 80GB, BF16 unless quantized noted:

| Model | Params | Quant | Weights | Tok/s (agg) | **Full (h)** | **Hard (h)** | Both (h) |
|-------|--------|-------|--------:|-------------:|------:|------:|------:|
| Qwen3-Coder-30B-A3B | 30B (3B active, MoE) | BF16 | 60 GB | 8000 | 0.2 | 0.04 | 0.3 |
| Qwen3-Coder-30B-A3B | 30B (3B active, MoE) | AWQ-int4 | 18 GB | 12000 | 0.1 | 0.03 | 0.2 |
| Qwen2.5-Coder-32B | 32B | BF16 | 64 GB | 1500 | 1.1 | 0.21 | 1.4 |
| Qwen2.5-Coder-32B | 32B | AWQ-int4 | 18 GB | 4000 | 0.4 | 0.08 | 0.5 |
| DeepSeek-R1-Distill-Qwen-32B | 32B | AWQ-int4 | 18 GB | 3500 | 0.5 | 0.09 | 0.6 |
| Qwen2.5-Coder-14B | 14B | BF16 | 28 GB | 4000 | 0.4 | 0.08 | 0.5 |
| Qwen2.5-Coder-7B | 7B | BF16 | 14 GB | 8000 | 0.2 | 0.04 | 0.3 |
| StarCoder2-15B | 15B | BF16 | 30 GB | 3500 | 0.5 | 0.09 | 0.6 |

**Critical caveats**:
- 上表只统计 **LLM 推理**时间。实际 wall-clock 还要加 **sandbox 测试执行**: 818 + 128 = 946 problem × 平均 2.9 turn × ~5 sec sandbox = **~4 h sandbox**（8-way parallel 降到 **~30 min**）
- 所以单 model on Full+Hard 真实 wall-clock ≈ **LLM_time + 30 min sandbox**
- 32B BF16 在 H100 80GB 上很紧 (64GB weights + KV cache)。**强烈建议用 AWQ-int4 量化** — 速度 ×2-3, 质量损失对 code 任务可忽略
- 30B-A3B (MoE) 因为只激活 3B params，single-H100 单卡跑起来比 dense 32B 快 4-6 倍

---

## 3. 5 个方案 — 选 Strategy B 即可

| Strategy | 模型组合 | API cost | Bootstrap | H100 time | 适用场景 |
|----------|---------|---------:|-----------|----------:|---------|
| **A. Minimal viable** | 2 local + 2 nano (GPT-4.1-nano + Gemini-Flash-Lite) | **$9** | none | 4 h | budget 极紧；预测 closed-source signal 会很弱 |
| **B. 推荐 — Recommended** ⭐ | 2 local + GPT-4o + Gemini-2.5-Pro + 3-seed bootstrap on Hard | **$260** | Hard ×3 (4 model) | 6 h | **paper 主表对得起 reviewer，且不烧钱** |
| **C. Broad coverage** | 4 local + GPT-4o + GPT-4o-mini + Gemini-Pro + Gemini-Flash + bootstrap | **$295** | Hard ×3 (4 model) | 12 h | 想在 appendix 把价格 / size 曲线画全 |
| **D. With reasoning row** | B + o4-mini (single seed) | **$310** | Hard ×3 (4 model) | 6 h | 想 claim "even reasoning models exhibit the gap" |
| **E. Full coverage** | C + o4-mini + GPT-4.1 | **$465** | Hard ×3 (6 model) | 14 h | budget 充裕；想覆盖所有主流 closed model family |

### Strategy B 详细成本 (推荐)

```
Local (H100):
  Qwen3-Coder-30B-A3B AWQ-int4     Full + Hard      $0    0.2 h LLM + 30 min sandbox
  Qwen2.5-Coder-32B   AWQ-int4     Full + Hard      $0    0.5 h LLM + 30 min sandbox

API:
  GPT-4o              single seed   Full + Hard      $113
                      + 2 extra Hard seeds (bootstrap)  + $35   (= 2 × $17.52)
  Gemini-2.5-Pro      single seed   Full + Hard      $85
                      + 2 extra Hard seeds (bootstrap)  + $26   (= 2 × $13.14)

Appendix (optional but cheap):
  GPT-4o-mini         single seed   Full + Hard       $7
  DeepSeek-R1-Distill-Qwen-32B AWQ Hard only          $0   ~0.1 h LLM + 5 min sandbox

────────────────────────────────────────────────────────────────────────────
SUBTOTAL                                                $266 + ~3-4 h H100
Buffer (35% for retries / rate-limit / bad calls)        $93
GRAND TOTAL                                            ~$360
H100 GRAND total                                        4-6 h (sandbox dominates)
```

---

## 4. Paper Table 5 (主表) 在 Strategy B 下的最终样子

```latex
\begin{tabular}{lllrrrrr}
\toprule
Model              & Access  & Split & Pass@1 & Blame@1 &  Gap & Outside-G & AvgTurns \\
\midrule
Qwen3-Coder-30B-A3B  & local  & Full  & TBD    & TBD     & TBD  & TBD       & TBD      \\
Qwen3-Coder-30B-A3B  & local  & Hard  & TBD ±  & TBD ±   & TBD ± & TBD       & TBD      \\
Qwen2.5-Coder-32B    & local  & Full  & TBD    & TBD     & TBD  & TBD       & TBD      \\
Qwen2.5-Coder-32B    & local  & Hard  & TBD ±  & TBD ±   & TBD ± & TBD       & TBD      \\
GPT-4o               & API    & Full  & TBD    & TBD     & TBD  & TBD       & TBD      \\
GPT-4o               & API    & Hard  & TBD ±  & TBD ±   & TBD ± & TBD       & TBD      \\
Gemini-2.5-Pro       & API    & Full  & TBD    & TBD     & TBD  & TBD       & TBD      \\
Gemini-2.5-Pro       & API    & Hard  & TBD ±  & TBD ±   & TBD ± & TBD       & TBD      \\
\bottomrule
\end{tabular}
```

8 rows. 2 open + 2 closed. Hard 4 行都有 paired bootstrap 95% CI（±）。直接堵住 reviewer "4 行不够" 的反应。

Appendix Table A1 加 GPT-4o-mini + DeepSeek-R1-Distill-Qwen-32B 两行，appendix Table A2 给出 difficulty band × model 的完整 6 行 × 3 band 矩阵。

---

## 5. 执行顺序 (server-side)

### Phase 0 — 数据 prep (本地 CPU, ~45 min total)

```bash
# 1. Active-fault label on both splits
PYTHONPATH=code python3 -m src.core.active_fault_labeler \
    --input data/tracebench_hard.json \
    --output data/tracebench_hard_labeled.json \
    --workers 8
# (~6 min on 8-core)

PYTHONPATH=code python3 -m src.core.active_fault_labeler \
    --input data/tracebench_full.json \
    --output data/tracebench_full_labeled.json \
    --workers 8
# (~40 min on 8-core)

# 2. Fault-family rollup table (paper Table 9)
PYTHONPATH=code python3 -m src.core.fault_families \
    --input data/tracebench_full_labeled.json \
    > out/table_fault_family.md
```

### Phase 1 — Local model runs on H100 (~3-4 h)

```bash
# vLLM server for Qwen3-Coder-30B-A3B
docker run --gpus all -p 8000:8000 vllm/vllm-openai \
    --model Qwen/Qwen3-Coder-30B-A3B-Instruct \
    --quantization awq_marlin \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.92

# In a separate shell, run TraceBench against local server:
OPENAI_API_BASE=http://localhost:8000/v1 \
OPENAI_API_KEY=EMPTY \
TRACEBENCH_MODEL="Qwen/Qwen3-Coder-30B-A3B-Instruct" \
PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_hard_labeled.json \
    --runner tracebench_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --checkpoint out/qwen30b_hard.jsonl \
    > out/qwen30b_hard.json

# Then Full
PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_full_labeled.json \
    --runner tracebench_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --checkpoint out/qwen30b_full.jsonl \
    > out/qwen30b_full.json

# Repeat for Qwen2.5-Coder-32B AWQ (swap --model in vLLM and TRACEBENCH_MODEL)
```

**Tip**: when you're done with one model, **don't** restart the whole evaluation — checkpoint files (`*.jsonl`) make it resumable. Just relaunch vLLM with the new model and rerun the same `evaluate.py` command (checkpoint will skip already-evaluated tasks).

### Phase 2 — API runs (~$260, can run in parallel with Phase 1 if H100 is free for API work too)

```bash
# GPT-4o on Hard (single seed)
export OPENAI_API_KEY=sk-...
PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_hard_labeled.json \
    --runner tracebench_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --model "gpt-4o-2024-11-20" \
    --checkpoint out/gpt4o_hard.jsonl \
    > out/gpt4o_hard.json

# GPT-4o on Full
PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_full_labeled.json \
    ... \
    --checkpoint out/gpt4o_full.jsonl

# Gemini-2.5-Pro (need a Gemini provider wrapper in multi_model_runner; see §7 below)
PROVIDER=google MODEL=gemini-2.5-pro \
    PYTHONPATH=code python3 code/evaluate.py \
    --tracebench data/tracebench_hard_labeled.json \
    --runner multi_model_runner:run_debug_session \
    --skip-raw --max-turns 5 \
    --checkpoint out/gemini_hard.jsonl \
    > out/gemini_hard.json
```

### Phase 3 — Bootstrap re-seeds (~$60, 1 h)

```bash
# Run 2 extra seeds on Hard for the 4 main models
for seed in 1 2; do
    for mname in gpt4o gemini_pro qwen30b qwen32b; do
        TRACEBENCH_SEED=$seed PYTHONPATH=code python3 code/evaluate.py \
            ... \
            --checkpoint out/${mname}_hard_seed${seed}.jsonl
    done
done
```

### Phase 4 — Analysis + figures (本地, ~30 min)

```bash
# Per-model per-problem records concat
cat out/*_records.jsonl > out/all_records.jsonl

# Figure 1 (real Outside-G vs RegressionRate scatter)
PYTHONPATH=code python3 code/scripts/make_figures.py \
    --records out/all_records.jsonl \
    --dataset data/tracebench_full_labeled.json \
    --output-dir paper/emnlp-tracebench/figures/

# Difficulty band table (Table 8)
PYTHONPATH=code python3 -c "
from src.evaluation.difficulty_slicer import slice_by_band, render_band_table
import json
recs = [json.loads(l) for l in open('out/all_records.jsonl')]
entries = {e['trace_id']: e for e in json.load(open('data/tracebench_full_labeled.json'))}
print(render_band_table(slice_by_band(recs, entries)))
" > out/table_difficulty_band.md

# Failure mode taxonomy (Table 12)
PYTHONPATH=code python3 -c "
from src.evaluation.failure_modes import classify_all, render_taxonomy_table
from src.core.metrics_v2 import active_spans_from_entry
... > out/table_taxonomy.md
"
```

---

## 6. 总账（推荐方案 B 下）

```
                                  Cost       Wall-clock
────────────────────────────────────────────────────────
Phase 0  data prep (active_fault) $0        45 min CPU
Phase 1  local (2 models × 2 splits) $0     3-4 h H100
Phase 2  API (4 cells: GPT-4o + Gemini-Pro × Full/Hard) $200   2-4 h API
Phase 3  bootstrap +12 cells       $60      30-60 min API
Phase 4  analysis + figures       $0        30 min CPU
────────────────────────────────────────────────────────
SUBTOTAL                          $260      ~7 h total
+ buffer (35%)                    +$90
────────────────────────────────────────────────────────
TOTAL                             ~$350     ~8 h
```

如果要做 appendix 的 GPT-4o-mini + DeepSeek-R1-Distill 那俩，**再加 $7 + 0.5 h**。可忽略。

---

## 7. 落到代码上的几个 TODO（不影响 critical path，但要 server 启动前补好）

### 7.1 Gemini provider wrapper

`multi_model_runner.py` 目前有 OpenAI / Anthropic / Together / Qwen 4 个 provider，但**没有 Google Gemini**。需要补:

```python
elif self.provider == "google":
    self.api_key = os.getenv("GOOGLE_API_KEY")
    # Use google-generativeai or REST API
    from google import genai
    self.client = genai.Client(api_key=self.api_key)
    self.model = model or "gemini-2.5-pro"
```

要 import: `pip install google-generativeai>=0.8`. **15 行代码**，server 启动前补。

### 7.2 Local-server 友好的 OpenAI-compatible adapter

vLLM serves OpenAI-compatible API on port 8000. `multi_model_runner.MultiModelGenerator` 的 `qwen` 分支（OpenAI-compatible via Together base URL）已经能用，**只需要设环境变量** `TOGETHER_API_BASE=http://localhost:8000/v1` 和 `TOGETHER_API_KEY=EMPTY`。无须改代码。

### 7.3 Seed 控制

`tracebench_runner.py` 当前用环境变量 `TRACEBENCH_TEMPERATURE` 控制温度，**没有 seed 参数**。Bootstrap 需要 seed 控制可重现。补一个 `TRACEBENCH_SEED` 环境变量传给 vLLM `seed` 参数；OpenAI/Google API 也支持 `seed` 参数。**10 行代码**。

### 7.4 sandbox subprocess pool

`harness.py` 当前每次 test 都新开 subprocess。对 818 problem × 平均 3 turn × 2 seed = 4900 sandbox 调用，单进程跑太慢。建议:
- 用 `concurrent.futures.ProcessPoolExecutor(max_workers=8)` 包一层
- 限制 `TRACEBENCH_TEST_TIMEOUT=60` 防止单个 task hang 整个 pool
- **20 行代码**

---

## 8. 风险点 + 应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| OpenAI/Google API rate-limit (TPM/RPM) | 高 | wall-clock × 2-3 | OpenAI: 用 tier-3+ 账号；Google: 默认 60 RPM 够用; 实现 exponential backoff |
| 32B 模型 OOM on H100 BF16 | 中 | 跑挂 | **用 AWQ-int4 量化** — 强烈推荐，速度 ×3 |
| vLLM blame_spans JSON parse 失败率高 (local model) | 中 | Blame@1 偏低 | 这是**有意 reported failure mode**, 不修；paper 加 footnote: "open models with low JSON adherence are penalized — this is part of the benchmark" |
| Gemini 2.5 Pro thinking tokens 偷偷涨 output | 中 | cost overshoot | 设 `thinking_config={"include_thoughts": false}` 或者改用 Flash 节省 |
| sandbox process pool 卡死 | 中 | wall-clock 多 1 h | 设 60s timeout + 8-way pool；超时直接计为 fail (paper 已说明此约定) |
| Active-fault labeling 在 Full 上跑太慢 | 低 | +30 min | 用 `--workers 8` 就行；single-thread ~40 min, 8-way ~5-6 min |

---

## 9. 一句话决策

✅ **走 Strategy B**：4 main rows (2 local + GPT-4o + Gemini-2.5-Pro), 3-seed bootstrap on Hard, optional 2 appendix rows. **$260-$350 + 7-8 h wall-clock**. 比之前估的 $597 + 2 day 省一半钱。

如果你想 push 一下卖点（appendix 加 reasoning row），加 **o4-mini single-seed**: +$50, +1h。Strategy D。

✅ **不要走 A**：API 模型用 nano 档基本看不出 Pass-Blame gap, 主表会显得没说服力。

✅ **不要走 E**：覆盖 6 个 closed model 性价比低；reviewer 不会因为多 2 个 row 就额外加分。

---

## 10. 一份现成的 punch-list (按顺序执行)

```
Day 0  (本地准备):
  [ ] cd ~/Desktop/tracebench
  [ ] pip install -r code/requirements-eval.txt
  [ ] (optional) pip install google-generativeai>=0.8  # for Gemini
  [ ] Run smoke: python code/scripts/smoke_pipeline.py --limit 5 → 验通过
  [ ] git init + first commit + tar.gz 备份

Day 0  (server 准备):
  [ ] scp tracebench/ to server:/data/
  [ ] vLLM 安装: pip install vllm>=0.6.2 (服务器侧)
  [ ] export OPENAI_API_KEY=...
  [ ] export GOOGLE_API_KEY=...
  [ ] huggingface-cli login (拉量化模型)

Day 1 (active fault + first run):
  [ ] active_fault_labeler --input tracebench_full.json  (~5 min @ 8 workers)
  [ ] active_fault_labeler --input tracebench_hard.json  (~1 min)
  [ ] Pull Qwen/Qwen3-Coder-30B-A3B-Instruct-AWQ (或自己 quantize 一次)
  [ ] vLLM serve + 跑 Hard (~30 min) + 跑 Full (~1 h)
  [ ] sanity check: out/qwen30b_hard.json 里 Blame@1, Outside-G, RegressionRate 都有非 None 值

Day 2 (剩下的 local + API):
  [ ] swap vLLM → Qwen/Qwen2.5-Coder-32B-Instruct AWQ
  [ ] 跑 Hard + Full (~2 h)
  [ ] OpenAI: GPT-4o on Hard + Full (~2 h, $113)
  [ ] Google: Gemini-2.5-Pro on Hard + Full (~2 h, $85)
  [ ] Run analysis: difficulty bands + bootstrap CI + figure
  [ ] 看初步数字, 决定是否需要 appendix rows

Day 3 (bootstrap + appendix):
  [ ] Bootstrap +2 seeds × 4 main models × Hard (~$60, 1 h)
  [ ] (optional) GPT-4o-mini full+hard ($7, 30 min)
  [ ] (optional) DeepSeek-R1-Distill on Hard ($0, 30 min)
  [ ] Figure 1 final + all tables → paper/

Day 4-5 (paper):
  [ ] 填 Table 5/8/9/10/11/12 + Figure 1 in main.tex
  [ ] Bibkey audit
  [ ] Limitations + appendix polish
  [ ] Anonymous repo upload
  [ ] 投稿
```

整个流程 **5 天 / $360 / 6-8 h server time** 可以走完。如果 Day 1 verify 通过, Day 2-5 基本可以无人值守跑。
