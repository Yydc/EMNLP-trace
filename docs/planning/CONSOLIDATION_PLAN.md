# 仓库收敛 Plan：把散落数据合并到 `~/Desktop/tracebench/` 一处

> 编写时间: 2026-05-15
> 状态: **plan only, 未执行**
> 目标: 把当前散落在 4 处的 data/code 收敛成一份适合 ACL 投稿用的 clean working dir
> 原则: **copy 不 symlink**（用户明确要求），保留 source 不动；只在 `~/Desktop/tracebench/` 下重组

---

## 1. 目标目录结构

```
~/Desktop/tracebench/                          ← 仍是工作根目录
├── data/                                      ★ 新建，paper-aligned data 一处汇总
│   ├── tracebench_full.json                   (49 MB, 818 problems)
│   ├── tracebench_hard.json                   (21 MB, 128 problems)
│   ├── oracle_spans.json                      (48 KB, 128 task 的 oracle blame span)
│   ├── splits/
│   │   ├── manifest_full.json                 (从 dataset 派生：trace_id + difficulty + rating)
│   │   └── manifest_hard.json
│   └── reference_trajectories/                ← 开发参考用，不是 paper 主结果
│       └── qwen3_32b_trace/                   (6.2 MB, 128 条 Qwen3-32B hard trace)
│
├── code/                                      ★ 整理后的单一 code 入口
│   ├── README.md                              (整合后的双语 readme)
│   ├── requirements-eval.txt                  (轻量：openai + anthropic + requests)
│   ├── requirements-build.txt                 (重量：含 vllm/torch，仅 data 生成需要)
│   ├── pyproject.toml                         (建议补，统一 packaging)
│   ├── tracebench/                            ← 主包，沿用现 src layout
│   │   ├── __init__.py
│   │   ├── runners/
│   │   │   ├── tracebench_runner.py
│   │   │   └── multi_model_runner.py
│   │   ├── evaluate.py                        (CLI entry)
│   │   ├── harness.py
│   │   ├── core/                              (from src/core/)
│   │   │   ├── ast_injector.py
│   │   │   ├── tracebench_generator.py
│   │   │   ├── tracebench_eval.py
│   │   │   ├── traceability_metrics.py
│   │   │   ├── solution_splitter.py
│   │   │   ├── risk_analyzer.py
│   │   │   ├── error_aware.py
│   │   │   ├── report_generator.py
│   │   │   ├── adversarial_generator.py
│   │   │   ├── dataset_loader.py
│   │   │   ├── multifile_converter.py
│   │   │   └── config.py
│   │   ├── agent/                             (from src/agent/)
│   │   ├── cli/                               (from src/cli/)
│   │   └── evaluation/                        (from src/evaluation/)
│   ├── scripts/                               (整合：build + filter + run)
│   │   ├── README.md                          (列每个脚本的用途)
│   │   ├── filter_by_depth.py
│   │   ├── filter_solved.py
│   │   ├── quality_filter.py
│   │   ├── run_pipeline.sh                    (修好 dead path 后)
│   │   ├── build_tracebench.py                (← 从 ICML 仓库回流)
│   │   ├── download_codeflow.py               (← 从 ICML 仓库回流)
│   │   ├── import_codeflowbench.py            (← 从 ICML 仓库回流)
│   │   └── procedure.md
│   ├── tbgen/                                 (← 从 ICML 仓库回流，dataset 生成 module)
│   ├── tbinfer/                               (← 从 ICML 仓库回流，inference module)
│   ├── tests/                                 ★ 新建（占位）
│   │   ├── __init__.py
│   │   ├── test_metrics.py                    (TODO: 占位)
│   │   ├── test_injector.py                   (TODO: 占位)
│   │   └── test_runner.py                     (TODO: 占位)
│   └── deprecated/                            ★ 不删但隔离的有问题文件
│       ├── README.md                          (说明为何隔离)
│       ├── baseline_runner.py                 (toy random mock，留作 reference)
│       └── tracebench_main_figures.py         (含 simulated data，不能进 release)
│
├── main.tex                                   ★ paper 主文件保留在根
├── custom.bib
├── acl.sty
├── acl_natbib.bst
├── ACL_formatting_reference.md
├── appendix_plan.md
├── main.pdf
├── main.bbl
├── README.md                                  ★ 重写：项目顶层说明
├── REVIEW_AND_ROADMAP.md                      (我之前写的)
├── DATA_LOCATIONS.md                          (我之前写的)
└── CONSOLIDATION_PLAN.md                      (本文件)
```

