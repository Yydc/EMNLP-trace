# 项目数据位置盘点

> 编写时间: 2026-05-15
> 目的: 找出 paper 818 / 128 split 真正完整的 data 所在
> 结论: **真数据在 `~/Downloads/Tracebench-main/tracebench/data/`**

---

## 1. 完整数据本体（818 + 128 split）

### ⭐ `/Users/apple/Downloads/Tracebench-main/tracebench/data/`

**这是 paper Table~\ref{tab:splits} 实际对应的数据集**。打开能跑数。

| 文件 | 大小 | 条目 | 状态 |
|------|------|------|------|
| `tracebench.json` | 49 MB | **818** problems | ✅ 完整 multi-turn，对应 `TraceBench-Full` |
| `tracebench_hard.json` | 21 MB | **128** problems | ✅ 完整 multi-turn，对应 `TraceBench-Hard` |
| `depth2_tracebench.json` | 12 KB | 3 | demo only |
| `depth3_tracebench.json` | 24 KB | 3 | demo only |
| `depth4_tracebench.json` | 16 KB | 2 | demo only |

**数据 schema**（已实际验证）：

```jsonc
{
  "trace_id": "TB_HARD_00000",
  "problem_id": "1054H",
  "source": "...",
  "rating": 3500,             // Codeforces rating ✅ paper 引用了
  "difficulty": "extreme",    // easy / medium / hard / very_hard / extreme / unrated
  "depth": 4,                 // call-graph 深度
  "multi_turn": true,         // ✅ 真的是 multi-turn
  "conversation_history": [   // ✅ 真的有 conversation_history
    {
      "turn_id": 0,
      "context": "...",
      "target_code": "...",
      "original_target_code": "...",
      "test_cases": [...],
      "has_error": false,
      "subproblems": ["compute_sum"],
      "depth": 2,
      "injections": []
    },
    {
      "turn_id": 1,
      "has_error": true,
      "subproblems": ["main"],
      "injections": [{"injection_id": "INJ_T01", "type": "boundary_condition_shift", ...}],
      "test_cases": [...]
    }
  ],
  "injections": [...],        // 全局聚合
  "original_code": "...",
  "task_description": "...",
  "meta_data": {
    "difficulty_level": 2,
    "difficulty_desc": "mixed",
    "num_turns": 2,
    "error_turns": [1],
    "num_injections": 1,
    "rating": 3500,
    "difficulty": "extreme",
    "codeforces_tags": [...],
    "total_test_cases": 6
  }
}
```

### 实际统计 vs Paper claim 对照

| 字段 | Paper (TB-Full / TB-Hard) | Data 实测 (Full / Hard) | 一致性 |
|------|---|---|---|
| Problems | 818 / 128 | **818 / 128** | ✅ 精确 |
| Total turns | 2402 / 442 | 2377 / 438 | ✅ 差 1% |
| Total test cases | 7165 / 1511 | **7165 / 1511** | ✅ 精确 |
| Total injections | 1113 (Full) | **1113 (Full)** | ✅ 精确 |
| Avg turns / problem | 2.94 / 3.45 | 2.91 / 3.42 | ✅ 差 1% |
| Rating mean | 1699 / 2679.7 | 1713.7 / **2679.7** | ✅ Hard 精确，Full 差 0.8% |
| Rating median | 1600 / 2700 | **1600 / 2700** | ✅ 精确 |
| Depth mean | 3.20 / 3.75 | **3.20 / 3.75** | ✅ 精确 |
| Multi-turn coverage | 100% | **100%** | ✅ |
| Avg injections / problem | 1.36 / 1.40 | 1.36 (1113/818) / 1.40 (179/128) | ✅ |

**结论**：Paper 的所有 Table~\ref{tab:splits} 数字都能在这份数据上直接重算出来，最大差异 1%（可能是 dataset 后期 minor patch）。

### Difficulty 分布（Full split）

