# Submission-Readiness Gap — 数据量 + 实验量 量化盘点

> Snapshot: 2026-05-15
> 目标: 把"距离能投 ACL 2026"具体落到**记录数 / API call 数 / token 数 / dollar / 小时**这四个量纲上。
> 上游文档: `CODE_GAPS.md`（代码侧）, `REVIEW_AND_ROADMAP.md`（review 侧）, `DATA_LOCATIONS.md`（data inventory）。

---

## TL;DR — 一张表说完

| 维度 | 当前 | 缺口 | 预计 |
|------|------|------|------|
| **Dataset** (paper Section 4 / Table 4) | 818 + 128 multi-turn ✓ | 0 | 已完成 |
| **Dataset 派生 label** (active fault per turn) | 0 / 1292 | **1292 sandbox replay** | ~3 hours wall-clock (4-way parallel) |
| **Trajectory matrix** (paper Table 5 主表) | 1 / 12 cells (Qwen3-32B × Hard, 格式不兼容) | **12 cells × 6 models × 2 splits, 16,890 turn-rounds, ~135M tokens** | ~$455 cost, ~2 days wall-clock (single pass) |
| **Bootstrap CI** (paper claims 95% CI on Hard) | 0 seeds | +2 seeds × Hard split × 6 models | +$142 → grand total $597 |
| **Outside-G + RegressionRate 实现** (paper Section 3 主指标) | 0 / 2 (code 没写) | 2 个新 metric + 1 修复 | 2.5 person-days |
| **派生表 (Table 8/9/11/12 + Figure 1)** | 0 / 5 ready | 全部要现场算 | 1 person-day 自动出 |
| **总计** | — | — | **3 周内可全部 close**（关键路径 1 人 80 小时 + $600） |

**底线**: 离投稿差 **1 个工程 sprint + ~$600 API 钱**。**比想象中近**。

---

## 1. 数据量缺口

### 1.1 已有（不缺）

```
data/tracebench_full.json         818 problems  2377 turns  7165 tests  1113 injections  ✓ paper-aligned
data/tracebench_hard.json         128 problems   438 turns  1511 tests   179 injections  ✓ paper-aligned
data/oracle_spans.json            128 oracle blame labels (Hard only)                    ✓ ready
data/splits/manifest_{full,hard}  lightweight metadata                                   ✓ ready
data/reference_trajectories/      128 Qwen3-32B trace (CLI 格式)                          △ 不可直接用
```

### 1.2 缺什么 — **3 类**

#### A. Per-entry 派生字段 (`active_faults_per_turn`)

| 项目 | 当前 | 需要 | 数据点数 |
|------|------|------|---------|
| Full split 的 `active_faults_per_turn` 字段 | 0/818 | 1/818 | 需对 **1113 个 injection × 1 turn 反事实回放** |
| Hard split 的 `active_faults_per_turn` 字段 | 0/128 | 1/128 | 需对 **179 个 injection × 1 turn 反事实回放** |
| Full split 的 oracle_spans (Hard 已有) | 0/818 | 1/818 | 可从 active_faults 派生 (0 额外 cost) |

**总数据生产**: 1113 + 179 = **1292 次 sandbox 反事实回放**。

每次回放 = `apply_counterfactual_patch → run_tests` ≈ 30 sec。

**Wall-clock**: 1292 × 30 sec ÷ 4-way parallel = **2.7 小时**。
**Cost**: $0（本地 CPU）。
**Code 前置依赖**: 实现 `_label_active_faults()` (CODE_GAPS.md §3)，~2 person-days。

#### B. Trajectory 矩阵 (paper Findings 主数据)

paper Table 5 要求 6 models × 2 splits。

**当前**:
- 有 1 个 cell (Qwen3-32B × Hard, 128 文件) — 但格式是 CLI/terminal 式，**不含 paper-required 字段**（无 `code` per attempt, 无 `blame_spans`, 无 `edited_lines`, 无 `test_results_per_test`, 无 `failure_traceback`）。
- 12 个 cell 中 **0 个可用**。

