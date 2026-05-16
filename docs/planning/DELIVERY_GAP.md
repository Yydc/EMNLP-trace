# 离交付还差多少实验 — 精确盘点

> 2026-05-15 — Discussion frame for "what's between us and submission"
> Reference: EXPERIMENT_PLAN.md, SERVER_RUN_PLAN.md, CODE_GAPS.md

---

## TL;DR 一张表

| 维度 | 状态 | 还差 |
|------|------|------|
| Dataset (818+128+oracle+manifest) | ✅ 100% | 0 |
| Code (8 metric + 4 analysis + figure + 50 tests) | ✅ 100% | 0 |
| Paper structure (AlphaDiana 6-section) | ✅ 100% | 0 (TBD 占位都标好) |
| **Active-fault labels** | 🟡 0/2 splits | **1 CPU 任务**, ~7 min |
| **Main eval matrix** | 🟡 0/16 cells | **16 trajectory 跑** (Full × 8 model 单 seed + Hard × 8 model 单 seed) |
| **Bootstrap Hard re-seeds** | 🟡 0/16 cells | **16 额外 trajectory 跑** (Hard × 8 model × 2 extra seeds) |
| **Analysis pass** | ✅ code 100% | **1 脚本 run** after eval matrix done |
| Paper number fill | 🟡 ~72 TBD placeholders | **1 day** after analysis (mostly sed-like substitution) |
| Bibkey audit + Limitations + Anon repo | 🟡 | **2 days** paper polish |

**总缺口**: **32 个 trajectory 跑 + 1 个 CPU prep + 1 个 analysis script run + 1 day paper fill + 2 days polish**.

**钱**: **$517 API + $181 buffer = $698**. 局部 GPU $0.

**时间**: **2-3 天 server** (主表 + bootstrap) **+ 3 天 paper** = **5-6 天到交付**.

---

## 1. 必须做的 (P0) — 不做交付不了

### 1.1 一次性 prep job (本地 CPU)

```
[1 task] active_fault_labeler on Full + Hard
   1292 sandbox counterfactual replays (1113 Full + 179 Hard)
   8-way parallel CPU
   Output: data/tracebench_{full,hard}_labeled.json
   Time: ~7 min total
   Cost: $0
```

**为什么 required**: Outside-G 的 active fault span 必须从这里来。否则 Outside-G 退化成 patch_locality proxy，paper Section 3 主指标失去 grounding。

### 1.2 主矩阵 — 16 个 trajectory cells

8 models × 2 splits (Full + Hard, single-seed)

```
LOCAL (H100, $0):
  Qwen3.6-27B                  × Full + Hard    [2 cells]
  Qwen3-Coder-30B-A3B          × Full + Hard    [2 cells]
  Qwen2.5-Coder-32B (AWQ-int4) × Full + Hard    [2 cells]
  GLM-4.7-Flash (AWQ-int4)     × Full + Hard    [2 cells]
  DeepSeek-R1-Distill-Qwen-32B × Full + Hard    [2 cells]
  Qwen2.5-Coder-14B            × Full + Hard    [2 cells]
                                                 ───────
                                                 12 local cells (8-12 h H100)

API:
  GPT-5.5         × Full + Hard                 [2 cells, $281]
  Gemini-3.1-Pro  × Full + Hard                 [2 cells, $113]
                                                 ───────
                                                 4 API cells ($394)
```

**为什么 required**: paper Table 5 (`tab:gap`) 16-row 主表的所有 cell。SC1+SC2 (Pass-Blame gap + Hard 是 diagnostic) 全靠这个。

### 1.3 Bootstrap re-seeds — 16 个 extra cells

8 models × Hard × 2 extra seeds (paper claim "Hard-split gaps include paired bootstrap 95% CIs")

```
LOCAL (H100, $0):
  6 model × Hard × 2 extra seed = 12 cells (~2-3 h H100)

API:
  2 model × Hard × 2 extra seed = 4 cells
    GPT-5.5 Hard × 2 extra seed = $88
    Gemini-3.1-Pro Hard × 2 extra seed = $35
                                       ───────
                                       $123
```

**为什么 required**: paper Table 5 caption 已经 commit 到 "with paired bootstrap 95% CIs"，不交 reviewer 立马挑。

### 1.4 Analysis pass — 1 个 script run

```
[1 task] cat out/*_records.jsonl | analysis_script
  Outputs all derived tables/figures from the 32 trajectory cells:
  - Figure 1 (Outside-G vs RegressionRate scatter)
  - Table 8 (difficulty band slicing)
  - Table 10 (diffusion validation r + bootstrap CI)
  - Table 11 (drift Hit/Miss stratification)
  - Table 12 (failure mode taxonomy frequency)
  Time: ~30 min CPU
  Cost: $0
```