**核心改动**:
1. `~/Desktop/tracebench/code/ACL2026 codeflow-master_副本/` 这一层冗余目录**取消**——直接把内容拍平到 `code/`
2. 数据从四处汇总到 `data/` 一处
3. 增加 `data/reference_trajectories/`（已有 trajectory，便于 metric 开发）
4. 增加 `code/deprecated/` 隔离 toy mock 和 simulated-data 文件
5. 增加 `code/tests/` 占位（未来补单元测试）

---

## 2. 来源 → 目标 映射表

### 2.1 Data 部分

| 目标路径 | 来源路径 | 操作 | 大小 |
|---------|---------|------|------|
| `data/tracebench_full.json` | `~/Downloads/Tracebench-main/tracebench/data/tracebench.json` | cp | 49 MB |
| `data/tracebench_hard.json` | `~/Downloads/Tracebench-main/tracebench/data/tracebench_hard.json` | cp | 21 MB |
| `data/oracle_spans.json` | `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/oracle_spans.json` | cp | 48 KB |
| `data/reference_trajectories/qwen3_32b_trace/` | `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/trajectories/gold128_trace/` | cp -r | 6.2 MB (128 文件) |
| `data/splits/manifest_full.json` | 从 `tracebench_full.json` 派生 | python 脚本（包含 trace_id / rating / difficulty / depth / num_turns 等元字段） | < 1 MB |
| `data/splits/manifest_hard.json` | 从 `tracebench_hard.json` 派生 | python 脚本 | ~200 KB |

**Data 总大小**: ~76 MB

**不拉进来的 data 候选（理由）**:

| 候选 | 大小 | 不拉的理由 |
|------|------|----------|
| `tracebench_cli_gold128/` (128 个 docker task 目录) | 48 MB | NeurIPS CLI version 专用，ACL paper 是 JSON-based eval，不需要 docker form |
| `~/.cache/huggingface/.../CodeFlowBench-2505/` (3 个 parquet shard) | 690 MB | source raw dataset，离 ACL paper output 太远；若要重新生成 dataset 再拉 |
| `compute_runs/compute_matched/` 的所有 trace | ~15 MB | 都是 smoke (n=10, solve_rate=0)，还没产生有价值的数据 |
| `depth2/3/4_tracebench.json` | 52 KB | demo-only，已被 full split 覆盖 |
| ICML `inference_results*.json` | 115 KB | 旧 version 的 inference 结果，跟当前 paper 数字无关 |

### 2.2 Code 部分

#### 2.2.1 主代码：从 Tracebench-main 拷贝（这是最干净的 source）

**来源**: `~/Downloads/Tracebench-main/tracebench/`（Feb 2026, 无 `.DS_Store`，无 `files (2)/` 污染）

