# 之前 data 哪些能用上？

> 2026-05-15 — 实验数据清单
> 已经盘点了 6 个 candidate 来源，下面一张表说清能用 / 不能用 / 怎么用。

---

## 一句话总结

✅ **`~/Desktop/tracebench/data/` 下 5 项全部直接复用，0 项需要重新构造**。
⚠️ **128 个 Qwen3-32B reference trajectories 只能用在 Section 5.4 case study + appendix**（schema 不兼容主表）。
✅ **NeurIPS sibling repo 还有 2 个高质量 case studies + 1 个真 aggregate 数字**，可以借到 paper 里。
❌ **HF source raw dataset、ICML build scripts、NeurIPS 的 n=10 smoke runs 都用不上**。

---

## 现有 data 用途映射表

每行: data 资产 → 在 paper 里出现的位置 → 是否需要重新跑

| # | 资产 | 来源 | 大小 | 用在 paper | 用在 code | 还需要跑吗？ |
|---|------|------|------:|-----------|----------|------------|
| 1 | `tracebench_full.json` | `~/Desktop/tracebench/data/` | 49 MB | **Table 4 splits stats** + 每个 Full 行的输入 + Table 9 family rollup + Table 8 difficulty band | every model run + `fault_families.py` + `difficulty_slicer` | ❌ **不用** — 直接 read |
| 2 | `tracebench_hard.json` | 同上 | 21 MB | **Table 4** + Table 5 Hard 列 + Table 8/11/12 Hard 数据 | every model run | ❌ **不用** — 直接 read |
| 3 | `oracle_spans.json` | 同上 | 46 KB | Hard split 的 Outside-G ground truth | `metrics_v2.active_spans_from_entry` 作为 fallback；`drift_stratifier` 校验 | ❌ **不用** — 已就绪 |
| 4 | `splits/manifest_full.json` | 同上（派生） | 282 KB | Table 8 (band slice) + 速读 | `difficulty_slicer.slice_by_band` 输入 | ❌ **不用** — 已派生 |
| 5 | `splits/manifest_hard.json` | 同上（派生） | 46 KB | Table 8 (band slice) + 速读 | 同上 | ❌ **不用** — 已派生 |
| 6 | `reference_trajectories/qwen3_32b_trace/` (128 files) | 同上 | 6 MB | ⚠️ **Section 5.4 Box 1 case study source** + **Appendix Case 1/2/3 candidates** | dev reference for analysis script smoke test | ⚠️ **不入主表**（schema 不兼容）但**写 case study 时直接引用其中 turn-level llm_output / command / stderr** |

### 关于 #6 reference_trajectories 的精确说明

格式 mismatch 详情:

```
Qwen3-32B trace schema (per-turn):           Paper Table 5 needs (per-attempt):
  turn_id                                      attempt_number
  llm_output                                   generated_code  ← 需从 llm_output 提取
  llm_reasoning                                ✗
  command  (terminal style: cat/python/...)    ✗
  stdout / stderr / exit_code                  ✗
  stage                                        ✗
                                              blame_spans      ← 没有
                                              edited_lines     ← 没有
                                              per_test_results ← 没有
                                              code_before      ← 没有
```

**结论**: 这 128 条 trajectory **不能换算成主表第一行**。换算成本（写 retrofit 脚本 + 重新模拟 sandbox）≈ 重新跑一遍。

**但可以用作:**
- ✅ **写 Section 5.4 condensed case study box** 时引用具体 turn 序列（如 `tb_hard_00012` solved at turn 13，`tb_hard_00000` 在 turn 13 因为 format error 崩了）
- ✅ **Appendix Case 1/2/3** 直接用 `tb_hard_00012` (precise repair) + `tb_hard_00000` (format-error breakdown)
- ✅ **Smoke 测试新写的 analysis 脚本** — 我已经在 `smoke_pipeline.py` 里这样做过

---

## 外部 candidate（不在 `~/Desktop/tracebench/data/` 但探索过的）

