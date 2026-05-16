#!/usr/bin/env python3
"""Stage 4: generate the 3 multi-panel PDFs included by main.tex.

Thin wrapper over `code/scripts/make_figures.py` (the real impl).
Reads from out/analysis + out/tables; writes to code/paper/figures/.

Usage::
    python code/scripts/04_make_figures.py --config pipeline.yaml \\
        --analysis-dir out/ --output-dir code/paper/figures/

Or in mock mode (uses code/mock_results/ as the source):
    python code/scripts/04_make_figures.py --mock \\
        --analysis-dir code/mock_results/ --output-dir code/paper/figures/
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="pipeline.yaml")
    ap.add_argument("--analysis-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--mock", action="store_true",
                    help="Use mock_results bundle/jsonl instead of out/")
    args = ap.parse_args()

    if args.mock:
        bundle  = args.analysis_dir / "mock_bundle.json"
        records = args.analysis_dir / "mock_per_problem_records.jsonl"
    else:
        bundle  = args.analysis_dir / "analysis" / "numbers.json"
        records = args.analysis_dir / "analysis" / "per_edit_scatter.jsonl"

    if not bundle.exists() or not records.exists():
        sys.exit(f"missing analysis inputs:\n  {bundle}\n  {records}\n"
                 "Run `make analyze` first, or pass --mock with code/mock_results/.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "code" / "scripts" / "make_figures.py"),
        "--records", str(records),
        "--bundle", str(bundle),
        "--output-dir", str(args.output_dir),
    ]
    print("$", " ".join(cmd))
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
