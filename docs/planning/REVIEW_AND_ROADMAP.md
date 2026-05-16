# TraceBench 草稿 Review、实验路线图 与 Code/Data 对齐报告

> 编写时间: 2026-05-14
> 对象: `main.tex`（v0, ACL 单栏 review 模板）+ `code/ACL2026 codeflow-master_副本/` 仓库
> 范围: 论文 review、对齐核查、补实验/补 code/补 data 的优先级路线图
>
> 这是一份"独立第三方阅读笔记"——刻意不直接修改任何文件，所有修改建议都写成可执行清单。

---

## 0. TL;DR (三句话总结)

1. **论文叙事自洽且立场清晰**：把贡献严格收敛到 "dataset + 评测协议 + 三类过程指标"，并明确把 RAD/ARC controller 推到 appendix，这点比之前的 controller 版本好得多。
2. **paper 主表的数字 vs. 仓库里的 data/code 严重不匹配**：论文宣称 818 problems / 2402 traces / 7165 tests / 1113 injections，但 `tracebench/data/` 下只有 8 条样本、53 条 test、且全部是 single-turn（没有 `conversation_history`、没有 `multi_turn=true`）。论文 4 个 finding 表里的 Pass@1 / Blame@1 / Outside-G / RegressionRate 数字目前**在仓库中无可重现来源**。
3. **三类过程指标里只有 1.5 个真正实现**：`Blame@1` ✅、`CF-Valid@1` ✅；`Outside-G` 只有近似的 `patch_locality.min_distance/mean_iou`（不是 paper 定义的 "fraction of edited lines outside G"）；`RegressionRate` 完全没实现；`Progress slope / R^2 / repeats` 是 dataset-level 拟合，不是 paper 描述的 per-trajectory。这是最大的代码缺口。

距离"能投稿"的真实距离：**Code 60% / Data 5% / Experiments 10%**。

---

## 1. 论文 Review (按章节)

### 1.1 Abstract & Intro (sec:intro)

**优点**
- "traceability gap" 这个 framing 干净、好引用，3 句话就能把 elevator pitch 讲清楚。
- 双 split (Full + Hard) 的设计有现实意义：单一 hard split 容易被审稿人质疑 "128 太小"，单一 full split 又容易 ceiling。
- Contributions bullet 写得克制，没堆。

**问题 / 建议**

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| I-1 | Abstract 里"7165 test cases"和后面 Table~\ref{tab:splits} 的 7165 数一致，但**仓库里只有 53 条 test**。这个数必须在投稿前来自真正的 dataset。 | ★★★ | 必须补 data 生成。优先级最高。 |
| I-2 | "edit-diffusion metrics against newly introduced regressions, showing diffusion captures harmful trajectory behavior rather than benign refactoring" —— 这是 paper 的一个**核心论点**，但目前实现里没有 RegressionRate 的代码。 | ★★★ | 补实现 + 补实验。 |
| I-3 | Intro 第 2 段大量引用 [jimenez2024swebench, deng2025swebenchpro, zhu2026cleanpr, zeng2026davincidev] —— 注意 cleanpr / davincidev / swebenchpro 这些 2025–2026 的引用要**逐条核对 bibkey + 年份**，否则 review 时容易被抓 fabrication。 | ★★ | 在投稿前列一个引用合法性检查清单。 |
| I-4 | "We call this mismatch the *traceability gap*" —— 这个 term 已被一些 SE/agent 工作零星用过，建议在 footnote 里说一句 "we follow the broad notion of process traceability in software engineering, instantiated here for multi-turn LLM debugging"，免得被指控 term 不新。 | ★ | footnote 一行字。 |
| I-5 | "Design principles" 那段是 5 条原则，但 Table~\ref{tab:design-principles} 也是 5 条，**两者一一对应但措辞不一致**（principle 5 paper 里叫 "structural metrics should be behaviorally checked"，table 里叫 "Behavioral validation"）。可读性上没问题，但严格审稿人会挑。 | ★ | 用同一个 short name 串起来。 |

### 1.2 Why a New Dataset (sec:why-dataset)

**Table~\ref{tab:benchmark-matrix}** 是这篇 paper 最核心的 positioning artifact，目前完成度最好。

**优点**
- 9 行 prior work 覆盖了 outcome-only / real-issue / seeded-debug / interactive / process-level 五个 family，剩余 gap 一栏写得诚实——不是无脑黑别人，而是承认每个都有自己的 axis。
- 用 ✓ / △ / ✗ 三档比纯 ✓/✗ 更有说服力。

