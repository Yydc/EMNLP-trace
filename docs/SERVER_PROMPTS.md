# Server-side Claude Code prompts — TraceBench-Full

Two-stage run plan for the H100 box.

| Stage | Wall-clock | Budget | Output |
|-------|-----------:|-------:|--------|
| **0. Setup** | ~10 min | $0 | repo cloned, deps installed, env verified |
| **1. Dry run** | **≤ 1 hour** (hard cap 55 min) | **≤ $5** (Gemini) | `out/dry_run/calibration_report.md` + go/no-go decision |
| **2. Full run** | ~14 h sequential | **≤ $131** (Gemini cell only) | `out/records/*` per cell → `code/paper/main.pdf` |

Both prompts are SELF-CONTAINED — paste them into a fresh `claude` session on the server.

---

## Stage 0 — one-time setup (run this in a shell, not Claude)

```bash
# On the H100 box, in a clean dir:
git clone https://github.com/Yydc/EMNLP-trace.git
cd EMNLP-trace

# Python 3.10+ recommended
python3 -m venv .venv && source .venv/bin/activate

# Light deps (openai, google-generativeai, numpy, pandas, matplotlib, pyyaml)
make install-eval

# Heavy deps (vllm, torch, transformers) — needed for local model serving
make install-build

# API key for the single Gemini cell
export GOOGLE_API_KEY=<your_key>

# Sanity check (no models loaded yet, just env + paths)
make verify-env
make test          # 58 pytest tests, ~30s
```

After this, the repo is ready; launch `claude` in the repo root and paste the Stage 1 prompt.

---

## Stage 1 — Dry-run calibration (≤ 1 hour, ≤ $5)

**Paste this entire block into a fresh `claude` session at the repo root:**

```
You are running TraceBench-Full Stage 1 (dry-run calibration) on this H100 server.
The repo is already cloned; deps + GOOGLE_API_KEY are set; tests pass.

GOAL: Run a 12-task stratified pilot on each of the 6 models, finish within 1 hour
total wall-clock, spend at most $5 on Gemini, and produce a go/no-go report.

CONSTRAINTS — non-negotiable:
- Hard wall-clock cap for the whole stage: 55 minutes (5 min headroom under 1h).
- Hard USD cap on Gemini API: $5.
- If either cap trips mid-run, the BudgetGuard in code/src/core/budget.py
  saves checkpoint and exits non-zero. Do NOT bypass; surface the failure.
- Do not edit any code unless a script is actually broken (read the error first).

EXECUTION PLAN:

1. Pre-flight (parallelize):
   - `make verify-env`        # confirms data files, python ver, env vars
   - `nvidia-smi | head -20`  # confirm H100 visible
   - `echo $GOOGLE_API_KEY | wc -c`  # confirm key present (>30 chars)

2. Launch the calibration. There are two ways the runner can be wired —
   the script auto-detects. Just run:

       make dry-run

   Internally this is:
       python code/scripts/00_dry_run_calibration.py \\
           --config pipeline.yaml \\
           --output-dir out/dry_run/ \\
           --n-per-band 4 \\
           --max-wall-clock-minutes 55 \\
           --max-usd 5.0

   For the 5 LOCAL models, the runner needs `vllm serve <hf_repo>` on
   port 8000 BEFORE that model's calls. If the dry-run is in "mock" mode
   (you'll see `_mock=true` in the JSONL), skip vllm — the calibration
   intentionally falls back to mock when the runner can't import.

   If you want to drive the real runner end-to-end:
   For each local model M in [qwen3_5_27b, qwen3_6_27b, qwen3_6_35b_a3b,
   glm_47_flash, deepseek_r1_32b]:
     a) Read code/configs/models/M.yaml; pull `hf_repo`, `vllm_port`,
        `quantization`, `max_model_len`, `gpu_memory_utilization`.
     b) Launch vllm in background:
          vllm serve <hf_repo> \\
              --port <vllm_port> \\
              --gpu-memory-utilization <gpu_memory_utilization> \\
              --max-model-len <max_model_len> \\
              [--quantization awq if `quantization` says awq]
     c) Wait until `curl localhost:<port>/v1/models` returns 200 (or 90s timeout).
     d) Run the per-model dry-run cell (5–8 min per model).
     e) Kill vllm before the next model — only one fits on an H100 at a time.

   For the API model gemini_31_pro: no vllm; runs immediately.

3. After the dry-run completes (or budget-cuts), read these two files:
   - out/dry_run/calibration_summary.csv     (6 rows, one per model)
   - out/dry_run/calibration_report.md       (human-readable, with gate)

4. Apply the GATE — block Stage 2 if any of:
   - `parse_ok_rate < 0.80` on ANY model (model can't emit JSON blame spans)
   - `projected_full_cost_usd > 250` on Gemini (will blow the $131 cap)
   - `timeout_rate > 0.20` on ANY model
   - The dry-run reports `aborted=true` (budget cut mid-stage)

5. Report back with:
   - The 6-row markdown table from calibration_report.md
   - Verdict: GREEN (all gates pass) / YELLOW (proceed with one note) / RED (stop)
   - If YELLOW or RED, tell me exactly which fix I need to make before Stage 2.

Total turn budget: try to finish in <30 of your own tool calls.
If you hit anything truly blocking (e.g. vllm OOM, GOOGLE_API_KEY rejected,
HF model not found), STOP and surface the exact error — don't paper over it.
```

---

## Stage 2 — Full run (long-form, $131 cap, ~14 h)

**Run this only AFTER Stage 1 returns GREEN. Paste into a fresh `claude` session:**