**目标**: 12 cells. Model 候选 = {Qwen3-Coder-480B, Claude-4.5 Sonnet, GPT-4o, GPT-4.1, DeepSeek-Coder-V3, Gemini-2.5-Pro} × {Full, Hard}.

**数据点数**:

| split | problem 数 | turn-rounds (= sum of num_turns) | per-model 数据点 | 6-model 数据点 |
|-------|-----------|--------------------------------|------------------|---------------|
| Full | 818 | 2377 | 2377 LLM calls + 2377 sandbox runs | 14,262 LLM + 14,262 sandbox |
| Hard | 128 | 438 | 438 + 438 | 2,628 + 2,628 |
| **合计** | 946 | 2,815 | 2,815 + 2,815 | **16,890 LLM + 16,890 sandbox** |

**Token 量** (multi-turn 含累积 context，单 call 均值: input 8K, output 2K):

| | Full per-model | Hard per-model | 6-model total |
|---|---|---|---|
| 输入 token | 19.0 M | 3.5 M | **135.0 M** |
| 输出 token | 4.8 M | 0.9 M | **34.2 M** |

#### C. Per-test pass/fail（用于 RegressionRate）

**当前**: `harness.py` 的 `_run_test_bundle` 是 all-or-nothing。
**需要**: 改成 per-test 返回 `Dict[test_id, bool]`。
**数据生产**: 0（运行时自动产生，不需要预存）。
**Code 前置**: ~0.5 person-day（CODE_GAPS.md §2）。

### 1.3 数据量小计

| 类型 | 数据点数 | 完成度 |
|------|---------|--------|
| Dataset 主体 | 818 problems / 7165 tests / 1113 injections | **100%** |
| Active-fault label (跨 split) | 1292 个 (待 generate) | **0%** |
| Trajectory matrix | 16,890 LLM calls + 16,890 sandbox runs | **0%** (现有 trace 格式不兼容) |
| Per-test pass/fail records | runtime artifact, 不存 | n/a |

**整体数据量缺口** ≈ 1292 sandbox 回放 + 16,890 LLM call + 16,890 sandbox 测试运行。

---

## 2. 实验量缺口

按 paper Table/Figure 倒推：

| Paper artifact | 状态 | 实验 run 数 | 依赖 |
|----------------|------|-------------|------|
| Table 1 (设计原则) | ready | 0 | — |
| Table 2 (benchmark matrix) | ready | 0 (定性) | — |
| Table 3 (主指标定义) | ready | 0 | — |
| Table 4 (splits stats: 818/128/...) | ready | 0 | 从现有 data 直接派生 |
| **Table 5 (主表: Pass@1, Blame@1, Outside-G, Gap)** | placeholder (4 行) | **12 main runs** | (B) 矩阵 + Outside-G impl |
| Table 6 (split-roles 解释) | ready | 0 | — |
| Table 7 (use-recommendation) | ready | 0 | — |
| **Table 8 (difficulty-band 表，全是 `\todo{fill}`)** | blocked | 0 额外（从 Table 5 切片） | (B) 矩阵 + difficulty_slicer impl |
| **Table 9 (fault-family，paper 数字 stale)** | blocked | 0 额外（脚本重算） | fault_families.py impl |
| **Table 10 (Outside-G vs RegressionRate, r=0.61, n=896)** | blocked | 0 额外（从 Table 5 派生） | Outside-G + RegressionRate impl |
| **Table 11 (early-drift, +12.4 / +21.3 / −36.0)** | blocked | 0 额外（从 Table 5 stratify） | drift_stratifier impl + active_fault label |
| **Table 12 (failure-mode taxonomy + frequency)** | descriptive | 0 额外（rule-based classifier） | classifier impl |
| Table 13 (release artifacts) | ready | 0 | — |
| **Figure 1 (Outside-G vs RegressionRate scatter)** | placeholder | 0 额外（从 Table 5 派生） | matplotlib script |

**Bootstrap CI**: paper Table 5 写 "Hard-split gaps include paired bootstrap 95% CIs"，对应：
- 单 seed run 可以做 bootstrap-of-problems（resample 128 个 task）→ 0 额外 run
- 多 seed run 可以做 paired bootstrap（resample seeds）→ 需要 **+2 seeds × Hard × 6 models = 12 extra runs**