**问题 / 建议**

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| W-1 | "Counterf. repair" 列里 Defects4J / SWE-bench 是 △ (partial)，但其实**人写的 patch 也可以视为 counterfactual repair**——审稿人很可能挑这个。 | ★★ | 在表注或正文加一句区分："natural patch ≠ minimal counterfactual span"。 |
| W-2 | TerminalBench / SWE-Bench Pro / Clean-PR / daVinci-Dev / ContextBench / RACE-bench / TRAJEVAL / CodeTracer 这些都是 2025–2026 的工作，**bibkey 必须逐条 verify**，否则审稿人一翻就发现是编的。 | ★★★ | 投稿前对 `custom.bib` 做一次 OpenReview + Google Scholar 实存性核查。 |
| W-3 | "Counterf. repair" 这一列对 ContextBench/RACE-bench/TRAJEVAL/CodeTracer 标 △ ——这几篇的 repair span 标注实际是什么形式需要在正文里**精确说一句**，否则审稿人会以为是无脑分类。 | ★★ | 给每个 prior work 加 1 句脚注或者扩展表（放 appendix）。 |
| W-4 | 表头列特别多 (9 columns)，单栏 layout 用 `\begin{adjustbox}{max width=\textwidth}` 压缩会牺牲可读性。 | ★ | 考虑把 "Multi-turn / Exec. feedback / Controlled fault" 合并成一个 "Trace structure" 复合列。 |

### 1.3 Protocol and Metrics (sec:metrics)

**优点**
- Full-transcript 协议写得清楚：$H_t$ 公式 + "drift in TraceBench is not caused by resetting the prompt" 这句话是非常好的防御性表述，预先 hedge 了一类潜在攻击。
- Table~\ref{tab:metrics} 三 axis × 三 metric 的 mapping 干净。
- "Why these metrics are jointly needed" 段落对应每个 axis ruling out 一类 failure mode，逻辑写得很顺。

**问题 / 建议**

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| M-1 | **Outside-G 的实现 vs. 定义不一致**。Paper 定义："fraction of edited lines outside the grounded fault neighborhood"。但 `src/core/traceability_metrics.py:178` 的 `_compute_patch_locality` 给的是 `min_distance / mean_iou / line_count_mean`——这是 **patch-bug 距离**，不是 **edited-line-outside-G 的占比**。 | ★★★ | 必须在 `traceability_metrics.py` 里补一个 `_compute_outside_g` 函数。 |
| M-2 | **RegressionRate 完全没实现**。Paper 把它写成 "behavioral validation" 的核心证据 (r=0.61, n=896)，但 codebase 没有 "before-edit pass set vs. after-edit pass set" 的差集统计。 | ★★★ | 必须补。下文 §3.3 给出具体接口。 |
| M-3 | "Active fault span" 的定义涉及**反事实回放**：injected fault i 的 counterfactual revert 必须 individually resolve 当前 failing assertion。但 codebase 里 `_extract_bug_spans` 只是把所有 injection 的 `anchor_line` 都当 bug span（`traceability_metrics.py:120`），**没有 active fault 的回放选择逻辑**。 | ★★★ | 这是核心 protocol，必须实现。 |
| M-4 | Figure~\ref{fig:metric-validation} 是一个**纯 LaTeX 框图**（minipage + tabularx），不是真的 figure。Paper 里写 "the final paper should replace this schematic with the scatter/regression plot"——这个 TODO 必须在投稿前 close。 | ★★ | 用 RegressionRate vs. Outside-G 的 real scatter 替换。 |
| M-5 | Accumulation 里 `Progress slope, R²` 在 code 里是 `_linear_fit` ——但**它拟合的是 dataset 级的 success_by_turn**（`tracebench_eval.py:118`），不是 paper 描述的 per-trajectory progress curve $\rho(P_t)$。这两个 fit 的解释完全不一样。 | ★★★ | 决定 paper 是 dataset-level 还是 trajectory-level；二者只能选一种讲法，目前是矛盾的。 |
| M-6 | "repeats" / "tests without intervening edits" / "newly failing tests" 三个 sub-signal **完全没有 code** 实现。 | ★★ | 这些是 finding 4 的核心，必须补。 |
| M-7 | Blame@K 实现 (line 136–176) 里有个**小 bug**：`if k > 1 and hit_by_k.get(k - 1)` 把 sorted_spans[:k] 当作 "top-k"，但后面只判 `hit_by_k[k] = 1` 不区分 strict vs cumulative。paper 报 Blame@1，单看 k=1 没问题，但 Blame@3 / Blame@5 的累计语义没写在 paper 里。 | ★ | 在 appendix 写清楚 Blame@K 是 strict top-K 还是 cumulative。 |

### 1.4 Dataset Pipeline (sec:pipeline)

**优点**
- Table~\ref{tab:splits} 是一张漂亮的 summary。
- "individual-failure + setwise-minimality" 是 paper 最重要的 causal claim，写得 compact。