| 资产 | 状态 | 决定 |
|------|------|------|
| `~/Downloads/Tracebench-main/tracebench/data/tracebench.json` | 我们用的 818 split 的原版 | ✅ 已 copy 入 `data/`，不再用源 |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/oracle_spans.json` | 我们的 `data/oracle_spans.json` 就是它 | ✅ 已 copy，不再用源 |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/trajectories/case_studies/` (2 files: `tb_hard_00000` + `tb_hard_00012`) | NeurIPS 已经精选过的代表性 trajectory | ⭐ **可借用** — 用作 paper Section 5.4 + appendix。已验证：`tb_hard_00012` passed=True/27 turns (precise repair case)；`tb_hard_00000` passed=False/27 turns (format error, first_error_turn=13). 这两条天然对应 paper 5-mode taxonomy 中的 precise_repair + symptom_patch/regression_loop |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/summaries/gold128_trace_aggregate.json` | Qwen3-32B × Hard 的真 aggregate: solve_rate=31.25%, mean_wasted_turns=4.87, mean_test_without_edit_rate=0.62 | ⚠️ **不入主表**（model 不是 SOTA），但 **可以在 paper 里作为 "even with older model architectures, the pattern holds" 的 sentinel reference** 引用一次 |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/summaries/audit_report_v3.json` | Dataset structural validity report: 128/128 tasks pass all sanity checks | ⭐ **可借用** — paper Section 4 (Dataset Pipeline) 可以引用 "all 128 Hard tasks pass structural validity checks at dataset build time" |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/02_anonymous_review_code/data/tracebench_cli_gold128/` (128 docker tasks) | NeurIPS-CLI 版本，docker/uv 形式 | ❌ **不用** — ACL paper 用 JSON 评测，与 docker 形式正交 |
| `~/Downloads/All Projects/Neurips2026_tracebenchcli/04_development_assets/compute_runs/compute_matched_smoke/` | n=10 smoke runs (gpt4o-mini / gpt54 / gpt54-mini / gpt54-nano × 5 controllers), 全部 solve_rate=0 | ❌ **没用** — pilot 失败的数据，连 sanity 都不算 |
| `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/scripts/{build_tracebench,download_codeflow}.py` | dataset 构造管线 | ❌ **不用** — 已 copy 入 `code/scripts/` 备用；只有重建 dataset 时才需要 |
| `~/Downloads/All Projects/ICML2025_ECON/tracebench_benchmark/{tbgen,tbinfer}/` | dataset 生成 + inference module | ❌ **不用** — 已 copy 入 `code/`，备用 |
| `~/.cache/huggingface/hub/datasets--WaterWang-001--CodeFlowBench-2505/` | CodeFlowBench-2505 source raw dataset (690 MB) | ❌ **不用** — 只有"重新生成 818 split"时需要拉 |

---

## 还需要生成 (server 端跑)

| 缺什么 | 怎么生成 | 时间 | 成本 |
|--------|---------|------|------|
| `active_faults_per_turn` 字段 (Full + Hard) | `python -m src.core.active_fault_labeler --workers 8` × 2 splits | ~7 min CPU | $0 |
| `out/checkpoints/{model}_{split}_seed{n}.jsonl` × 32 | server 端按 EXPERIMENT_PLAN §4 跑 8 model × (Full 1-seed + Hard 3-seed) | 12-15 h H100 + ~6 h API | **$517 + $181 buffer = $698** |
| `out/*_records.jsonl` per model | runner 跑完后自动产出 | 免费副产 | $0 |

---

## 在 paper 里的精确引用清单

| paper 位置 | 用到哪条 data | 怎么用 |
|-----------|--------------|--------|
| Abstract | tracebench_full + hard 的 818 / 128 / 2402 / 7165 数字 | 直接引用 |
| §1 Intro 第 4 段 | 同上 | 直接引用 |
| §2 Why a new dataset (Table 2 benchmark matrix) | — | 仅文献对照，不引数据 |
| §3 Protocol and Metrics | tracebench_*.json 的 conversation_history schema 描述 | 用 1 例 `{trace_id, conversation_history[i].{...}}` 作 schema example |
| §4 Dataset Pipeline (Table 4 splits) | manifest_*.json 派生数 + audit_report_v3.json | "all 128 Hard tasks pass structural validity" 引 audit |
| **§5.1 Finding 1 (Table 5)** | **server 跑出的 8 model × 2 split** | 主表 |
| §5.2 Finding 2 (Table 6 + Fig 1 left) | manifest 切片 + 主表 sliced | difficulty_slicer 输出 |
| §5.3 Finding 3 (Table 9 fault family) | fault_families 重算 tracebench_full | 直接引 `out/table_fault_family.md` |
| §5.3 Finding 3 (Fig 1 right scatter) | 主表 per-edit (Outside-G, RegressionRate) | make_figures.py 出图 |
| **§5.4 Finding 4 (Box 1 condensed case)** | **`reference_trajectories/qwen3_32b_trace/tb_hard_00012__dNBGcsy.json` 或 `tb_hard_00000__eLkediY.json`** | 引用具体 turn 序列说明 mis-loc→diffusion→regression |
| §5.4 Finding 4 (Table 11 early drift) | 主表 stratified by first-blame hit/miss | drift_stratifier 输出 |
| §5.4 Finding 4 (Table 12 taxonomy frequency) | 主表 classified by 5-mode | failure_modes.classify_all 输出 |
| §6 Release | tracebench_*.json + oracle_spans + manifests | 列入 release manifest |
| Appendix A (Dataset card) | tracebench_full schema | 完整字段说明 |
| Appendix F (case studies) | `reference_trajectories/{tb_hard_00000, tb_hard_00012}` + 主表里 mining 出的 1-2 例 | 3 个完整 case |

---

## TL;DR — 一张图说完

```
                          USED                          NOT USED
                       ────────────                  ────────────
                                                         
data/tracebench_full.json       ✓ everywhere      
data/tracebench_hard.json       ✓ everywhere      
data/oracle_spans.json          ✓ Hard Outside-G  
data/splits/manifest_*.json     ✓ band slice      
data/reference_trajectories/    ✓ §5.4 case study only (NOT main table)
                                                         
NeurIPS case_studies/ (2 file)  ✓ Box 1 + Appendix F
NeurIPS audit_report_v3         ✓ §4 sanity claim
NeurIPS gold128_trace_aggregate ⚠️ optional reference number
                                                  
                                                   NeurIPS tracebench_cli_gold128/ (docker form)
                                                   NeurIPS compute_matched_smoke (n=10, 全 0)
                                                   ICML build_tracebench.py (备用，未启用)
                                                   HF CodeFlowBench-2505 (重建源，未启用)
                                                  
Still to GENERATE:
  active_faults_per_turn field   ← 7 min CPU,  $0
  Main 24-cell trajectory matrix ← 12-15 h H100 + ~6 h API, $700
```

**净结论**: 已有 data 95% 直接复用，**没有需要重新构造的核心 dataset**。还差 1 次本地 CPU 派生 (7 分钟) + 1 轮 server 端模型评估 (2 天 + $700)。