| 目标 | 来源 | 备注 |
|-----|------|------|
| `code/tracebench/runners/tracebench_runner.py` | `~/Downloads/Tracebench-main/tracebench/tracebench_runner.py` | 改路径到 runners/ |
| `code/tracebench/runners/multi_model_runner.py` | `~/Downloads/Tracebench-main/tracebench/multi_model_runner.py` | 同上 |
| `code/tracebench/evaluate.py` | `~/Downloads/Tracebench-main/tracebench/evaluate.py` |  |
| `code/tracebench/harness.py` | `~/Downloads/Tracebench-main/tracebench/harness.py` |  |
| `code/tracebench/core/*` | `~/Downloads/Tracebench-main/tracebench/src/core/*` | 把 `src/` 拍平 |
| `code/tracebench/agent/*` | `~/Downloads/Tracebench-main/tracebench/src/agent/*` |  |
| `code/tracebench/cli/*` | `~/Downloads/Tracebench-main/tracebench/src/cli/*` |  |
| `code/tracebench/evaluation/*` | `~/Downloads/Tracebench-main/tracebench/src/evaluation/*` |  |
| `code/scripts/filter_by_depth.py` | `~/Downloads/Tracebench-main/tracebench/scripts/filter_by_depth.py` |  |
| `code/scripts/filter_solved.py` | `~/Downloads/Tracebench-main/tracebench/scripts/filter_solved.py` |  |
| `code/scripts/quality_filter.py` | `~/Downloads/Tracebench-main/tracebench/scripts/quality_filter.py` |  |
| `code/scripts/procedure.md` | `~/Downloads/Tracebench-main/tracebench/scripts/procedure.md` |  |
| `code/scripts/run_pipeline.sh` | `~/Downloads/Tracebench-main/tracebench/scripts/run_pipeline.sh` | ⚠️ 含 dead path，复制后需手动修 |
| `code/test_multi_turn.py` | `~/Downloads/Tracebench-main/tracebench/test_multi_turn.py` | 移到 tests/，改名 `tests/smoke_multi_turn.py` |
| `code/tracebench/generate_solutions.py` | `~/Downloads/Tracebench-main/tracebench/generate_solutions.py` | 跟 generation 相关，留 |

#### 2.2.2 Build pipeline 模块：从 ICML 仓库回流（解决 Desktop 副本里的 dead path）

**来源**: `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/`

| 目标 | 来源 | 备注 |
|-----|------|------|
| `code/scripts/build_tracebench.py` | `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/scripts/build_tracebench.py` | 6 KB，**正是 run_pipeline.sh dead path 的目标** |
| `code/scripts/download_codeflow.py` | `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/scripts/download_codeflow.py` | 1.5 KB，从 HF 拉 CodeFlowBench |
| `code/scripts/import_codeflowbench.py` | `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/scripts/import_codeflowbench.py` | 6 KB |
| `code/scripts/example_complete_workflow.py` | `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/scripts/example_complete_workflow.py` | 8 KB |
| `code/tbgen/*` | `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/tbgen/` (除 `__pycache__`) | dataset 生成 module |
| `code/tbinfer/*` | `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/tbinfer/` (除 `__pycache__`) | inference module |

> ⚠️ 拉过来后需要做一次 **import path migration**：ICML 模块原本是 `tbgen.xxx` / `tbinfer.xxx`，新目录下应该已经 ok（因为放在 code/ 下平级），但要 grep `from tbgen` / `import tbgen` 确认 no breakage。

#### 2.2.3 隔离掉但不删的 deprecated 文件

| 目标 | 来源 | 隔离理由 |
|-----|------|---------|
| `code/deprecated/baseline_runner.py` | `~/Downloads/Tracebench-main/tracebench/baseline_runner.py` | 用 `random.random()` 模拟 success rate 的 toy mock，不能误用 |
| `code/deprecated/tracebench_main_figures.py` | `~/Desktop/tracebench/code/ACL2026 codeflow-master_副本/files (2)/tracebench_main_figures.py` | 含 `===== SIMULATED DATA =====` 硬编码数，**绝不能进 release** |
| `code/deprecated/README.md` | 新建 | 解释为啥这些文件被隔离 |

### 2.3 不带走、需要明确删除的内容

