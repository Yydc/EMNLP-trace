#!/usr/bin/env python3
"""End-to-end smoke test: load real Hard split, run a stub runner, compute
all metrics, dump per-problem records.

This does NOT call any LLM API. It uses a deterministic stub runner that
returns the corrupted code unchanged (so every problem 'fails'). The point
is to verify the full plumbing — runner → metrics_v2 → aggregator → slicer
→ drift → failure mode → figure JSON — works against the real dataset.

Usage::

    python scripts/smoke_pipeline.py --limit 5 --output out/smoke.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


def stub_run_debug_session(
    entry: Dict[str, Any],
    mode: str = "baseline",
    enable_adaptive_decoding: bool = False,
    max_turns: int = 5,
) -> Dict[str, Any]:
    """A stub runner that pretends to attempt each turn but always fails.

    Emits the same shape as ``tracebench_runner.run_debug_session`` so the
    aggregator and metrics can ingest it.
    """
    convo = entry.get("conversation_history", []) or []
    turn_results = []
    total_attempts = 0
    for t_idx, turn in enumerate(convo):
        tid = turn.get("turn_id", t_idx)
        has_error = turn.get("has_error", False)
        target = turn.get("target_code", "") or ""
        original = turn.get("original_target_code", target) or target
        tests = turn.get("test_cases", []) or []

        attempts = []
        if has_error:
            # Pretend we attempted but produced unchanged corrupted code.
            # This exercises the metrics pipeline (edited_lines empty,
            # per_test_results filled by the harness, etc.).
            total_attempts += 1
            attempts.append({
                "attempt_number": total_attempts,
                "turn": tid,
                "attempt_in_turn": 0,
                "mode": mode,
                "temperature": 0.0,
                "blame_spans": [{
                    "file_path": "solution.py", "start_line": 1, "end_line": 5, "score": 1.0
                }],
                "patch_spans": [],
                "code_before": target,
                "generated_code": target,  # unchanged ⇒ trivial regression rate
                "edited_lines": [],
                "per_test_results": {i: False for i in range(len(tests))},
                "success": False,
                "test_result": "stub: no LLM",
                "raw_response": "",
            })
            # Add a second attempt that "tries" the original to show a
            # nontrivial trajectory.
            total_attempts += 1
            attempts.append({
                "attempt_number": total_attempts,
                "turn": tid,
                "attempt_in_turn": 1,
                "mode": mode,
                "temperature": 0.0,
                "blame_spans": [{
                    "file_path": "solution.py", "start_line": 10, "end_line": 12, "score": 0.8
                }],
                "patch_spans": [{"file_path": "solution.py", "start_line": 1, "end_line": 5}],
                "code_before": target,
                "generated_code": original,  # revert to clean
                "edited_lines": list(range(1, 6)),
                "per_test_results": {i: True for i in range(len(tests))},
                "success": True,
                "test_result": "stub: clean revert",
                "raw_response": "",
            })
        turn_results.append({
            "turn_id": tid,
            "subproblems": turn.get("subproblems", []),
            "has_injected_error": has_error,
            "solved": bool(attempts) and attempts[-1]["success"],
            "attempts": attempts,
        })

    overall = all(t.get("solved") or not t.get("has_injected_error") for t in turn_results)
    return {
        "problem_id": entry.get("trace_id"),
        "mode": mode,
        "enable_adaptive_decoding": enable_adaptive_decoding,
        "solved": overall,
        "first_success_turn": len(turn_results) if overall else None,
        "total_turns": len(turn_results),
        "total_attempts": total_attempts,
        "turn_results": turn_results,
        "dialogue_chain_length": 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="data/tracebench_hard.json")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--output", default="out/smoke.json")
    args = p.parse_args()

    # Resolve dataset relative to project root.
    ds_path = Path(args.dataset)
    if not ds_path.is_absolute():
        ds_path = Path("/Users/apple/Desktop/tracebench") / ds_path
    with ds_path.open() as fin:
        entries = json.load(fin)[: args.limit]
    print(f"loaded {len(entries)} entries from {ds_path}")

    from src.core.tracebench_eval import MetricAggregator
    from src.core.traceability_metrics import TraceabilityMetrics
    from src.evaluation.bootstrap import problem_bootstrap_ci
    from src.evaluation.difficulty_slicer import slice_by_band, render_band_table
    from src.evaluation.drift_stratifier import stratify_problems
    from src.evaluation.failure_modes import classify_all, render_taxonomy_table
    from src.core.metrics_v2 import active_spans_from_entry

    tm = TraceabilityMetrics(k_values=[1, 3, 5])
    agg = MetricAggregator(blame_k=[1, 3, 5], max_turns=5)
    logs_by_id: Dict[str, Dict[str, Any]] = {}

    t0 = time.time()
    for i, entry in enumerate(entries):
        log = stub_run_debug_session(entry)
        metrics = tm.analyze(entry, log, file_path="solution.py")
        agg.add_result(log, metrics)
        logs_by_id[entry["trace_id"]] = log
        print(f"  [{i+1}/{len(entries)}] {entry['trace_id']}  solved={log['solved']}  "
              f"og={metrics.get('outside_g')} rr={metrics.get('regression_rate')} "
              f"slope={metrics.get('trajectory_slope')}")
    elapsed = time.time() - t0
    print(f"smoke run done in {elapsed:.1f}s")

    agg_out = agg.aggregate()
    by_id = {e["trace_id"]: e for e in entries}

    # Difficulty slicing
    band_table = slice_by_band(agg_out["per_problem_records"], by_id)

    # Drift stratifier
    drift = stratify_problems(
        agg_out["per_problem_records"], logs_by_id, by_id,
        active_spans_fn=lambda e: active_spans_from_entry(e, 1),  # turn 1 default
    )

    # Failure-mode classifier
    fm = classify_all(
        agg_out["per_problem_records"], logs_by_id, by_id,
        active_spans_fn=lambda e: active_spans_from_entry(e, 1),
    )

    # Bootstrap CI on Pass@1
    pass_vals = [int(r["solved"]) for r in agg_out["per_problem_records"]]
    pt, lo, hi = problem_bootstrap_ci(pass_vals, n_resamples=500)

    out = {
        "elapsed_sec": elapsed,
        "n_problems": len(entries),
        "aggregate": {
            k: v for k, v in agg_out.items()
            if k != "per_problem_records"  # too big for stdout
        },
        "bootstrap_pass_at_1": {"point": pt, "lo": lo, "hi": hi},
        "difficulty_bands": band_table,
        "drift_stratification": drift,
        "failure_modes": fm,
        "band_table_md": render_band_table(band_table),
        "taxonomy_md": render_taxonomy_table(fm),
    }

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = Path("/Users/apple/Desktop/tracebench") / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fout:
        json.dump(out, fout, indent=2, ensure_ascii=False, default=str)

    # Stdout summary
    print()
    print("=== AGGREGATE ===")
    for k, v in out["aggregate"].items():
        if isinstance(v, dict):
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")
    print()
    print("=== Bootstrap Pass@1 ===")
    print(f"  {pt:.3f}  [{lo:.3f}, {hi:.3f}]")
    print()
    print("=== Failure-mode Taxonomy ===")
    print(out["taxonomy_md"])
    print()
    print(f"wrote full dump → {out_path}")


if __name__ == "__main__":
    main()
