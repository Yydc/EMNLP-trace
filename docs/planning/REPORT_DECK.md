# 汇报材料：TraceBench EMNLP — Claim/Experiment/Data 对应表

> 编写: 2026-05-15
> 用途: 今日汇报。已综合 GPT 的 framing 建议 + 我们手上的真实 data/code 状态。
> 决定: 论文锁成 **dataset/evaluation paper**，**不** 卖 RAD/ARC 作为主方法。
> 一句话定位: "TraceBench-Full + validated traceability evaluation"，**不是** "TraceBench + RAD"。

---

## 1. Main Claim (1) + Sub-Claims (4)

### Main Claim — 一句话能讲完

**多轮代码修复 (multi-turn code debugging) 的 outcome success 与 process traceability 是两件事；我们用一个 causally-grounded 数据集 + 三类过程指标把这种分离首次系统化、可审计化，并证明这种分离不是小样本伪影。**

正式表述（给 abstract / intro 用）:

> Final test success in multi-turn code debugging does not reveal whether an agent localized the fault, preserved already-correct code, or accumulated unstable edits before converging. We introduce **TraceBench-Full**, a causally grounded dataset (818 problems / 2402 traces / 7165 tests) with a 128-instance high-signal diagnostic subset **TraceBench-Hard**, and three behaviorally validated process metrics (attribution / propagation / accumulation). Across representative LLMs the traceability gap is large, persists at scale, and is amplified on Hard. This enables a missing class of community-scale, process-level evaluation.

### Sub-Claim 表

| ID | Sub-Claim | 一句话定位 |
|----|-----------|----------|
| **SC1** | **Pass-Blame gap is large and persists at scale.** | 不是 small-sample artifact: 在 818 problem 的 Full 上 gap 仍 30-65 pts，覆盖广不解决问题。 |
| **SC2** | **TraceBench-Hard is a diagnostic split, not cherry-picking.** | 128 是 strict subset (rating ≥ very_hard / depth mean 3.75)，专门暴露 strong-model 上的 process failure。Easy/Med 上 1-2 turn 就 solved，drift signal 被 ceiling 掩盖。 |
| **SC3** | **Fault coverage is transparent + Outside-G is behaviorally validated.** | 1113 injections × 5 typed families 全部 distribution 公开；Outside-G 不是 line-count proxy，而是与 RegressionRate (r=0.61, p<0.001) 行为相关。 |
| **SC4** | **Trace logs reveal a measurable failure pattern: mis-localization → diffusion → regression.** | 第一回合的 blame miss 预测后续 +12.4 patch / +21.3 Outside-G / −36.0 final Blame@1；不是定性故事，是可定量。 |

### 为什么是这 4 个 sub-claim

- 每个对应 paper 一个 finding section (3.5 页主文证据全部按这 4 个分);
- 每个对应一类 reviewer concern:
  - SC1 → AC 的 "outcome ≠ process";
  - SC2 → AC 的 "128 太小";
  - SC3 → reviewer Th34 的 "synthetic faults 代表性 / Outside-G 是不是 line count";
  - SC4 → reviewer 的 "更多 qualitative evidence";
- 每个都可以 **现有数据 + 必跑实验** 闭合 (见 §3).

---

## 2. 完整实验表 (8 个 experiment, 5 P0 + 3 P1)

### 体例
- **Status** = 现状: ✅ 已有 / 🟡 部分有 / 🔴 没跑 / 🛠 需要 code 先实现
- **Owner** = 谁负责 (single-person assumption: 我; 多人时可改)
- **Cost / Days** = 估算 (基于 §3 的 turn 数 + token 单价)

### P0 — 必须做（不做则 reject）