```
extreme    67
very_hard  123
hard       210
medium     207
easy       204
unrated    7
```

Paper "Easy / Medium / Hard / VeryHard+" 三 band 对应：
- Easy-Med = easy + medium = 411
- Hard = 210
- VeryHard+ = very_hard + extreme = 190
- unrated 7 个怎么处理需要确认（建议剔除或归 Easy-Med）

### Injection 类型分布（10 种 strategy）

Full split:

```
boundary_condition_shift  513   ← 这一类最多
off_by_one                252
variable_shadowing        165
statement_omission         84
wrong_operator             77
wrong_return_variable       7
early_return_fallback       5
arg_swap_call               5
missing_update_in_branch    4
initialization_error        1
                       ━━━━━
                         1113
```

⚠️ 但 paper Table~\ref{tab:fault-family} 用的是 5 类聚合 (334+278+201+167+133=1113)，**5 类的具体 mapping paper 没写**——和这 10 种 strategy 的对应关系需要 reverse-engineer 或者直接问原作者。

---

## 2. 其他 candidate 仓库的状态

### `/Users/apple/Desktop/tracebench/code/ACL2026 codeflow-master_副本/`

这是用户给我的那份 working copy——`data/` 下只有 demo（8 条 entry，44 KB）。**没有真数据**。

### `/Users/apple/Downloads/All Projects/ACL2026 codeflow-master/`

跟上面那份是兄弟备份，**也只有 44 KB demo**，没有真数据。

| 文件 | 大小 |
|------|------|
| `tracebench/data/tracebench.json` | 44 KB（demo only） |
| `tracebench/data/depth2/3/4_tracebench.json` | 同 demo |

### ⭐ `/Users/apple/Downloads/All Projects/Neurips2026_tracebenchcli/`

**这是 NeurIPS 2026 投稿用的 CLI 版本**，包含：

- `02_anonymous_review_code/` (54 MB)：anonymous review-ready 包
  - `tracebench_cli_gold128/` — **128 个独立 task 目录**，每个 task 是一个完整的"CLI"形态：
    ```
    tb_hard_00000/
    ├── environment/   # docker/uv 环境
    ├── instruction.md # task prompt
    ├── solution/      # reference solution
    ├── task.toml      # task config
    └── tests/         # tests
    ```
  - `oracle_spans.json` — 128 个 task 的 oracle fault span (per-file line numbers)
  - `tracebench_cli_gold128_manifest.json` — 128 task 的清单
  - `trajectories/gold128_trace/` — **128 条已收集的 trajectory**（Qwen3-32B trace mode）
  - `trajectories/case_studies/` — 案例研究
  - `summaries/` — 已聚合的统计
- `04_development_assets/` (90 MB)：
  - `compute_runs/` — 已跑过的 model × controller 矩阵
    - `compute_matched/openai/` 含 gpt4o-mini / gpt54 / gpt54-mini / gpt54-nano × {arc, best-of-n, heuristic-rerank, trace, trace-scheduled-blame} 五种 controller
    - 当前都是 smoke (n=10) 且 solve_rate=0 → 还是 pilot stage
  - `data_snapshot/` — 与 02 的 review code data 同步
  - `figure_sources/` / `figures_pdf/` / `tables/` — 已生成的图表素材
- `01_submission_tex/` — submission 草稿源码

**重要**: 已经收集到的 trajectory 数据：
- `gold128_trace/` 下 **128 个 trajectory file**（Qwen3-32B 一个 model）
- `gold128_trace_aggregate.json` 给出聚合 metric：
  ```
  n_tasks: 128
  n_passed: 40
  solve_rate: 0.3125
  mean_wasted_turns: 4.8672
  mean_test_without_edit_rate: 0.6175    ← paper "test-without-edit" 指标已经在这儿
  mean_empty_command_rate: 0.0669
  total_blame_calls: 6
  tasks_with_any_blame: 4                ← 只有 4 个 task 有 blame call
  ```