**问题 / 建议**

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| P-1 | Table~\ref{tab:splits} 里数字 (818 / 2402 / 7165 / 128 / 442 / 1511 / ...) **在仓库里完全不可重现**。这是审稿人 sanity check 的第一目标。 | ★★★ | 必须生成全量数据并把统计脚本固化。 |
| P-2 | "individual failure" / "setwise minimality" 的 check 在 `tracebench_generator.py` 里只看到 `corrupted_error_type == "assert"`，没看到对 N-injection 数据集做"任意子集去掉就 still failing"的递归 check。 | ★★★ | 补 `validate_setwise_minimality()`。 |
| P-3 | "Rating mean / median" 列引用了 Codeforces rating——必须在 appendix 写清楚 rating 取的是 problem 级还是 contest 级；目前正文没有 source。 | ★★ | appendix 补一段。 |
| P-4 | "Avg injections / problem 1.36 / 1.40"——但 `tracebench_generator.py` 接受 `single_single / single_multi / multi_multi` 三种 mode，paper 没说三种 mode 的占比。审稿人会问：你 1.36 是从 mode 分布里平均出来的吗？ | ★★ | appendix 加 mode × split 的 breakdown。 |
| P-5 | "Multi-turn coverage 100%" —— 但 shipped data 全是 single-turn (无 `conversation_history`)。这条声明目前**反映的是 generator 能力，不是 dataset 实际状态**。 | ★★★ | 要么实际生成 multi-turn 数据，要么把这条声明退一步。 |

### 1.5 Findings (sec:findings)

#### Finding 1 (Pass-Blame gap) — Table~\ref{tab:gap}

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| F1-1 | 表里只有 2 个 model (Qwen3-Coder-480B / Claude-4.5 Sonnet) × 2 splits = 4 行。这对一个 EMNLP dataset paper 来说**模型覆盖太薄**。审稿人会问 GPT-4o / GPT-4.1 / o1 / DeepSeek-Coder / Llama-3-Coder / Gemini 在哪。 | ★★★ | 至少补 4–6 个 model。下文 §4 给出建议清单。 |
| F1-2 | 95% CI 只有 hard-split 有 (±5.7, ±3.8)，full-split 没 bootstrap CI——审稿人会立刻 reject 这种 asymmetric reporting。 | ★★ | 两个 split 都必须有 bootstrap CI。 |
| F1-3 | Pass@1 用了哪个 generator harness？paper 没明说。`multi_model_runner.py` 默认温度 0.35，Pass@1 一般报 greedy (T=0) 或 pass@k with k samples。 | ★★ | 在 §3 实验协议里固化一段。 |
| F1-4 | Claude-4.5 Sonnet 在 TBH 上 Pass@1=88.8 但 Blame@1=1.7 ——**1.7 这个数字太低，几乎是 0**。是 prompt 没在追问 blamed spans 吗？还是 parser 把 blamed spans 解析失败了？这种近似全 0 的结果如果不解释清楚，会被指控 implementation bug。 | ★★★ | 必须做 sanity diagnostic：取 10 个 Claude 失败 trace 看 raw output，明确是模型确实漏 blame 还是 parser 漏掉。 |

#### Finding 2 (TBH exposes process failures) — Table~\ref{tab:split-roles} / tab:use-recommendation / tab:difficulty-plan

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| F2-1 | Table~\ref{tab:difficulty-plan} 全是 `\todo{fill}`——**完全没有数据**。这是 reviewer 第一眼就会看到的 placeholder，是 reject signal。 | ★★★ | 投稿前必须填满。 |
| F2-2 | "average turns per problem 2.94 / 3.45" 出现在 5.1 的总表里也出现在这一段，但没说**是哪几个 model 上算出的平均**——每个 model 的 turn 数显然不一样。 | ★★ | 改成"averaged across models" 或加 footnote。 |

#### Finding 3 (Diffusion validation) — Table~\ref{tab:fault-family} / tab:diffusion-validation

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| F3-1 | Fault-family 表把 1113 injection 分成 5 类，但 `tracebench_generator.py` 里有 **11 个 strategies** (`boundary_condition_shift / off_by_one / wrong_return_variable / missing_update_in_branch / arg_swap_call / wrong_operator / initialization_error / variable_shadowing / loop_entry_condition / statement_omission / early_return_fallback / anchor_only`)。paper 的 5 类显然是后聚合的。 | ★★ | appendix 明确写出 11 → 5 的 mapping。 |
| F3-2 | "Outside-G vs RegressionRate: r=0.61, p<0.001, n=896" —— n=896 这个数字哪来的？818 problem × ? = 896？还是 trajectory × turn 级的 sample？这个 n 必须可重现。 | ★★★ | 在 appendix 写清楚 sample 单位 (per-edit / per-trajectory) 和 filtering。 |
| F3-3 | partial regression（控制 EditSize 后看 Outside-G 残差）在正文承诺要做但没数据。 | ★★ | 列入实验补做清单。 |

#### Finding 4 (Mis-loc → diffusion → regression) — Table~\ref{tab:early-drift} / tab:taxonomy