**Code 都已经 ready**, 只需要执行。所有分析模块 (`src/evaluation/{bootstrap,difficulty_slicer,drift_stratifier,failure_modes}` + `scripts/make_figures.py`) 已经 unit-tested。

---

## 2. P0 总账

| 类别 | Count | Cost | Time |
|------|------:|-----:|-----:|
| CPU prep | 1 task | $0 | 7 min |
| Local trajectory cells (Full + Hard × 6 models, 1 seed) | 12 | $0 | 8-12 h H100 |
| Local bootstrap Hard re-seeds (6 model × 2 extra seed) | 12 | $0 | 2-3 h H100 |
| API trajectory cells (Full + Hard × 2 SOTA, 1 seed) | 4 | $394 | 2-4 h API (parallel) |
| API bootstrap Hard re-seeds (2 model × 2 extra seed) | 4 | $123 | ~1 h API |
| Analysis pass (figure + 5 tables) | 1 script | $0 | 30 min CPU |
| **Total** | **32 trajectory + 2 script** | **$517** + 35% buffer = **$698** | **~2 days** wall-clock |

---

## 3. P1 强烈建议 (不做审稿人会反复要)

### 3.1 Local model JSON-parse sanity diagnostic (~2 hours, $0)

跑完第 1 个 local model (~推荐 Qwen3.6-27B Hard) 之后立刻做的事:

```
[1 manual inspection]
取 30 个 trace 看 raw blame_spans 输出:
  - JSON 格式合法率
  - 解析失败时的 typical 错误
  - 是否需要给 paper appendix 加一段 "we treat unparseable blame as empty (counted against Blame@1)"
```

**为什么有用**: paper Section 5.1 Finding 1 prose 已经隐含 "the protocol is identical across rows"。如果 local models JSON 解析失败率 >30%，要么我们 paper 里直接 acknowledge，要么补一个 prompt-engineering pass。**0 extra cost**, 但是 reject-prevention。

### 3.2 Turn-budget sensitivity (~$26, 0.5 day)

```
GPT-5.5 × Hard × {3, 5, 8} max turns = 3 runs
  Each at $43.80 (single-seed Hard)
  → $131 total
  Or use a cheaper model (Qwen3.6-27B local, $0) → recommended
```

**为什么 reviewer 会要**: 自然问题"如果给模型更多 turn，gap 还存在吗？" — 我们的 default 是 5 turn。如果 8 turn 后 gap 还是大的, 说明 gap 不是 budget 不够导致的。**Appendix only, 不入主表**。

### 3.3 Sanity baseline: Qwen3-32B (CLI-format, 128 trace) 重利用

我们已经有 NeurIPS sibling 的 128 trajectories on Qwen3-32B × Hard. 虽然 schema 不兼容主表，但可以**只用其中的 aggregate** (solve_rate=31.25%, mean_test_without_edit_rate=0.62, ...) 作为 paper §5 一句话引用:

> "An older Qwen3-32B run reported in concurrent work {citation} on the same Hard split achieves 31.3% solve rate with 62% test-without-edit rate; we confirm the gap persists when the protocol is unified across models."

**Cost: $0, 时间: 0**. 纯 reference text in paper.

---

## 4. P2 选填 (appendix only, 时间紧可全砍)

| 实验 | Cost | Time | 价值 |
|------|-----:|-----:|------|
| Local size curve (Qwen2.5-Coder-7B/14B + StarCoder2-15B × Hard) | $0 | +1.5 h H100 | 弱模型对照，"size 不能拯救 traceability" |
| SWE-bench Verified cross-eval (3 model × 500 issues, Pass@1 only) | ~$84 | +1 day | 显示 TraceBench vs outcome benchmark 不相关 |
| Human study (2 PhD × 50 trajectory × 5 mode) | $0 | +2 person-day | inter-rater agreement vs metric, 强 paper |
| RAD/ARC controller (Appendix G, "trace signals can support controllers") | ~$30 | +1 day | 答辩 "the dataset is actionable" |
| External transfer to CodeFlowBench (1 model) | ~$20 | +0.5 day | 显示 protocol generalizes |

**全砍的话, 不影响主线 4 个 finding 成立**. 但每个都能让 paper 强一档.

---

## 5. 风险点 + 缓冲