```
You are running TraceBench-Full Stage 2 (full evaluation) on this H100 server.
Stage 1 (dry-run) already returned GREEN. Now produce the real records that
feed the paper.

GOAL: Run all 6 models on the full 818-problem split, with per-cell budget
caps. Resume from checkpoint if any cell crashes. At the end, build
out/analysis/numbers.json, regenerate figures + numbers.tex, and compile
the final main.pdf with `make check && make paper`.

BUDGET (PER CELL — script enforces via code/src/core/budget.py):
- Local cells: --max-wall-clock-hours 3   (no $ cap, price is $0)
- Gemini cell: --max-usd 131 --max-wall-clock-hours 6

Total expected: ~12 H100-hours + ~$97 on Gemini (the $131 cap leaves 35% slack).
If the Gemini cell hits $131, the script writes checkpoint and exits with code 2.
DO NOT silently retry past the cap — surface it to me.

EXECUTION:

For each of the 6 cells, run sequentially:

  ----- LOCAL CELL: <model_id> -----
  1. Read code/configs/models/<model_id>.yaml; pull hf_repo, vllm_port,
     gpu_memory_utilization, max_model_len, quantization.
  2. Start vllm in background:
       vllm serve <hf_repo> \\
           --port <vllm_port> \\
           --gpu-memory-utilization <gpu_memory_utilization> \\
           --max-model-len <max_model_len> \\
           [--quantization awq if applicable]
     Log to /tmp/vllm_<model_id>.log.
  3. Wait up to 180s for `curl http://localhost:<vllm_port>/v1/models` → 200.
     If it never comes up: tail the log, surface the error, STOP.
  4. Run the cell with a HARD wall-clock cap:
       python code/scripts/02_run_evaluation.py \\
           --config pipeline.yaml \\
           --model <model_id> \\
           --split full \\
           --max-wall-clock-hours 3
     Run this in foreground (it prints rate + ETA every 25 problems).
  5. When the script returns:
       - Exit 0: success. Verify out/records/<model_id>_full_records.jsonl
         has ~818 lines (`wc -l`).
       - Exit 2: budget cut. Read out/records/<model_id>_full_summary.json
         for the abort reason; report to me and ask whether to bump the
         cap and `make eval-local MODEL=<model_id>` to resume.
       - Other non-zero: crash. Tail stderr, surface the error, STOP.
  6. Kill vllm: `pkill -f "vllm serve <hf_repo>"` (verify with `nvidia-smi`).

  ----- API CELL: gemini_31_pro -----
  Same as above but skip vllm setup. Use:
       python code/scripts/02_run_evaluation.py \\
           --config pipeline.yaml \\
           --model gemini_31_pro \\
           --split full \\
           --max-usd 131 \\
           --max-wall-clock-hours 6

CELL ORDER (smallest → largest local, then API last):
  1. qwen3_6_35b_a3b   (1.4 H100-h estimated — A3B activation)
  2. glm_47_flash      (1.7 H100-h)
  3. qwen3_6_27b       (2.0 H100-h)
  4. qwen3_5_27b       (2.1 H100-h)
  5. deepseek_r1_32b   (2.5 H100-h)
  6. gemini_31_pro     (API, parallelizable — could overlap with the
                        later local cells if you want, but sequential is
                        simpler and only ~2h extra wall-clock)

RESUME SEMANTICS: each cell writes
  out/checkpoints/<model>_full.jsonl  (one line per completed problem_id)
The runner skips problem_ids already in the checkpoint. So if cell 4 dies
at problem 600, re-running the same command resumes from 601 automatically.

AFTER ALL 6 CELLS GREEN — build the paper:

  make analyze    # produces out/analysis/numbers.json + 8 CSV tables
  make figures    # writes code/paper/figures/*.pdf (3 multi-panel)
  make tex        # rewrites code/paper/numbers.tex (replaces \\mockval{} with real values)
  make check      # HARD GATE: verifies main.tex \\input's numbers.tex,
                  # every macro is defined, no \\todo/TBD/mock strings,
                  # row counts match, Hard ⊂ Full re-verified
  make paper      # compiles code/paper/main.pdf

If `make check` fails: surface the exact assertion + the offending line in
main.tex. Do NOT try to silence the check by editing main.tex — fix the
upstream data/script that produced the wrong number.

FINAL REPORT TO ME:
  - Per-cell summary table: model | n_done/818 | wall_clock | $ spent | aborted?
  - The path to main.pdf
  - The contents of out/analysis/numbers.json (it's small, paste it)
  - Any cell that aborted or any check that failed, with the exact error

DO NOT push to GitHub from the server. I'll review main.pdf and the records
locally first, then push from my laptop.
```

---

## What changed since the planning docs

- `BudgetGuard` is now wired into BOTH stages (Stage 1 at script level over
  all 6 models; Stage 2 per-cell via `--max-usd` / `--max-wall-clock-hours`).
- Cell ordering in the Stage 2 prompt puts smallest local models first so
  any infrastructure problem surfaces fast (15-min cycles instead of 3h).
- The `make check` gate is non-bypassable — main.pdf will not build if any
  paper number lacks a `numbers.tex` definition. This is the consistency
  guardrail GPT requested.

## Resume cheat sheet

| Situation | Action |
|-----------|--------|
| Cell crashed mid-run | Same `python scripts/02_run_evaluation.py …` command resumes from `out/checkpoints/` |
| Budget cut mid-cell | Read summary JSON, bump `--max-usd` or `--max-wall-clock-hours`, re-run same command |
| Need to retry one model only | `python scripts/02_run_evaluation.py --model <id> --split full` (others untouched) |
| Want a fresh start | `rm out/checkpoints/<model>_full.jsonl out/records/<model>_full*` |
| Want to skip Gemini entirely | `make eval-local` (omits the API cell) |