| # | 问题 | 严重度 | 建议 |
|---|------|--------|------|
| F4-1 | Table~\ref{tab:early-drift} 的 +12.4 / +21.3 / −36.0 也是**目前 codebase 里无法重算的**（依赖 first-blame hit/miss 的 per-trajectory stratification，code 没实现）。 | ★★★ | 补 stratification 脚本。 |
| F4-2 | tcolorbox 里 condensed qualitative case —— 这种"叙述性 case"在 EMNLP 容易被认为是 anecdotal。建议**至少配 1 张真的 trajectory diagram**（按 turn × edited region heatmap）。 | ★★ | 投稿前补图。 |
| F4-3 | Table~\ref{tab:taxonomy} 是 descriptive 的 5 类失败 mode，但**每一类 mode 在数据上的占比** paper 都没给。这是个明显的可加表。 | ★★ | "Taxonomy frequency by model" 表。 |

### 1.6 Release & Limitations (sec:release)

- Release artifact 列表写得不错。但要注意：投稿前必须真的把这些文件托管到 anonymous repo (anonymous.4open.science / HF datasets 匿名上传)。
- Limitations 段比较短——审稿人通常会要求**至少 3 类 limitations**：
  1. 限于 Python 算法题（这条有）
  2. 限于 AST-level injection（不能复现"真实"的 cross-file bug、并发 bug、性能 bug）
  3. Counterfactual repair 是"最小修改"，不是"开发者真实修复风格"
  4. 评测里 model 是 zero-shot 不带 tool use；agentic harness 没标准化

### 1.7 Appendix Plan (app:roadmap)

- 10 节的 appendix plan 写得齐全，但目前**全是占位**（只有 Full Metric Definitions 一节有 5 句话内容）。
- ACL/EMNLP 允许 unlimited appendix，但 review 时审稿人是否读取决于"appendix 里有真东西"。

---

## 2. Code 整理：仓库现状盘点

### 2.1 目录结构（去掉 macOS 噪音）

```
code/ACL2026 codeflow-master_副本/
├── README.md                          ← codebase 高层 README
├── requirements.txt                   ← vllm 0.6.2 + torch 2.1.2，注意版本锁很死
├── tracebench/
│   ├── data/
│   │   ├── tracebench.json            ← 8 个 entry，single-turn，全部 difficulty=3
│   │   ├── depth2/3/4_tracebench.json ← 各 2–3 个 entry，与 tracebench.json 有重叠
│   ├── scripts/                       ← pipeline 自动化脚本（bash + python）
│   │   ├── run_pipeline.sh            ← 7 步 pipeline (filter → generate → validate → inject)
│   │   ├── filter_by_depth.py
│   │   ├── filter_depth4plus.py       ← 旧版
│   │   ├── filter_solved.py
│   │   ├── quality_filter.py
│   │   └── procedure.md
│   ├── src/
│   │   ├── agent/                     ← prompt + generation
│   │   ├── cli/                       ← run_evaluation.py / generate_data.py
│   │   ├── core/
│   │   │   ├── ast_injector.py        ← 12 个 injection strategy 实现
│   │   │   ├── tracebench_generator.py
│   │   │   ├── tracebench_eval.py     ← MetricAggregator
│   │   │   ├── traceability_metrics.py← Blame@K / CF-Valid@1 / patch_locality
│   │   │   ├── solution_splitter.py
│   │   │   ├── risk_analyzer.py       ← Span dataclass
│   │   │   ├── error_aware.py
│   │   │   ├── report_generator.py
│   │   │   ├── adversarial_generator.py
│   │   │   ├── dataset_loader.py
│   │   │   ├── multifile_converter.py
│   │   │   └── config.py
│   │   └── evaluation/                ← pipeline / metrics / workflows / harness
│   ├── baseline_runner.py             ← Toy 仿真 runner（不调 LLM，用 random.random()）
│   ├── multi_model_runner.py          ← 真实多模型 runner（Qwen / Claude / OpenAI）
│   ├── tracebench_runner.py           ← 主 runner，含 multi-turn 路径
│   ├── evaluate.py                    ← 评测 CLI entry
│   ├── harness.py                     ← 沙箱执行
│   └── test_multi_turn.py             ← 冒烟测试
├── files (2)/                         ← figure3/4/5 + tracebench_main_figures.py
│   └── tracebench_main_figures.py     ← ⚠️ 用 SIMULATED DATA hard-code 出图
```

### 2.2 实现 vs Paper 的对齐矩阵