| ID | Experiment | Paper artifact | Method | Status | Cost | Days |
|----|-----------|---------------|--------|--------|------|------|
| **E1** | **Main model × split × Pass/Blame matrix** | Table 3 ("Finding 1" 主表) | 6 model × 2 split, full-transcript $H_t$, $T_{\max}=5$, temp=0.2, JSON blame_spans output. 报告: Pass@1, Blame@1, Gap, Outside-G, EditSize, AvgTurns. Hard 加 3-seed paired bootstrap CI. | 🔴 0/12 cells, 现有 Qwen3-32B trace 格式不兼容 | $597 | 2 (wall-clock 1-2 day) |
| **E2** | **Difficulty / depth stratification** | Figure 1 ("Finding 2") | 把 E1 结果按 Easy-Med / Hard / VeryHard+ 三 band 切, 或按 depth ≤2/=3/≥4. 报告: Pass/Blame/Gap/Outside-G/RegRate/AvgTurns × 6 model × 3 band. | 🟡 dataset 有 difficulty 字段 (extreme 67 / very_hard 123 / hard 210 / med 207 / easy 204 / unrated 7), 但 slicer 没实现 | $0 (从 E1 派生) | 0.5 |
| **E3** | **Fault-family performance breakdown** | Table 4 ("Finding 3" 主表) | 把 E1 结果按 5 个 fault family (Boundary/Off-by-one, Wrong-Op, Omission, Dep-Misuse, Corner-case) 切. 报告每 family: count, Pass@1, Blame@1, Gap, Outside-G, RegRate. **NOTE**: paper 现有的 334/278/201/167/133 与 live data **对不上** (实测 boundary 类 765)，必须重算。 | 🟡 10→5 family mapping 没固化; live count 不匹配 paper | $0 (从 dataset + E1 派生) | 1 (含 paper Table 修订) |
| **E4** | **Outside-G vs RegressionRate behavioral validation** | Figure 2 ("Finding 3" 副表) | Per-edit scatter: x=Outside-G, y=RegressionRate. Pearson r + p value + n. 补 partial regression: `RegRate ~ Outside-G + EditSize + Model + Difficulty`, 看 Outside-G 系数在控制 EditSize 后是否仍显著. | 🛠 RegressionRate code 未实现; per-test pass/fail 需要 harness 改造 | $0 (从 E1 派生, run-time exec) | 2 (含 metric impl) |
| **E5** | **Cost accounting table** | Table 5 (主文 compact + appendix 完整) | Per-model 报告: avg turns, avg tests run, total LLM calls, total prompt/output tokens, wall-clock, GPU hours (本地), API $ (远程). | 🟡 runner 已 log token; 需聚合 | $0 (附产) | 0.3 |

### P1 — 强烈建议做（不做的话审稿人会反复要）

| ID | Experiment | Paper artifact | Method | Status | Cost | Days |
|----|-----------|---------------|--------|--------|------|------|
| **E6** | **Local-model reproducibility** | Table 3 主表加 2-3 个 local rows + appendix 全表 | Run `Qwen3-Coder-30B-A3B-Instruct` 和 `Qwen2.5-Coder-32B-Instruct` 在 Full+Hard. Optional: `DeepSeek-R1-Distill-Qwen-32B` 在 Hard. 目的: 证明 gap 不是 closed-source artifact. | 🔴 0/3 local cells | $0 (本地 GPU) | 2 (wall-clock; 8×H100 估 8-12h per model) |
| **E7** | **Full-transcript sanity check** | Appendix table (3 protocol × metric) | 3 protocol on Hard: (a) snapshot-only $\{P_t, O_t\}$, (b) full $H_t$, (c) full $H_t$ + Reflexion-style summary. 报告 Pass/Blame/Outside-G/RegRate. **目的**: 堵 z9T7 reviewer "missing history artifact" 担心. | 🔴 0/3 protocols | $35 (Hard only, 1 model × 3 protocol) | 1 |
| **E8** | **Early-misloc → drift stratification** | Table 6 ("Finding 4" 主表) | 按 first-blame hit/miss 把 trajectory 分两组, 报告下游 cumulative patch / Outside-G / final Blame@1 的差值. | 🛠 stratifier 没实现 + 依赖 E1 + active-fault label | $0 (从 E1 派生) | 0.5 |

### P2 — 可放 appendix（不上不影响主线）

| ID | Experiment | Cost | Days |
|----|-----------|------|------|
| P2-1 | Turn-budget sensitivity (3/5/8 turn, Hard, 1 model) | $20 | 0.5 |
| P2-2 | Human sanity check on 50 trajectories (2 author annotators × failure-mode labels) | 人工 | 1 |
| P2-3 | SWE-bench Verified 对照 (3 model, Pass@1 + patch-size) | $50 | 1 |
| P2-4 | RAD/ARC trace-signal-aware steering as appendix use case | $30 | 1 |
| P2-5 | External transfer to CodeFlowBench (1 model) | $20 | 0.5 |

### 实验总计

| 类别 | Run 数 | $ Cost | Days |
|------|-------|--------|------|
| P0 (必须) | 5 experiments (但 E2-E5 都是从 E1 派生, 实际 1 big run + 4 派生) | $597 | 5.8 |
| P1 (强烈建议) | 3 experiments (E6 本地, E7 多 protocol, E8 派生) | $35 (P1 主要是本地 GPU + 已有 API) | 3.5 |
| **P0 + P1 合计** | **8 experiments → 1 main API matrix run + 1 local matrix + 1 protocol study + 5 派生分析** | **~$632** | **~9.3 person-days** |
| P2 (可选) | 5 experiments | $120 | 4 |