### 2.1 实验 run 总数

| 类别 | run 数 | 包含 |
|------|--------|------|
| Active-fault label 跑 | 1 (本地) | 1292 sandbox replay |
| 主表 trajectory matrix (single-seed) | **12** | 6 model × 2 split |
| Bootstrap CI (paired, 3-seed Hard) | **+12** | 6 model × Hard × 2 extra seeds |
| Difficulty-band 切片 | 0 (从主表派生) | — |
| Fault-family 重算 | 0 (从 data 派生) | — |
| Outside-G vs RegressionRate scatter | 0 (从主表派生) | — |
| Early-drift stratification | 0 (从主表派生) | — |
| Failure-mode taxonomy | 0 (从主表派生) | — |
| **合计**: | **24 LLM-driven runs** + 1 本地 prep run | |

### 2.2 选填 (P2)

| 类别 | run 数 | 价值 |
|------|--------|------|
| Turn-budget sensitivity (3/5/8 turn) | +6 (3 budget × 2 split × 1 model) | appendix，证明 budget 不是 confound |
| SWE-bench Verified 对照 (3 model) | +3 | 显示与 outcome benchmark 的差异性 |
| Human study on failure mode (50 task × 5 SE PhD) | 人工 | 涨分，appendix |

---

## 3. 钱 + 时间预算

### 3.1 Cost（按当前 listing 价 2026-05）

```
TraceBench-Full (per-model, 2377 turn-rounds × 8K input + 2K output):
  GPT-4o      ($2.50 / $10.00 per MT)     $  95
  Claude-4.5  ($3.00 / $15.00)            $ 128
  Qwen3-480B  ($0.30 / $0.30 via Together)$   7
  Gemini-2.5  ($1.25 / $10.00)            $  71
  GPT-4.1     ($2.00 / $8.00)             $  76
  DeepSeek-V3 ($0.28 / $0.28)             $   7
  ── Full 6-model total                   $ 385

TraceBench-Hard (per-model, 438 turn-rounds):
  ── Hard 6-model total                   $  71

Single-pass (6 × 2)                       $ 455
+ 2 extra Hard seeds for bootstrap        $ 142
GRAND TOTAL (paper-ready)                 $ 597
```

**注释**:
- 80% 的钱花在 Claude + GPT-4o。如果 budget 紧，先做 4 个 open-weight + 2 个 frontier 也能成立。
- $597 包含 Hard 上的 bootstrap CI（3 seed），但 Full 只有 single-seed（paper 实际只 claim Hard 的 CI，所以 OK）。
- 加 Full 也跑 3 seed → 总 $1,030。**强烈不建议**（边际效益低）。

**Buffer 建议**: $800 (35% margin for retries / rate-limit re-runs / bad calls)。

### 3.2 Wall-clock

```
Single model × Full @ 8-concurrent API : 2.1 h
Single model × Hard @ 8-concurrent API : 0.4 h
6 models in parallel (separate providers): ~3 h theoretical
Realistic with retry/rate-limit overhead: 12-36 h (1-2 days)
Bootstrap (2 extra Hard seeds × 6 models, parallelizable): +1 h
```

**总 wall-clock**: **1.5 – 2.5 天** for the full 12+12 = 24 run matrix。

### 3.3 Person-day

```
Code 实现 (CODE_GAPS.md 列的 12 项):
  §3 active fault selection                       2.0 d
  §2 RegressionRate (incl. per-test exec)        1.5 d
  §1 Outside-G                                    1.0 d
  §4 per-trajectory slope                         0.5 d
  §5 repeats / test-without-edit                  0.5 d
  §6 bootstrap CI                                 0.5 d
  §7 fault-family rollup + Table 9 fix            1.0 d
  §8 difficulty slicer                            0.5 d
  §9 drift stratifier                             0.5 d
  §10 failure-mode classifier                     1.0 d
  §11 figure generation                           1.0 d
  unit tests + ergonomics                         1.0 d
  ── code subtotal                              11.0 d

Active-fault label generation (run)              0.5 d  (含 sandbox time)
Trajectory matrix run (start + babysit)          1.5 d  (wall-clock 1-2 day, 但需有人盯)
Paper updates (回填 Tables 5/8/9/10/11/12 + Fig 1) 1.5 d
End-to-end smoke + writing polish                1.0 d
                                                ─────
                                                15.5 person-days
```