| Paper 概念 | Paper 位置 | Code 位置 | 状态 | 备注 |
|------------|-----------|-----------|------|------|
| 双 split (Full + Hard) | tab:splits | — | ❌ | 仓库无 full/hard 切分逻辑 |
| Verified $P^\star$ | sec:pipeline | scripts/filter_solved.py | ⚠️ partial | 但依赖 `data/datav3.json`（缺失） |
| AST-level fault injection | sec:pipeline | core/ast_injector.py | ✅ | 12 strategies |
| Individual-failure check | sec:pipeline | tracebench_generator.py 中 `corrupted_error_type == "assert"` | ⚠️ partial | 单 injection 可以 check，但**没看到对子集做 minimality recursive check** |
| Setwise-minimality check | sec:pipeline | — | ❌ | 完全缺失 |
| Active fault span (counterfactual replay) | sec:metrics | — | ❌ | `_extract_bug_spans` 只是把所有 injection 都视为 bug span，没有"哪个 injection causes current failure" 的回放选择 |
| Full-transcript $H_t$ | sec:metrics | tracebench_runner.py:340+ | ✅ | multi-turn path 已支持 |
| Blame@1 | tab:metrics | traceability_metrics.py:_compute_blame_at_k | ✅ |  |
| CF-Valid@1 | tab:metrics | traceability_metrics.py:_compute_cf_valid_at_1 | ✅ | 实现了"top-1 blame 与 bug span 取 overlap → 反事实 → 重跑" |
| Outside-$G$ | tab:metrics | ≈ patch_locality | ⚠️ partial | 实际算的是 distance/IoU，**不是 "fraction outside G"** |
| RegressionRate | tab:metrics | — | ❌ | 缺失 |
| Progress slope / $R^2$ | tab:metrics | tracebench_eval.py:_linear_fit | ⚠️ partial | 是 dataset-level，不是 per-trajectory |
| Repeats / test-without-edit | tab:metrics | — | ❌ |  |
| Outside-G vs RegressionRate (r=0.61) | fig:metric-validation / tab:diffusion-validation | — | ❌ | 论文核心点，code 不能产出 |
| Early mis-loc → drift stratification | tab:early-drift | — | ❌ |  |
| Difficulty band breakdown | tab:difficulty-plan | filter_by_depth.py 有 depth filter，但 depth ≠ difficulty rating | ⚠️ partial | depth 是 call-graph 深度，rating 是 Codeforces 分数 |
| Fault-family rollup (5 类) | tab:fault-family | injector 有 12 strategy，需要后聚合 mapping | ⚠️ partial | mapping 没固化 |
| Bootstrap CI | sec:findings | — | ❌ |  |

### 2.3 Code 健康度 / 整理建议

1. **`baseline_runner.py` 是个 toy mock**（用 `random.random()` 模拟 success rate），跟真正的评测无关。投稿前**必须从主入口移除**或者改名 `examples/random_baseline.py`，否则审稿人下载 code 第一眼就会怀疑整个评测都是 mock。
2. **`files (2)/` 目录**含有 `tracebench_main_figures.py`，里面所有 numbers 都是注释里写得明明白白的 `===== SIMULATED DATA =====`。这个文件**不能进 release**，否则马上被指控 fabrication。建议改名 `figures/_layout_preview.py` 并在 README 写明"layout preview only, do not use for paper figures"。
3. 中文注释满文件都是 (`# 配置日志`, `# === 策略池定义 ===`, `# 优先级：Tier 1 ...`)。EMNLP 投稿 release code 时建议**保留**（加分项：作者诚实），但**README 必须双语**。
4. `multi_model_runner.py` 和 `tracebench_runner.py` 功能重叠严重（prompt 构造 / patch span / anchor 提取几乎一致）。建议合并：保留 `tracebench_runner.py`，把 `multi_model_runner.MultiModelGenerator` 抽出来当 provider adapter。
5. `src/cli/run_evaluation.py` 与 `evaluate.py` 是两套入口，跑的是不同 pipeline——`evaluate.py` 调 `run_tracebench_eval`，`run_evaluation.py` 调 `run_enhanced_pipeline`。**用户视角混乱**。投稿前选一个，另一个删掉或者明确写"legacy"。
6. **缺测试**：除了 `test_multi_turn.py` 一个冒烟脚本，没有任何单元测试。审稿人下载 code 看到 unit test 是有加分的。建议补 `tests/test_metrics.py` 覆盖 Blame@K、CF-Valid@1、Outside-G 三个核心 metric。
7. `requirements.txt` 锁死了 `vllm==0.6.2 / torch==2.1.2 / transformers==4.46.3`——这些版本现在已经落后。但因为有外部 API 路径（Together / Anthropic / OpenAI），其实评测主路径不需要 vllm。建议拆 `requirements-eval.txt`（轻量，只要 `openai>=1.51 / anthropic / requests`）和 `requirements-train.txt`（带 vllm）。
8. `.DS_Store` 文件遍地都是（root, code/, code/ACL2026.../, tracebench/, src/, core/, agent/, evaluation/, data/）—投稿前 cleanup。

---

## 3. Data 对齐：仓库现状盘点

### 3.1 当前 shipped data 真实状态