| 路径 | 操作 | 理由 |
|------|------|------|
| `~/Desktop/tracebench/code/ACL2026 codeflow-master_副本/` | **整个目录在迁移完成后删除** | 收敛后冗余 |
| 所有 `.DS_Store` | 删 | macOS 噪音 |
| 所有 `__pycache__/` | 删 | Python build artifact |
| `~/Desktop/tracebench/code/ACL2026 codeflow-master_副本/.claude/` | 删 | per-machine state |
| `~/Desktop/tracebench/code/ACL2026 codeflow-master_副本/files (2)/figure3.png` 等 png | 删 | 已知是 simulated 输出 |

---

## 3. 执行步骤（按依赖顺序）

> ⚠️ 每步都先 `dry-run`，再实际 cp/rm；rm 操作前再 confirm 一次。

### Step 1: 备份（防回退）

```bash
# 把当前 Desktop/tracebench 整体打个 timestamp tar，丢到 ~/Desktop/_backup/
mkdir -p ~/Desktop/_backup
tar -czf ~/Desktop/_backup/tracebench_pre_consolidate_$(date +%Y%m%d_%H%M%S).tar.gz \
    -C ~/Desktop tracebench
```

预计 backup tar 大小：~1 MB（main.tex/pdf + Desktop 副本里没真数据）。

### Step 2: 建立新目录骨架

```bash
cd ~/Desktop/tracebench
mkdir -p data/splits data/reference_trajectories
mkdir -p code/tracebench/runners code/tracebench/core code/tracebench/agent \
         code/tracebench/cli code/tracebench/evaluation
mkdir -p code/scripts code/tests code/deprecated
mkdir -p code/tbgen code/tbinfer
```

### Step 3: 拉数据

```bash
# data 主体（818 + 128）
cp ~/Downloads/Tracebench-main/tracebench/data/tracebench.json \
   ~/Desktop/tracebench/data/tracebench_full.json
cp ~/Downloads/Tracebench-main/tracebench/data/tracebench_hard.json \
   ~/Desktop/tracebench/data/tracebench_hard.json

# oracle spans
cp "/Users/apple/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/oracle_spans.json" \
   ~/Desktop/tracebench/data/oracle_spans.json

# 参考 trajectory（128 file, 6.2 MB）
cp -r "/Users/apple/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/trajectories/gold128_trace" \
      ~/Desktop/tracebench/data/reference_trajectories/qwen3_32b_trace
```

### Step 4: 派生 manifest

```bash
# 跑一个 python 脚本从 full/hard JSON 里抽元字段
python3 -c "
import json
for split in ['full', 'hard']:
    src = f'/Users/apple/Desktop/tracebench/data/tracebench_{split}.json'
    dst = f'/Users/apple/Desktop/tracebench/data/splits/manifest_{split}.json'
    d = json.load(open(src))
    manifest = [{
        'trace_id': e.get('trace_id'),
        'problem_id': e.get('problem_id'),
        'source': e.get('source'),
        'rating': e.get('rating'),
        'difficulty': e.get('difficulty'),
        'depth': e.get('depth'),
        'num_turns': e.get('meta_data',{}).get('num_turns'),
        'num_injections': e.get('meta_data',{}).get('num_injections'),
        'total_test_cases': e.get('meta_data',{}).get('total_test_cases'),
        'codeforces_tags': e.get('meta_data',{}).get('codeforces_tags'),
    } for e in d]
    json.dump(manifest, open(dst, 'w'), indent=2, ensure_ascii=False)
    print(f'{dst}: {len(manifest)} entries')
"
```

### Step 5: 拉 code（主体来自 Tracebench-main）