> ⚠️ 注意：这个 "Qwen3-32B trace" 跑出来只有 4 个 task 触发 blame，跟 paper claim 的 Blame@1=49.5%（Qwen3-Coder-480B Full）/ 13.1%（Hard）数量级不一致。两点可能：
> 1. 这里用的是 **32B**，不是 480B，能力差很多。
> 2. paper 数字可能来自另一套 run。
>
> 这个不一致需要去原作者那里 confirm。

### `/Users/apple/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/`

ICML 2025 投稿的更早 version，已有大量 scripts：
- `scripts/build_tracebench.py`、`scripts/download_codeflow.py`、`scripts/import_codeflowbench.py` — **数据 build pipeline 的源头脚本**（Desktop 副本里这些是缺的）
- `tbgen/`、`tbinfer/` — generator + inferer 模块
- `inference_results.json` (19 KB)、`inference_results_improved.json` (96 KB) — 早期 inference 结果
- `data/tracebench_together/tracebench__unknown/` — 空目录，data 没保留
- `test_pipeline_output/` — pipeline 输出 demo（含 turn_1_input.json 到 turn_6_input.json）

> 💡 如果想重建数据生成流程，**`scripts/download_codeflow.py` + `scripts/build_tracebench.py` 这两个脚本可能就是当年生成 818 split 的 ground-truth**。Desktop 副本的 `run_pipeline.sh` 引用了一个不存在的 `generate_tracebench.py`，但 ICML 版本里有真东西。

### `/Users/apple/.cache/huggingface/hub/datasets--WaterWang-001--CodeFlowBench-2505/`

HuggingFace 上 **CodeFlowBench-2505** 数据集本地缓存，**690 MB**：
- 三个大 blob（261 MB + 217 MB + 149 MB + 44 MB + 19 MB），看 size 像是分 parquet shard。
- 这是 paper Section~\ref{sec:pipeline} 提到的 source dataset（"CodeFlow_xxx" 系列 problem id 应该都来自这里）。
- 如果要重跑生成 pipeline，**这就是 input source**。

---

## 3. 数据流图

```
  HuggingFace: WaterWang-001/CodeFlowBench-2505 (~/.cache/huggingface/, 690 MB)
                                  │
                                  ▼
  ICML2025_ECON/tracebench_benchmark/scripts/{download_codeflow,build_tracebench}.py
                                  │
                                  ▼
                  (历史 pipeline，运行后产出 …)
                                  │
                                  ▼
  ⭐ Tracebench-main/tracebench/data/
        ├── tracebench.json          (818 problems, Full split)
        └── tracebench_hard.json     (128 problems, Hard split)
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
        ACL2026 paper formulation          NeurIPS2026 CLI version
        (sub-paper draft 用的 split)       (改造成 docker/uv CLI 形态)
                                                  │
                                                  ▼
                Neurips2026_tracebenchcli/02_anonymous_review_code/
                  ├── tracebench_cli_gold128/    (128 task 目录 + tests + sol)
                  ├── oracle_spans.json          (gold blame label)
                  └── trajectories/gold128_trace/ (128 条 Qwen3-32B trace)
```

---

## 4. 立即可用的操作

### 4.1 用真数据替换 Desktop 副本里的 demo

```bash
# 把 818 split 链接进 Desktop 工作目录
ln -sf "/Users/apple/Downloads/Tracebench-main/tracebench/data/tracebench.json" \
       "/Users/apple/Desktop/tracebench/code/ACL2026 codeflow-master_副本/tracebench/data/tracebench_full.json"

ln -sf "/Users/apple/Downloads/Tracebench-main/tracebench/data/tracebench_hard.json" \
       "/Users/apple/Desktop/tracebench/code/ACL2026 codeflow-master_副本/tracebench/data/tracebench_hard.json"
```