**保底 1 人专职 3 周**，含周末缓冲 + unforeseen blocker。

---

## 4. 关键路径（含可并行机会）

```
┌─────────────────────────────────────────────────────────────────┐
│ Week 1                                                          │
│   Mon-Tue: §3 active fault impl + §2 RegressionRate impl       │
│            (gates everything else)                              │
│   Wed:    §1 Outside-G impl                                    │
│   Thu:    Run active-fault label on 1292 inj (3h wall-clock)   │
│           ─ data side ready for evaluation                      │
│   Fri:    Kick off 12 main runs (parallel across providers)    │
│           Start §4/§5/§6/§7 in parallel                        │
├─────────────────────────────────────────────────────────────────┤
│ Week 2                                                          │
│   Mon:    Main 12 runs finish (1-2 day wall-clock)             │
│           Kick off +12 bootstrap re-seeds                       │
│   Tue:    §8 difficulty slicer + §9 drift stratifier impl      │
│   Wed:    §10 failure-mode classifier + §11 figure gen         │
│   Thu:    Bootstrap re-seeds finish, compute CIs                │
│   Fri:    Smoke test end-to-end on 30 problems × all metrics   │
├─────────────────────────────────────────────────────────────────┤
│ Week 3                                                          │
│   Mon-Tue: Fill all Tables 5/8/9/10/11/12 + Fig 1 in main.tex  │
│   Wed:    Bibkey audit (cleanpr/davincidev/...)                │
│   Thu:    Limitations 扩写 + appendix close                     │
│   Fri:    Final polish + anonymous repo upload                 │
└─────────────────────────────────────────────────────────────────┘
```

### 可并行的 4 条线

| 线 | 内容 | 何时启动 |
|----|------|---------|
| A | active-fault label run | Day 4 (依赖 §3 impl) |
| B | trajectory matrix run | Day 5 (依赖 A 完成 + §1+§2 impl) |
| C | §4–§7 metric impl | Day 1 (无依赖) |
| D | §8–§10 派生 impl | Day 8 (依赖 B 数据) |

C 全程跟主线并行；A → B → D 是 critical path。

---

## 5. 风险点 + 应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| LLM API rate-limit during multi-model run | 高 | wall-clock × 2-3 | 早 1 天启动，retry with exponential backoff |
| Claude/GPT 的某个 model 经常给 malformed blame_spans | 中 | parser 失败，metric 偏 | 写 robust parser + fallback；做 sanity diagnostic（取 30 trace 看 raw output） |
| Active-fault label 时间超预期 | 中 | +1 day | sandbox subprocess 调到 8-way parallel；timeout 调严（25s） |
| Outside-G 的"neighborhood radius"超参 cherry-pick 怀疑 | 中 | reviewer 砸 | 报告 radius=3/5/10 三档 sensitivity，主表用 3 |
| Bibkey 假货 | 中 | reject | 投稿前一次性核查 8 个 2025-2026 引用 |
| Server 挂 / Together 端 unstable | 中 | rerun 一次 | checkpoint 已有，资料不丢 |

---

## 6. 三句话最后总结

1. **数据 95% 已就绪**：818/128 split + 128 oracle spans + manifests 都在 `data/`，paper Table 4 直接重算可对得上。
2. **实验 0% 就绪**：paper Table 5/8/10/11/12 + Figure 1 全部依赖一个 12-cell trajectory matrix（6 model × 2 split），目前 0/12 完成，需要 **~$600 + 1-2 天 wall-clock + 11 人-day code 工作**。
3. **离投稿差 1 个工程 sprint（3 周专职）**：critical path = 3 个 metric impl (3 day) → active-fault label (0.5 day) → trajectory matrix run (1-2 day wall-clock) → 派生表 + figure (2 day) → paper polish (3 day)。预算 $800 (+35% margin)。