| 字段 | Paper 声明 | 仓库现状 | 差距 |
|------|-----------|----------|------|
| Problems (TB-Full) | 818 | 8（多文件重叠后 unique 约 3–5） | ×100+ |
| Problems (TB-Hard) | 128 | 0 | 不存在 |
| Total turns | 2402 | 0（所有 entry 都是 single-turn，无 `conversation_history`） | ×∞ |
| Total test cases | 7165 | 53 | ×135 |
| Difficulty bands | 3 (Easy-Med / Hard / VeryHard+) | 1（全部 `difficulty_level=3 multi_multi`） | 没有 |
| Fault families | 5（聚合自 11 strategy） | 出现 5 种 strategy（off_by_one×2, statement_omission×3, wrong_operator×3, wrong_return_variable×1, variable_shadowing×1） | mapping 没做 |
| Rating (Codeforces) | mean 1699 / 1600 | 字段不存在 | 缺 |
| Multi-turn coverage | 100% | 0% | 完全反向 |

### 3.2 数据生成 pipeline 当前能否 run

- `scripts/run_pipeline.sh` 期待输入 `data/datav3.json`（不在仓库里），所以**整条 pipeline 现在不能从零跑起来**。
- 第 2/4 步 (`generate_solutions.py`) 调 Together (Qwen) + OpenAI (gpt-4.1-mini) API，依赖外部 key。
- 第 7 步 (`generate_tracebench.py`) **不在仓库根目录**——`run_pipeline.sh:241` 引用了 `python3 generate_tracebench.py`，但仓库只有 `tracebench/src/core/tracebench_generator.py`。这是个 dead path。

**结论**：数据 0 实质进度。只有 8 个 demo entry 用来跑 smoke test。

### 3.3 数据生成的优先动作（按 dependence 排序）

1. **拿到 source data**：locate 或重新构造 `data/datav3.json`（CodeFlowBench / Codeforces dump）。如果原始作者已经有，先放进仓库；如果没有，写一个 `scripts/download_codeforces.py`。
2. **修复 pipeline dead path**：`scripts/run_pipeline.sh` 里把 `generate_tracebench.py` 改成 `python -m src.cli.generate_data` 或者真的把 generator 暴露成 CLI。
3. **多轮化**：当前 `tracebench_generator.py` 接受 `multi_turn=True` 参数，但 8 个 sample 都是 single-turn——说明这个 flag 没被实际跑过。先用 `multi_turn=True` 跑 50 个 sample 验通。
4. **加 Codeforces rating 字段**：在 entry 顶层加 `rating` 字段，从 CF 元数据 join 进来。
5. **难度分桶**：基于 (rating × call-graph-depth × n_injections) 三个 axis 算难度 score，划成 Easy-Med (<1500) / Hard (1500–2200) / VeryHard+ (≥2200)，然后取 top 128 当 TB-Hard。
6. **Active fault label 生成**：跑 counterfactual replay——对每个 N-injection 样本，逐个 injection 单独 revert，记录哪些 revert 能 fix 当前 failing assertion，标 `active_fault_id` 字段。
7. **Test case 扩充**：当前每个 problem 4–10 个 test，paper 要 7165/818 ≈ 8.76 平均；现状 53/8 ≈ 6.6——偏低，需要补 test。

预期周期：拿到 source data 之后，**单机跑 818 个 problem 的全 pipeline 估计 2–3 天**（瓶颈在 generate_solutions 那一步 LLM 调用）。

---

## 4. 实验补做清单（按优先级排序）

### P0（不补完直接 reject）

1. **真实的 TB-Full / TB-Hard 数据集生成**（§3.3 第 1–7 步）。
2. **Pass@1 + Blame@1 主表填实**（Table~\ref{tab:gap}）：
   - Model 覆盖 ≥ 6 个：
     - Open weights: Qwen3-Coder-480B (已有占位), DeepSeek-Coder-V3, Llama-3.1-405B-Instruct, Qwen2.5-Coder-32B
     - Closed: Claude-4.5 Sonnet (已有占位), GPT-4o, GPT-4.1, Gemini-2.5-Pro
   - 每个 model 跑 5–10 个 seed，报 mean ± bootstrap 95% CI
   - 两个 split 都要有 CI（不能像现在只 hard 有）
3. **Outside-G 真实实现 + RegressionRate 真实实现**（§5 详述）。
4. **Outside-G vs RegressionRate 散点图**（替换 Figure~\ref{fig:metric-validation} 的 schematic）：
   - sample 单位定下来（建议 per-edit，n 大）
   - 报 Pearson r + p value，附 partial regression (control EditSize)。
5. **Difficulty-band table 填实**（Table~\ref{tab:difficulty-plan}）。
6. **Sanity diagnostic on Claude Blame@1=1.7%**：取 30 个 trace 手工或者半自动看 raw output，明确是模型 behavior 还是 parser bug。

### P1（不补完审稿人会反复要）

