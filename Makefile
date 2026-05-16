# =====================================================================
#  TraceBench-Full — thin wrapper over pipeline.yaml
#  Targets correspond 1:1 to stages in pipeline.yaml.
# =====================================================================

PY        ?= python3
PYTHONPATH:= code/src
CFG       ?= pipeline.yaml
WORK      := out

export PYTHONPATH

# ---------------------------------------------------------------------
# Top-level meta targets
# ---------------------------------------------------------------------
.PHONY: help estimate verify-env install install-eval install-build clean \
        test smoke \
        label dry-run eval analyze figures tex check paper all

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

estimate: ## Print cost/wall-clock roll-up from pipeline.yaml
	@$(PY) code/scripts/util_estimate_budget.py --config $(CFG)

verify-env: ## Run pre-flight invariants (subset, python, files, env)
	@$(PY) code/scripts/util_verify_env.py --config $(CFG)

install-eval: ## Install eval-only deps (fits on a no-GPU box, no vllm)
	pip install -r code/requirements-eval.txt

install-build: ## Install heavy deps (vllm, torch) for dataset regen
	pip install -r code/requirements-build.txt

install: install-eval ## Alias for install-eval

test: ## Run pytest
	pytest code/tests/ -v

smoke: ## End-to-end smoke (no LLM, mock runner)
	$(PY) code/scripts/smoke_pipeline.py --limit 5 --output $(WORK)/smoke.json

clean: ## Remove all generated artifacts (keeps data/ + checkpoints)
	rm -rf code/paper/figures/fig_macro_outcome.pdf \
	       code/paper/figures/fig_micro_*.pdf \
	       code/paper/numbers.tex \
	       code/paper/tables/*.tex \
	       $(WORK)/analysis $(WORK)/tables $(WORK)/figures
	@echo "Kept: data/, out/checkpoints/, out/records/, out/dry_run/"

# ---------------------------------------------------------------------
# Stage targets (1:1 with pipeline.yaml `stages:`)
# ---------------------------------------------------------------------
label: ## Stage 0: active-fault labeling (Full + Hard)
	$(PY) code/scripts/01_label_active_faults.py \
	    --input data/tracebench_full.json \
	    --output data/derived/tracebench_full_labeled.json --workers 8
	$(PY) code/scripts/01_label_active_faults.py \
	    --input data/tracebench_hard.json \
	    --output data/derived/tracebench_hard_labeled.json --workers 8

dry-run: ## Stage 1: Day-0 30-task calibration across 6 models
	$(PY) code/scripts/00_dry_run_calibration.py \
	    --config $(CFG) --output-dir $(WORK)/dry_run/

eval: ## Stage 2: 6-model × Full main run (resumable)
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model qwen3_5_27b      --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model qwen3_6_27b      --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model qwen3_6_35b_a3b  --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model glm_47_flash     --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model deepseek_r1_32b  --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model gemini_31_pro    --split full

eval-local: ## Stage 2 (local subset only — no API)
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model qwen3_5_27b      --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model qwen3_6_27b      --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model qwen3_6_35b_a3b  --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model glm_47_flash     --split full
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model deepseek_r1_32b  --split full

eval-api: ## Stage 2 (API only — Gemini)
	$(PY) code/scripts/02_run_evaluation.py --config $(CFG) --model gemini_31_pro    --split full

analyze: ## Stage 3: produce 8 CSV tables + numbers.json from records
	$(PY) code/scripts/03_analyze.py --config $(CFG) \
	    --records-dir $(WORK)/records/ \
	    --labeled-full data/derived/tracebench_full_labeled.json \
	    --labeled-hard data/derived/tracebench_hard_labeled.json \
	    --output-dir $(WORK)/

figures: analyze ## Stage 4: generate the 3 multi-panel PDFs
	$(PY) code/scripts/04_make_figures.py --config $(CFG) \
	    --analysis-dir $(WORK)/ --output-dir code/paper/figures/

tex: analyze ## Stage 5: render numbers.tex and table .tex includes
	$(PY) code/scripts/05_render_tex.py --config $(CFG) \
	    --analysis-dir $(WORK)/ --paper-dir code/paper/

check: tex figures ## Stage 6: hard-fail consistency guardrail
	$(PY) code/scripts/06_consistency_check.py --config $(CFG) --strict

paper: check ## Stage 7: compile main.pdf
	cd code/paper && pdflatex -interaction=nonstopmode main.tex
	cd code/paper && bibtex main || true
	cd code/paper && pdflatex -interaction=nonstopmode main.tex
	cd code/paper && pdflatex -interaction=nonstopmode main.tex
	@echo ""
	@echo "==>  code/paper/main.pdf"

# ---------------------------------------------------------------------
# Master target — full pipeline from scratch
# ---------------------------------------------------------------------
all: verify-env label dry-run eval analyze figures tex check paper ## Run the entire pipeline
	@echo ""
	@echo "==> SUCCESS"
	@echo "    Paper: code/paper/main.pdf"
	@echo "    Tables: out/tables/*.csv"
	@echo "    Numbers: out/analysis/numbers.json"
	@echo ""

# ---------------------------------------------------------------------
# Mock-only target — useful for paper-formatting iteration without runs
# ---------------------------------------------------------------------
mock-paper: ## Render paper with MOCK data (skip eval+analyze)
	$(PY) code/scripts/generate_mock_results.py --output-dir code/mock_results/
	$(PY) code/scripts/04_make_figures.py --analysis-dir code/mock_results/ \
	    --output-dir code/paper/figures/ --mock
	$(PY) code/scripts/05_render_tex.py --analysis-dir code/mock_results/ \
	    --paper-dir code/paper/ --mock
	cd code/paper && pdflatex -interaction=nonstopmode main.tex > /dev/null
	cd code/paper && bibtex main || true
	cd code/paper && pdflatex -interaction=nonstopmode main.tex > /dev/null
	cd code/paper && pdflatex -interaction=nonstopmode main.tex > /dev/null
	@echo ""
	@echo "==> MOCK paper compiled: code/paper/main.pdf"
	@echo "    (contains placeholder numbers in red italics)"

.DEFAULT_GOAL := help