| 风险 | 概率 | 影响 | 缓冲已计入？ |
|------|------|------|--------------|
| OpenAI/Google API rate-limit (TPM/RPM) | 高 | wall-clock × 2-3 | ✅ 35% cost buffer + 2-3 天 wall-clock 已留 |
| vLLM AWQ-int4 量化精度 vs BF16 差距 >5 pts | 中 | reviewer 抓 | 应对: 取 1 model BF16 同模型 BF16 vs AWQ 在 Hard 上跑 sanity (extra $0, 2 h H100) |
| 32B BF16 H100 OOM | 高 | 跑不动 | ✅ 已 plan AWQ-int4 |
| Active fault label 大量 trusted-fallback (>50%) | 中 | reviewer 问 "你 active_fault 选择不准" | 提前写 appendix: stratified labeling 6 档输出, trusted-fallback 不是 fail-mode |
| GPT-5.5 thinking tokens 偷偷涨 cost | 中 | 超 $700 | buffer 内 |
| Local model JSON blame parse 失败率高 | 中 | local rows 整列 Blame@1 偏低 | sanity 后决定: 加 prompt repair retry, 或 paper acknowledge |
| Server 中途挂 | 低 | 重跑 | 全部 cells 都用 checkpoint=*.jsonl, 可 resume |

---

## 6. Minimal viable submission vs. Nice-to-have 对比

| 路线 | 实验数 | Cost | Wall-clock | 主表 row | Findings 覆盖 |
|------|-------:|-----:|-----------:|---------:|---------------|
| **Minimal** (P0 only) | 32 + 1 prep + 1 analysis | $698 | 2 天 server + 3 天 paper = **5 天** | 8 model × 2 split | F1+F2+F3+F4 全覆盖 |
| **Recommended** (P0 + sanity + turn-budget) | +3 cells | +$26 | +0.5 天 | + Appendix turn-budget | + 防御 budget concern |
| **Strong** (P0 + P1 全部) | +5 cells | +$110 | +1 天 | + 3 appendix tables | + 防御 budget + reproducibility |
| **Top-tier** (Recommended + human study) | +5 cells + 50 manual labels | +$0 (manual) | +2 person-day | + Appendix human-study | 学术加分项 |

---

## 7. 我推荐的分发 (按 时间 / cost / 信号 三轴 trade-off)

✅ **走 Recommended**：P0 全跑 + Sanity diagnostic + Turn-budget sensitivity (用 Qwen3.6-27B local 跑 budget=3/5/8, $0 cost)

**总账**:
- 实验数: **32 main + 3 sensitivity + 1 sanity + 1 analysis = 37 个 invocation**
- Cost: **$698 + $0 sensitivity = $698**
- Time: **2-3 天 server + 3 天 paper = ~5-6 天**

**理由**:
- P0 是 reject-prevention。
- Sanity diagnostic 是免费保险 (不做 reviewer 问 "为什么 local 模型 Blame@1 全是 0" 就完了)。
- Turn-budget 用 free local model 跑, 防御反向 attack "5 turn 不够"。
- Human study + SWE-bench cross-eval 可以放到 rebuttal 阶段补 (那时候 1 周时间还来得及)。

---

## 8. 关键 checkpoint (server-side 监控点)

实验过程中 5 个 sanity-check 点:

| Checkpoint | 时机 | 看什么 | Threshold |
|-----------|------|--------|-----------|
| C1: active fault labeling 结束 | ~7 min after start | strict-active vs trusted-fallback 比例 | strict-active >20% on Hard (we saw 23% 早期) |
| C2: 第 1 个 model × 30 problems | 跑完前 30 题 | Outside-G / RegressionRate 不是 None | 都有非空值 |
| C3: 第 1 个 model × Hard 跑完 | ~30 min in | Solve rate plausible | Qwen3.6-27B 在 50-70% 之间 |
| C4: 第 1 个 model 完整 (Full+Hard) | ~2 h in | Pass@1 - Blame@1 gap 存在 | gap > 20 pts on Hard |
| C5: 全 8 model 主矩阵跑完 | day 2 EOD | bootstrap CI 收敛 | Hard 95% CI 宽度 < 15 pts (8 个 model 各自) |

**如果 C2-C5 任何一个出问题**, 优先 debug 不是继续跑 — 否则白烧钱。

---

## 9. 一句话决策

**离交付的 minimum 实验量是 32 trajectory cells + 1 CPU prep + 1 analysis script run**.

✅ 推荐**走 P0 + 3 sensitivity + sanity = 37 invocation**, **$698 + 5-6 天**.

接下来要决定:
1. 是 Day 0 (今天/明天) 就 push 到 server, 还是先 dry-run 1 个 model on 30 题确认 wiring 全部 OK?
2. P2 里哪一项最值得加 (human study? RAD-as-appendix? SWE-bench cross-eval?)
3. 主表里要不要补一个 "Qwen3-32B from concurrent work" reference row (利用 NeurIPS sibling 的 aggregate 数字, $0)