```bash
SRC="/Users/apple/Downloads/Tracebench-main/tracebench"
DST="/Users/apple/Desktop/tracebench/code"

# runners
cp "$SRC/tracebench_runner.py" "$DST/tracebench/runners/"
cp "$SRC/multi_model_runner.py" "$DST/tracebench/runners/"

# top-level entries
cp "$SRC/evaluate.py" "$DST/tracebench/"
cp "$SRC/harness.py" "$DST/tracebench/"
cp "$SRC/generate_solutions.py" "$DST/tracebench/"

# src/ 子树拍平到 tracebench/
cp -r "$SRC/src/core/"*.py "$DST/tracebench/core/"
cp -r "$SRC/src/agent/"*.py "$DST/tracebench/agent/"
cp -r "$SRC/src/cli/"*.py "$DST/tracebench/cli/"
cp -r "$SRC/src/evaluation/"*.py "$DST/tracebench/evaluation/"
cp "$SRC/src/__init__.py" "$DST/tracebench/__init__.py"

# scripts
cp "$SRC/scripts/"*.py "$DST/scripts/"
cp "$SRC/scripts/run_pipeline.sh" "$DST/scripts/"
cp "$SRC/scripts/procedure.md" "$DST/scripts/"

# smoke test
cp "$SRC/test_multi_turn.py" "$DST/tests/smoke_multi_turn.py"

# baseline_runner 隔离
cp "$SRC/baseline_runner.py" "$DST/deprecated/"
```

### Step 6: 从 ICML 回流 build pipeline 缺件

```bash
SRC_ICML="/Users/apple/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark"
DST="/Users/apple/Desktop/tracebench/code"

cp "$SRC_ICML/scripts/build_tracebench.py" "$DST/scripts/"
cp "$SRC_ICML/scripts/download_codeflow.py" "$DST/scripts/"
cp "$SRC_ICML/scripts/import_codeflowbench.py" "$DST/scripts/"
cp "$SRC_ICML/scripts/example_complete_workflow.py" "$DST/scripts/"
cp "$SRC_ICML/scripts/build_with_together.sh" "$DST/scripts/"

# tbgen / tbinfer 模块（去掉 __pycache__）
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
    "$SRC_ICML/tbgen/" "$DST/tbgen/"
rsync -av --exclude='__pycache__' --exclude='*.pyc' \
    "$SRC_ICML/tbinfer/" "$DST/tbinfer/"
```

### Step 7: 拉 simulated figures 到 deprecated

```bash
cp "/Users/apple/Desktop/tracebench/code/ACL2026 codeflow-master_副本/files (2)/tracebench_main_figures.py" \
   "/Users/apple/Desktop/tracebench/code/deprecated/"
```

### Step 8: 写新 README + requirements

需要新建（执行时由我写）：
- `code/README.md` — 双语，列项目结构 + 跑评测的最小命令
- `code/deprecated/README.md` — 解释每个 deprecated 文件的隔离原因
- `code/scripts/README.md` — 列每个脚本干什么
- `code/requirements-eval.txt` — 仅 `openai>=1.51 / anthropic / requests / numpy`
- `code/requirements-build.txt` — `vllm==0.6.2 / torch==2.1.2 / transformers==4.46.3 / openai>=1.51 / huggingface_hub`
- 项目根 `README.md` — 重写为顶层项目说明
- `code/tests/__init__.py`、`code/tests/test_metrics.py`（占位）、`code/tests/test_injector.py`（占位）

### Step 9: 修 dead path

`code/scripts/run_pipeline.sh` 里 `python3 generate_tracebench.py` 改成 `python3 scripts/build_tracebench.py` 或类似（**需要先 cat 两个 script 确认接口兼容**）。

### Step 10: 删原冗余目录

```bash
# 最后一步！先 ls 确认新 code/ 完整再删
rm -rf "/Users/apple/Desktop/tracebench/code/ACL2026 codeflow-master_副本"
# 删 .DS_Store
find ~/Desktop/tracebench -name ".DS_Store" -delete
find ~/Desktop/tracebench -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

### Step 11: 验证（最关键）

```bash
cd ~/Desktop/tracebench