预算 buffer: $800 (含 retry / rate-limit / bad call).

---

## 3. Claim ↔ Data ↔ Experiment ↔ Paper-Artifact 对应表

每行的逻辑链: **Sub-Claim → 需要什么实验 → 实验跑在什么数据上 → 输出到 paper 的哪个 Table/Figure**.

| Sub-Claim | 实验 | 输入数据 | 派生指标 | Paper artifact | 现在差什么 |
|-----------|------|---------|---------|---------------|-----------|
| **SC1 Pass-Blame gap large + persists** | **E1** (main matrix) + **E5** (cost) | `tracebench_full.json` (818) + `tracebench_hard.json` (128) + `oracle_spans.json` (Hard, 128) | Pass@1, Blame@1, Gap = Pass-Blame, AvgTurns | Table 3 (Finding 1 主表), Table 5 (cost) | E1 全部 12 cell 没跑; Blame@1 code ✓, 但 active_fault label 缺 (1292 sandbox replay) |
| **SC2 Hard is diagnostic** | **E2** (difficulty/depth stratification) | E1 trajectory 输出 + `manifest_full.json` (有 difficulty/depth/rating) + `manifest_hard.json` | Pass/Blame/Gap/Outside-G/RegRate × {Easy-Med, Hard, VeryHard+} | Figure 1 (Finding 2) + Table 6 (split-role 对比) | difficulty slicer 没实现; 依赖 E1 |
| **SC3a Fault coverage transparent** | **E3** (family breakdown) | `tracebench_full.json` 的 injection metadata + E1 trajectory | Count × Pass/Blame/Gap/Outside-G/RegRate × 5 family | Table 4 (Finding 3 主表) | 10→5 family mapping 没固化; paper 现有数字与 live data 不匹配 |
| **SC3b Outside-G behaviorally validated** | **E4** (Outside-G vs RegRate) | E1 per-edit log (含 $P_t$/$P_{t+1}$ + per-test pass/fail) | Outside-G per edit, RegressionRate per edit, scatter + regression | Figure 2 (Finding 3 副表) | Outside-G (strict) + RegressionRate code 都没实现 (CODE_GAPS §1+§2) |
| **SC4 Mis-loc → diffusion → regression** | **E8** (early-drift stratification) + qualitative case | E1 trajectory + active_fault label (per-turn) | Δpatch size, ΔOutside-G, ΔBlame@1, Miss-Hit | Table 6 (Finding 4) + Box 1 (Case 2 condensed) | active_fault per turn 没标; drift stratifier 没实现 |
| **(支撑性) full-transcript validity** | **E7** (3-protocol sanity) | `tracebench_hard.json` + `oracle_spans.json` | Same 4 metrics × 3 protocols | Appendix table | 没跑 (snapshot vs full $H_t$ vs summary) |
| **(支撑性) reproducibility** | **E6** (local model rows) | Same as E1 但 model 是 local | Same as E1 | Table 3 添加 2-3 local rows | 0/2 local model 跑过 |

### 关键数据依赖（按 dataset 文件）

| Data file | 用于哪些 Sub-Claim | 完成度 |
|-----------|-------------------|-------|
| `data/tracebench_full.json` (49 MB, 818) | SC1, SC2, SC3a | ✅ ready |
| `data/tracebench_hard.json` (21 MB, 128) | SC1, SC2, SC4 | ✅ ready |
| `data/oracle_spans.json` (46 KB, Hard 128) | SC1 (Blame), SC4 (drift) — **Hard only** | ✅ ready (Hard only) |
| `data/splits/manifest_*.json` | SC2 (slicing by difficulty/depth) | ✅ ready |
| `data/reference_trajectories/qwen3_32b_trace/` (CLI 格式 128) | dev reference, 不是 paper 主结果 | △ ready-but-unused |
| **active_faults_per_turn 字段** (派生) | SC4 全部; SC3b 在 Full 上 | 🔴 0/946, 需 1292 sandbox replay |
| **E1 trajectory dump** (planned) | 全部 4 个 SC | 🔴 0/12 cells |

---

## 4. 与 NeurIPS sibling work 的 boundary（必须在 paper 里写清楚）

