# `code/scripts/`

Pipeline scripts. Two families:

## A. Dataset construction (rebuild the 818 / 128 splits from source)

You only need these if you want to **regenerate** the dataset.
For evaluation users, just use `data/tracebench_full.json` and `data/tracebench_hard.json`.

| Script | Role |
|--------|------|
| `download_codeflow.py`            | Pull CodeFlowBench-2505 from HuggingFace (`WaterWang-001/CodeFlowBench-2505`). |
| `import_codeflowbench.py`         | Convert raw CodeFlowBench JSON into the internal problem format. |
| `build_tracebench.py`             | The actual TraceBench generator. Consumes verified programs, injects AST faults, validates, writes JSON. Together-API based. |
| `build_with_together.sh`          | One-shot wrapper around `build_tracebench.py` for a Together API run. |
| `example_complete_workflow.py`    | Reference end-to-end pipeline tying the three above. |
| `run_pipeline.sh`                 | Bash pipeline: filter → generate solutions → validate → inject. Wraps `build_tracebench.py`. |
| `filter_by_depth.py`              | Filter problems by call-graph depth. |
| `filter_depth4plus.py`            | (legacy) Filter to depth ≥ 4. Superseded by `filter_by_depth.py`. |
| `filter_solved.py`                | Keep only problems that the seed model solves (so injection has something to break). |
| `quality_filter.py`               | Additional quality gates (e.g., reject trivial tests). |
| `procedure.md`                    | Step-by-step procedure notes. |

## B. Evaluation

Use the top-level entries instead — these live one directory up:

| Entry | Role |
|-------|------|
| `../evaluate.py`             | Main CLI: run a debug session on TraceBench JSON, compute Blame@K + CF-Valid@1 + patch locality. |
| `../tracebench_runner.py`    | Multi-turn debug session implementation (calls Together-compatible API). |
| `../multi_model_runner.py`   | Same as above but with provider switching (Together / Anthropic / OpenAI). |
| `../harness.py`              | Sandbox test execution. |
| `../generate_solutions.py`   | (used during dataset build) Generate seed model solutions. |

## C. Pipeline dependency map

```
                 HF dataset (WaterWang-001/CodeFlowBench-2505)
                                 │
                                 ▼
                       download_codeflow.py
                                 │
                                 ▼
                    import_codeflowbench.py
                                 │
                                 ▼  (verified problems)
                       filter_by_depth.py
                                 │
                                 ▼
                       filter_solved.py
                                 │
                                 ▼
                   build_tracebench.py  ←─ uses tbgen/ module
                                 │
                                 ▼
                   data/tracebench_{full,hard}.json
```

> Note: the bash pipeline `run_pipeline.sh` historically referred to a
> top-level `generate_tracebench.py`. That file does **not** exist in this
> repo — use `scripts/build_tracebench.py` instead. See the comment block
> at the top of `run_pipeline.sh` for the updated call.