# data 完整性
python3 -c "
import json
for split in ['full', 'hard']:
    d = json.load(open(f'data/tracebench_{split}.json'))
    print(f'{split}: {len(d)} problems')
    e = d[0]
    assert e.get('multi_turn'), f'{split} entry 0 lacks multi_turn flag'
    assert e.get('conversation_history'), f'{split} entry 0 lacks conversation_history'
    print(f'  ✓ multi_turn + conversation_history OK')

oracle = json.load(open('data/oracle_spans.json'))
print(f'oracle: {len(oracle)} task spans')
"

# code import 自检
python3 -c "
import sys
sys.path.insert(0, 'code')
from tracebench.core.traceability_metrics import TraceabilityMetrics
from tracebench.core.tracebench_eval import run_tracebench_eval
from tracebench.core.ast_injector import ASTInjector
print('✓ core imports OK')
"

# 跑 smoke test
cd code && python3 tests/smoke_multi_turn.py
```

---

## 4. 决策点（执行前需要你拍板）

每条都给一个 **建议默认**，你可以直接 "ok 按默认走"，或者改：

| # | 决策 | 选项 | 建议默认 |
|---|------|------|---------|
| D1 | `tracebench.json` 改名为 `tracebench_full.json` 让两个 split 对称？ | (a) 改名 / (b) 保留原名 `tracebench.json` | **(a) 改名** — 跟 paper 术语 TraceBench-Full 一致 |
| D2 | NeurIPS 的 128 条 Qwen3-32B trajectory 放哪？ | (a) `data/reference_trajectories/` (建议) / (b) `code/examples/` / (c) 不带走 | **(a)** — 是 data 性质，但要明确"reference / dev use only, 不是 paper 主结果" |
| D3 | 拉 `code/ACL2026 codeflow-master_副本/files (2)/figure3-5.png` 吗？ | (a) 带到 `data/_figures_simulated/` 留 warning / (b) 不带 | **(b) 不带** — 已知 simulated，留着只会污染 |
| D4 | ICML 的 `tbgen` / `tbinfer` 拉过来吗？ | (a) 都拉（建议）/ (b) 只拉 scripts/ 文件 / (c) 一个不拉 | **(a)** — `tbgen` 里有 dataset 生成的实际实现，比 Desktop 副本里的更完整 |
| D5 | `baseline_runner.py` 处置？ | (a) 移 deprecated/ (建议) / (b) 直接删 / (c) 保留 | **(a)** — 留 reference value，但显式 isolate |
| D6 | 把 `src/` 子树**拍平**到 `tracebench/{core,agent,cli,evaluation}/` 还是保留 `src/` 一层？ | (a) 拍平 / (b) 保留 `src/` | **(b) 保留 `src/`** — 改主意：拍平会破坏现有 `from src.core.xxx import ...` 的 import path，工作量很大且容易出错；保留 `code/tracebench/src/{core,agent,...}` 更 safe | 
| D7 | 把 `runners/` 单独抽出来吗？ | (a) 抽出 / (b) 跟 `harness.py` `evaluate.py` 平级保留 | **(b) 不抽** — 同上，少改 import path | 
| D8 | 项目根 `README.md` 重写还是保留？ | (a) 重写（建议）/ (b) 保留旧的 | **(a)** — 旧的只说 "is a self-contained LaTeX project"，不反映现状 |
| D9 | `code/tests/` 占位文件留空还是写 minimal failing test？ | (a) minimal failing test (建议) / (b) 全空 | **(a)** — 写 `pytest.skip("TODO")` 占位，至少能跑 |
| D10 | HF cache 的 CodeFlowBench-2505 (690 MB) 放进 `data/` 吗？ | (a) 放（占空间但自包含）/ (b) 不放（已在 HF cache，且 source-only） | **(b) 不放** — paper 不直接展示 source raw dataset；要 reproduce 时再 `huggingface-cli download` |

**重要的 D6/D7 修正**: 我在目标结构里写的"拍平 src/"是错的。看了一眼 import 链：

- `tracebench_runner.py` 用 `from src.agent.generation import CodeGenerator`、`from src.core.error_aware import ...`
- `evaluate.py` 用 `from src.core.tracebench_eval import run_tracebench_eval`

如果拍平 `src/`，需要把每个 `from src.xxx` 改成 `from tracebench.xxx`——风险/工作量大。**建议改方案：保留 `src/`**。修正后的目录结构是：

```
code/
├── README.md
├── requirements-{eval,build}.txt
├── tracebench_runner.py          (保留在 tracebench/ 同级)
├── multi_model_runner.py
├── evaluate.py
├── harness.py
├── generate_solutions.py
├── test_multi_turn.py            (smoke test 留这儿)
├── src/                          ← 完全沿用现 layout
│   ├── core/...
│   ├── agent/...
│   ├── cli/...
│   └── evaluation/...
├── scripts/                      (整合后)
├── tbgen/
├── tbinfer/
├── tests/                        ← 新增占位
└── deprecated/                   ← 隔离区
```

——更安全，少改 import。

---

## 5. 执行后的 sanity check 清单

1. ✅ `python -c "import json; print(len(json.load(open('data/tracebench_full.json'))))"` 输出 818
2. ✅ `python -c "import json; print(len(json.load(open('data/tracebench_hard.json'))))"` 输出 128
3. ✅ `python -c "import json; print(len(json.load(open('data/oracle_spans.json'))))"` 输出 128
4. ✅ `ls data/reference_trajectories/qwen3_32b_trace/ | wc -l` 输出 128
5. ✅ `find code -name "*.py" | head -5` 能看到 runners + core 模块
6. ✅ `cd code && python -c "from src.core.traceability_metrics import TraceabilityMetrics"` 不报错
7. ✅ `cd code && python test_multi_turn.py` smoke 通过（或者只 fail 在 API key 缺失）
8. ✅ `find . -name ".DS_Store" -o -name "__pycache__" | wc -l` 输出 0
9. ✅ `ls deprecated/` 看到 `baseline_runner.py` + `tracebench_main_figures.py` + `README.md`
10. ✅ root 下 `main.tex` `main.pdf` 等 paper 文件没被动

---

## 6. 估算 & 风险

**时间**: 实际执行 ~30 分钟（大头是 49 MB JSON cp + verification）

**磁盘**: `~/Desktop/tracebench/` 从当前 ~1 MB 涨到 ~78 MB（49 + 21 + 6.2 + code ~1 MB）

**风险点**:
- ⚠️ Step 6 拉 tbgen/tbinfer 后**可能有 import 冲突**（如果 src/core 里有同名模块）——建议先 grep 确认
- ⚠️ Step 9 修 run_pipeline.sh dead path 需要先确认 `build_tracebench.py` 接口与 `generate_tracebench.py`（不存在的那个）兼容
- ⚠️ Step 10 删 `code/ACL2026 codeflow-master_副本/`——**只有在 Step 11 验证通过后才能执行**。否则数据没了。
- ⚠️ `oracle_spans.json` 是 128 task 的 oracle，**只对 hard split 有**。Full split 的 819 个 problem 没有 oracle_spans。这一点在 paper 里 Outside-G 计算时要写清楚（或者 Full split 的 oracle 我们自己用 active-fault selection 算法重新生成）。

---

## 7. 等你拍板的事

请回答以下任一形式：
- (a) **"按默认走"**：我按 D1=改名 / D2=放 reference_trajectories / D3=不带 figures / D4=拉 tbgen+tbinfer / D5=baseline_runner 移 deprecated / D6=保留 src/ / D7=不抽 runners / D8=重写 README / D9=minimal failing test / D10=不放 HF cache 直接执行
- (b) **指定改动**：列出要改的 Dx 编号 + 选项
- (c) **改方案**：指出 Section 1 目录结构里要变的部分

确认后我开干。