| Paper | 主贡献 | TraceBench-Full (本文) 关系 |
|-------|-------|---------------------------|
| NeurIPS 2026 TraceBench-CLI + ARC (sibling) | CLI-form benchmark + controller + solve/waste/diagnosis/external transfer | 本文**不**重复; ARC 内容 paper §7 Appendix G **可选**用例 |
| Clean-PR (zhu2026) | PR-level training signal | training data, 不是 evaluation resource |
| daVinci-Dev (zeng2026) | agent-native mid-training | training recipe, 不是 evaluation resource |
| SWE-Bench Pro (deng2025) | enterprise-level long-horizon issues | realistic but no causal fault span |
| ContextBench / RACE-bench / TRAJEVAL / CodeTracer | trajectory diagnosis | partial process labels, 但 active fault 不是 counterfactual object |

**boundary 一句话**: 我们的 corner 是 *"controlled active fault + counterfactual repair + multi-turn transcript + behaviorally validated diffusion metrics"* — paper Table 1 大表用 6 个 axis 把这个 corner 钉死。

---

## 5. 今天汇报的 3 张 slide

### Slide 1 — Main + Sub Claims

```
MAIN CLAIM
"Outcome success ≠ process traceability in multi-turn code debugging."
TraceBench-Full = first causally-grounded, process-auditable dataset that
proves this is not a small-sample artifact.

SUB-CLAIMS
SC1  Pass-Blame gap is LARGE (30-65 pts) and PERSISTS at scale (818 problems)
SC2  TraceBench-Hard is DIAGNOSTIC (rating ≥ very_hard, depth 3.75) — not cherry-picking
SC3  Fault coverage TRANSPARENT (5 families × 1113 inj) + Outside-G BEHAVIORALLY VALIDATED (r=0.61)
SC4  Trace logs reveal MIS-LOC → DIFFUSION → REGRESSION (early Miss → +21.3 Outside-G later)
```

### Slide 2 — Experiment Plan (8 个)

```
P0 (必须):
  E1  6-model × 2-split main matrix       [Pass@1, Blame@1, Gap, Outside-G]   $597, 2 days
  E2  Difficulty/depth stratification     [from E1 sliced]                    0$, 0.5d
  E3  Fault-family breakdown              [from E1 + dataset]                 0$, 1d
  E4  Outside-G vs RegressionRate         [from E1 per-edit]                  0$, 2d (含 metric impl)
  E5  Cost accounting                     [E1 副产]                           0$, 0.3d

P1 (强烈建议):
  E6  Local-model reproducibility         [Qwen3-Coder-30B + Qwen2.5-32B]    GPU 8-12h, 2d
  E7  Full-transcript sanity check        [snapshot / full / +summary]        $35, 1d
  E8  Early-misloc → drift stratification [from E1 stratified]                0$, 0.5d

Total: 8 experiments, ~$632, 9.3 person-days, 3-week sprint
```

### Slide 3 — 数据/代码 Gap (一张表说完)

```
数据现状 (76 MB on disk):
  ✓ TraceBench-Full 818  — paper Table 2 数字全部对得上
  ✓ TraceBench-Hard 128  — paper Table 2 数字全部对得上
  ✓ oracle_spans (Hard)  — 128 task 的 ground truth
  ✗ active_fault per turn — 0/946 (需 1292 sandbox replay, 3h wall-clock)
  ✗ trajectory matrix     — 0/12 cells (需 $597 + 2 day wall-clock)

代码现状 (11 person-days to close):
  ✓ Blame@K, CF-Valid@1, AST 12-strategy injection, multi-turn runner
  ✗ Outside-G (strict 定义)        — paper Section 3 主指标
  ✗ RegressionRate (per-test diff) — paper Section 3 主指标
  ✗ active_fault selection          — paper Section 3 protocol
  ✗ per-traj progress slope         — paper Section 3 主指标
  ✗ repeats / test-without-edit     — paper Section 3 + Finding 4
  ✗ bootstrap CI                    — Table 3 caption claim
  ✗ family rollup (10→5)            — Table 4
  ✗ difficulty slicer               — Figure 1
  ✗ drift stratifier                — Table 6
  ✗ failure-mode classifier         — Table 6 frequency
  ✗ figure generation               — Figure 1, Figure 2
```

---

## 6. GPT 建议 vs 我们的实际能力对照

GPT 给的方案 high-level 没问题，但有几点根据我们实际盘点要微调:

| GPT 建议 | 我们实际能做 | 调整 |
|---------|------------|------|
| "至少一个本地模型 Full+Hard" | Qwen3-Coder-30B-A3B 本地 8×H100 估 8-12h × 2 split | ✅ 采纳; 主表加 Qwen3-Coder-30B 一个 row, Qwen2.5-32B 进 appendix |
| "Outside-G ≈ structural proxy for diffusion" | Paper 现有定义就是 fraction-edited-outside-G, 但 code 里只有 patch_locality (distance/IoU); 必须先 impl | ⚠️ 加到 critical path 最前 (CODE_GAPS §1) |
| "fault family 334+278+201+167+133=1113" | 实测 boundary 类 765, 不是 334; paper 数字 stale | ⚠️ Table 4 必须重算; mapping 没固化 |
| "Outside-G vs RegressionRate r=0.61, n=896" | RegressionRate 完全没实现; n=896 来源不明 (per-edit? per-traj? 哪些 model?) | ⚠️ 需要先 spec n 的单位; 跑 E1 后能算 |
| "RAD/ARC 移到 appendix optional use case" | NeurIPS sibling 已经卖 ARC, 这里只放 1 page appendix | ✅ 采纳 |
| "本地模型可能 JSON blame 不稳定" | 我们的 parser 会 fallback to empty; 已计为 attribution=0 | ✅ 已实现 |
| "rebuttal 已经把 Case 2 定义成 canonical mis-loc→diffusion→regression" | 我们 paper §5.4 已有 condensed Case 2 box | ✅ 已就绪 |

### GPT 没提到、但我们必须做的

1. **active_fault per turn 标签生成** (1292 sandbox replay) — GPT 没提，但 paper Section 3 metrics 全部依赖
2. **Code 实现 11 个 metric/slicer/classifier** (CODE_GAPS.md 全表) — GPT 默认 code 已经 ready
3. **去掉 paper §5 finding 1 表里 hard-only bootstrap CI 而 full-split 无 CI 的不对称**: 要么两个 split 都给 CI, 要么 footnote 解释为何只 Hard 给

---

## 7. 一个小风险 + 一个 punch-list

### 风险
"Qwen3-Coder-480B" 这个 model 名在 paper 出现 — 注意:
- NeurIPS sibling 也跑了 Qwen3-Coder-480B
- 如果 EMNLP 投稿是 anonymous, 两篇都跑同一组 model 不算 dual submission 信号
- 但 numbers 必须独立产出 (不要复用 NeurIPS run); 否则 ARR audit 会查到

### Punch-list (汇报后立即执行)

| Day | 任务 |
|-----|------|
| 1-2 | 实现 Outside-G + RegressionRate (CODE_GAPS §1+§2) |
| 2 | 实现 active_fault selection (§3); 跑 1292 sandbox replay (3h wall-clock) |
| 3 | Smoke test: 在 30 problems × Blame@1 + Outside-G + RegRate 都能算出数 |
| 4 | Kick E1 (6 model × 2 split API matrix) — wall-clock 1-2 day |
| 5-7 | 并行: 实现 §4-§7 (per-traj slope, repeats, bootstrap, family rollup); 本地 GPU 跑 Qwen3-Coder-30B (E6) |
| 8-9 | E1 完成 + 实现 E2/E4/E8 stratifier/scatter/drift |
| 10-12 | Bootstrap +12 runs; 填 Table 3/4/6 + Figure 1/2 in main.tex |
| 13-15 | Polish + appendix + bibkey audit + anonymous repo upload |

---

## 8. 汇报开场词 (60 秒版本)

> "这篇 paper 锁定为 dataset/evaluation 投 EMNLP，不卖 RAD 作主方法。Main claim 一句话: 在多轮代码修复里, outcome success ≠ process traceability, 我们用 818 个 problem 的 causally-grounded 数据集 + 三类过程指标证明这种分离不是小样本伪影。
>
> 数据 95% 就绪 (818 + 128 + 128 oracle), 但有两个空: 一个是 active_fault 标签需要 1292 次本地 sandbox replay (3小时), 一个是 trajectory matrix 6 model × 2 split 还没跑 (估 \$600 + 1-2 天).
>
> 代码 60% 就绪: Blame@K / CF-Valid 已经有, Outside-G (paper 主指标) / RegressionRate / active_fault selection / repeats / bootstrap / family rollup / 各种 slicer 都得补, 估 11 人-day. 加上跑 + paper polish, 总 critical path 是 3 周专职."

---

> **底线**: 这是一个 dataset paper，不是 method paper。Main contribution 是 **dataset + 三类 validated 过程指标 + 4 个 empirical findings**。所有实验都服务于 4 个 sub-claim, 不要再被 RAD 拉回 method paper。3 周 + \$800 是真实可达的 submission-ready budget.