> 注意：不要直接覆盖原来的 `tracebench.json`——demo file 还有 valgrind 价值。建议用 `tracebench_full.json` 新文件名。

### 4.2 验证 paper 数字（已经做完）

我刚跑过的 verification 脚本就在 `Bash` 命令历史里，关键结论是 paper Table~\ref{tab:splits} 的所有数字（818 / 128 / 7165 / 1511 / 1113 / depth 3.20 / 3.75 / rating 1600 / 2700）**都对得上**，最大偏差 1%（2402 vs 2377 turns），可能是 dataset 后期 patch。

### 4.3 直接复用 NeurIPS 的 trajectory

`Neurips2026_tracebenchcli/02_anonymous_review_code/data/trajectories/gold128_trace/` 下的 128 条 Qwen3-32B trajectory 已经存在，**这是现成的 trajectory source**，可以直接用来：
1. 验证 Outside-G 和 RegressionRate 实现的正确性（需要先把 metric 实现到位）
2. 跑 early mis-loc → drift 分析（Table~\ref{tab:early-drift}）
3. 写 case study (Section~\ref{sec:findings} Finding 4)

但要注意：这是 **32B model** 的 trace，跟 paper 报的 **480B + Claude-4.5** 不一样。

### 4.4 重建数据生成 pipeline

如果要 reproduce 数据生成：
1. ICML 仓库的 `scripts/build_tracebench.py` + `scripts/download_codeflow.py` 是源头
2. HF cache 里 `datasets--WaterWang-001--CodeFlowBench-2505` 是 input
3. 整套 pipeline 应该能 reproduce 818 split

但**没必要 reproduce**——既然 `Tracebench-main/` 里已经有现成的 818 / 128 split，直接复用即可。

---

## 5. 仓库收敛建议

目前 **5 个相关 project 散落在 4 个 location**。投稿前最好整合：

| 现在 | 建议 |
|------|------|
| `~/Desktop/tracebench/code/ACL2026 codeflow-master_副本/` | **当前 working dir**，保留 |
| `~/Downloads/Tracebench-main/tracebench/data/` | data 源，**软链或复制 tracebench.json + tracebench_hard.json 到 working dir** |
| `~/Downloads/All Projects/ACL2026 codeflow-master/` | 冗余备份，可弃 |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/` | 含 trajectory 和 oracle_spans，**保留作为 trajectory source** |
| `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/` | 含 build pipeline 脚本，**保留作为 generation reference** |
| `~/.cache/huggingface/.../CodeFlowBench-2505/` | source dataset，HF cache 不动 |

---

## 6. 重要的下一步动作（基于这次发现 update 我之前的 REVIEW_AND_ROADMAP.md）

之前的 review 里我说 "Data 5% 完成度"——**这个判断错了**。基于这次发现：

- **Data: 实际上 95% 完成度**（818/128 split 已经有，只是没放在 Desktop working dir 里）
- **Trajectory: 5–10% 完成度**（NeurIPS 仓库有 128 条 Qwen3-32B trace，但 paper 需要 6 model × 2 split 的全矩阵，目前只有 1 model × 1 split）
- **Code metric 实现: 60% 完成度**（Outside-G、RegressionRate、repeats、active-fault selection 还得补，跟原结论一致）
- **Code repo 整理: 30% 完成度**（5 个备份需要收敛）

**修正后的距离估算**：
- 不再需要 "拿到 source data + 跑全 pipeline" 这步（省 5–7 人天）
- 反而要 **从 NeurIPS CLI 版本回流 oracle_spans 和 trajectory 的现成数据**
- 距离投稿的真实 critical path：metric 补全（3–4 天）→ trajectory matrix 补跑（6 model × 2 split，3–5 天 LLM API time）→ Paper 数字回填（1 天）→ Polish（2 天）= **约 10–14 人天**（≈ 2 周专注）

预算下调：
- LLM cost 仍 ~$5K
- 时间从 4–6 周缩短到 **2–3 周**
