# `code/deprecated/` — DO NOT USE IN RELEASE

Files here are kept only for reference / historical reasons.
**They must NOT be linked from the paper, the camera-ready release, or any reproducibility instructions.**

## `baseline_runner.py`

A toy "baseline" runner that simulates a debugging session using `random.random()`:

```python
if mode == "error_aware":
    success_rate = 0.7 if injected_errors else 0.3
else:
    success_rate = 0.3
turn_solved = random.random() < success_rate
```

It does **not** call any LLM and is unsuitable for any quantitative claim.
Originally provided as a smoke fixture; superseded by `code/tracebench_runner.py` and `code/multi_model_runner.py`.

## `tracebench_main_figures.py`

Generates Figure 1 / 2 / 3 mockups for the paper layout. Every data series
is **hard-coded SIMULATED DATA**, explicitly marked `===== SIMULATED DATA =====`
in the file. Keeping it here only for the figure layout (color choices, panel
arrangement) so the actual analysis script can match the visual design.

Do **not** ship `fig1_dynamics.pdf`, `fig2_scaling_poison.pdf`, or
`fig3_gap_ablation.pdf` produced by this file. Regenerate from real data
in `code/scripts/` (see `CODE_GAPS.md` for the missing analysis script).