7. **Fault-family × model × split breakdown**（appendix table）：哪些 family 哪些 model 最弱。
8. **Difficulty-band × metric**：Pass@1 / Blame@1 / Outside-G / RegressionRate 在 Easy-Med / Hard / VeryHard+ 三个 band 的分布。
9. **Early mis-loc stratification** (Table~\ref{tab:early-drift})：first-blame hit/miss 分组的下游 metric 差。
10. **Failure-mode taxonomy frequency**（Table~\ref{tab:taxonomy} 的频率版）。
11. **Turn-budget sensitivity**：3 / 5 / 8 turn 下 Pass@1 / Blame@1 的变化（appendix）。
12. **Bootstrap CI on full split**（不能只 hard split 有）。
13. **Inter-judge agreement** for the failure-mode taxonomy（如果 taxonomy 是人工标的）。

### P2（强化卖点，能不补就先不补，但补了能涨分）

14. **Trajectory dynamics 图**（每 turn × 每 model 的 Pass@1 / Blame@1 曲线，替代 `tracebench_main_figures.py` 里的 simulated 版本）。
15. **Cost accounting** appendix：token cost + wall-clock + n_executions per model。
16. **Comparison with SWE-bench**：跑 SWE-bench Verified 上同样的 3 个 model 报 Pass@1 + 任意 process metric（哪怕是 patch-size），作为 "we are complementary not competing"。
17. **Qualitative case study × 3**（precise repair / drift / recovery），每个配真 trajectory diagram。
18. **Human study**：让 5 个 SE PhD 标 50 个 trajectory 的 failure mode，看跟 metric 的 agreement。

---

## 5. Code 需要新增 / 修改的具体接口

### 5.1 实现 Outside-G（M-1）

`src/core/traceability_metrics.py` 加：

```python
def _compute_outside_g(self, problem_log, active_spans, neighborhood_lines=3):
    """
    For each edit attempt, compute the fraction of edited lines whose distance
    to the nearest active span exceeds neighborhood_lines. Returns trajectory-mean.
    """
    fractions = []
    for sub in problem_log.get("subproblems", []):
        for att in sub.get("attempts", []):
            edited = att.get("edited_lines", [])  # 需要 runner 上报
            if not edited or not active_spans:
                continue
            outside = 0
            for ln in edited:
                d = min(abs(ln - g) for g in active_spans)
                if d > neighborhood_lines:
                    outside += 1
            fractions.append(outside / len(edited))
    return sum(fractions) / len(fractions) if fractions else None
```

需要在 runner 里把 `edited_lines` 上报给 attempt log。

### 5.2 实现 RegressionRate（M-2）

```python
def _compute_regression_rate(self, problem_log, entry, file_path):
    """
    For each (P_t → P_{t+1}) transition, run the full test suite on both,
    compute |passed_before ∩ failed_after| / |passed_before|.
    """
    tests = entry["evaluation"]["test_cases"]
    rates = []
    for sub in problem_log.get("subproblems", []):
        attempts = sub.get("attempts", [])
        for i in range(len(attempts) - 1):
            before_code = attempts[i].get("code")
            after_code = attempts[i + 1].get("code")
            if not before_code or not after_code:
                continue
            passed_before = self._run_per_test(before_code, tests, file_path)
            passed_after = self._run_per_test(after_code, tests, file_path)
            if not passed_before:
                continue
            new_fail = passed_before - passed_after
            rates.append(len(new_fail) / len(passed_before))
    return sum(rates) / len(rates) if rates else None
```

`_run_per_test` 必须返回**每个 test 的 pass/fail set**，不是当前 `_run_test_bundle` 那种 all-or-nothing。

### 5.3 Active fault selection（M-3）

```python
def _select_active_faults(self, entry, current_failing_assertion):
    """
    For each injection, apply counterfactual revert (use clean lines at injection span)
    and check whether the currently failing assertion now passes.
    Return injection ids whose revert fixes the current failure.
    """
    ...
```

注：这个是 dataset 一次性 pre-compute 的，不必每次 eval 都跑。可以放在 dataset 构造阶段，把结果写进 entry 的 `active_faults_per_turn` 字段。

### 5.4 Per-trajectory progress curve（M-5）

把 `MetricAggregator._linear_fit` 拆成两层：

- `per_trajectory_slope(rho_curve)` -> 每条 trajectory 一个 slope/R²
- `dataset_slope(per_traj_slopes)` -> 报均值 + 分布

paper 必须明确写"trajectory-level slope, averaged over instances"。

### 5.5 Repeats / TestWithoutEdit 计数（M-6）

```python
def _count_repeats(self, problem_log):
    """Count attempts whose patch is byte-identical to a prior attempt."""
def _count_test_without_edit(self, problem_log):
    """Count attempts where the code hash matches the prior attempt but a new test was triggered."""
```

### 5.6 Split builder（P-2 + P-3）

`src/cli/build_splits.py`：

```python
def build_splits(all_entries, rating_threshold_hard=2200, k_hard=128):
    """Produce tracebench_full.json + tracebench_hard.json + manifests."""
```

### 5.7 Fault-family rollup（F3-1）

`src/core/fault_families.py`：

```python
STRATEGY_TO_FAMILY = {
    "off_by_one": "Boundary/Off-by-one",
    "boundary_condition_shift": "Boundary/Off-by-one",
    "wrong_operator": "Wrong operator/condition",
    "loop_entry_condition": "Wrong operator/condition",
    "statement_omission": "Omission/missing branch",
    "missing_update_in_branch": "Omission/missing branch",
    "wrong_return_variable": "Dependency misuse",
    "variable_shadowing": "Dependency misuse",
    "arg_swap_call": "Dependency misuse",
    "initialization_error": "Corner-case/type",
    "early_return_fallback": "Corner-case/type",
}
```

固化这个 mapping，paper appendix 引用它。

---

## 6. 离 "跑完实验" 还剩多远？时间估算

> 假设：1–2 人 + 外部 API budget 充足 + 单台机器 + 没有 unforeseen blocker。

| 阶段 | 内容 | 工作量 (人天) | 阻塞前置 |
|------|------|--------------|---------|
| **0. 仓库整理** | 删 baseline_runner / `files (2)` rename / requirements 拆分 / .DS_Store 清理 / README 双语 | 0.5 | — |
| **1. 补 metric 实现** | Outside-G / RegressionRate / per-traj slope / repeats / active fault selection | 3–4 | — |
| **2. 单元测试** | tests/test_metrics.py 覆盖 5 个 metric | 1 | 1 |
| **3. 数据 source** | 拿到/重建 `data/datav3.json` | 1–3 | — |
| **4. 数据生成全跑** | 跑 run_pipeline.sh 到 818 problem 量级 + multi-turn 化 + active-fault 标注 | 2–4（含 API 等待） | 3 |
| **5. 分桶 + Hard split** | difficulty score → 三 band + 取 top 128 hard | 0.5 | 4 |
| **6. 主表 evals** | 6 model × 2 split × 5 seed 跑 Pass@1 / Blame@1 / Outside-G / RegressionRate | 3–5（瓶颈在 LLM 调用 throughput） | 1, 5 |
| **7. 子分析** | difficulty-band / fault-family / early-drift / repeats × model | 1–2 | 6 |
| **8. Figure 生成** | Outside-G vs RegressionRate 散点 + difficulty band heatmap + trajectory dynamics | 1 | 7 |
| **9. paper 数字回填** | 把 Table 1–10 的占位换成真实数 + 写 limitations 扩展 | 1 | 7, 8 |
| **10. Bootstrap CI + sanity** | 全部 metric 加 1000-resample CI + Claude Blame=1.7 的 diagnostic | 1 | 6 |

**最快线**：约 **14–22 人天**（≈ 2–3 周专注工作）。

**真实预估（含 debug / API rate-limit / 跑挂了重跑）**：**4–6 周**。

**风险点**：
- 数据 source 是不是有现成的——如果没有，4 → 8–10 人天。
- LLM API rate limit 和成本——Claude-4.5 Sonnet 上 128 hard split × 5 seed × 平均 3.45 turn × prompt ~5K token ≈ 11M tokens prompt + ≈ 1M output；按 $3/MT input + $15/MT output 算 ≈ $48/model；6 model ≈ $300。Full split 同算法 818 problem × 2.94 turn ≈ 200M token ≈ $700/model，6 model ≈ $4200。**预算应预留 $5–7K**。

---

## 7. 一句话总结建议（按优先级）

1. **马上：删 `baseline_runner.py` 和 `files (2)/tracebench_main_figures.py` 不能进 release 的部分**；保留 anonymous-friendly README。
2. **本周：把 Outside-G 和 RegressionRate 真正实现，写单元测试，跑通 8 个 demo entry**。
3. **下周：解决数据 source（`datav3.json`）问题；如果没有，重写一个 collector**。
4. **第 3 周：跑通 multi-turn 数据生成 + active-fault label，验证 50 个样本能闭环**。
5. **第 4–5 周：scale 到 818，跑 6 个 model × 2 split**，回填所有 placeholder 数字。
6. **第 6 周：补 figure、写 appendix、做 bootstrap CI、最终 polish**。

如果只有 2 周 deadline，**只投 TB-Hard 128 instance 版本，TB-Full 推到后续 extension**——单 split 投稿仍然成立（paper 现在的 framing 也支持 hard-only fallback），但表述需要软化。

---

*以上所有建议都按"不直接修改文件"原则，只列动作清单。如需我执行任何具体一项（比如先补 RegressionRate 的 implementation 或者先 clean code 仓库），请明确指定。*
