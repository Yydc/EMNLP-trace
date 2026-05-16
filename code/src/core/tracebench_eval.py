from __future__ import annotations

import json
import sys
from pathlib import Path
import os
from statistics import mean
from typing import Any, Callable, Dict, List, Optional

from .traceability_metrics import TraceabilityMetrics

# Buckets used for pass@K-style turn reporting
PASS_AT_TURN_BUCKETS = [1, 3, 5]


class MetricAggregator:
    """Accumulates per-problem metrics and produces dataset-level aggregates."""

    def __init__(self, blame_k: List[int], turn_buckets: Optional[List[int]] = None, max_turns: int = 5) -> None:
        self.blame_k = sorted(set(blame_k))
        self.turn_buckets = turn_buckets or PASS_AT_TURN_BUCKETS
        self.max_turns = max(1, max_turns)
        self.total_problems = 0
        self.successful = 0
        self.pass_counts = {k: 0 for k in self.turn_buckets}
        self.blame_counts = {k: 0 for k in self.blame_k}
        self.patch_min_distances: List[float] = []
        self.patch_mean_distances: List[float] = []
        self.patch_mean_ious: List[float] = []
        self.patch_line_counts: List[float] = []
        self.patch_hits: List[int] = []
        self.precision_at_1: List[float] = []
        self.cf_valid_at_1: List[float] = []
        self.success_by_turn: List[int] = [0 for _ in range(self.max_turns)]
        # New paper-aligned aggregators (metrics_v2)
        self.outside_g_values: List[float] = []
        self.regression_rate_values: List[float] = []
        self.trajectory_slopes: List[float] = []
        self.trajectory_r2s: List[float] = []
        self.repeats_per_problem: List[int] = []
        self.twe_per_problem: List[int] = []
        # Per-problem records for downstream bootstrap CI / slicing
        self.per_problem: List[Dict[str, Any]] = []

    def add_result(self, problem_log: Dict[str, Any], trace_metrics: Dict[str, Any]) -> None:
        """Safely ingest a single problem's results."""
        self.total_problems += 1

        if problem_log.get("solved"):
            self.successful += 1

        # Multi-turn format uses total_attempts instead of first_success_turn
        first_success_turn = problem_log.get("first_success_turn")
        total_attempts = problem_log.get("total_attempts")

        # For pass_at_turn: use total_attempts if available (multi-turn), else first_success_turn
        attempts_metric = total_attempts if total_attempts is not None else first_success_turn

        if isinstance(attempts_metric, int) and attempts_metric > 0:
            for bucket in self.turn_buckets:
                if attempts_metric <= bucket:
                    self.pass_counts[bucket] += 1
            # For pass_rate_by_turn, use actual turn count
            turn_count = first_success_turn if isinstance(first_success_turn, int) else attempts_metric
            for t in range(min(turn_count, self.max_turns), self.max_turns + 1):
                self.success_by_turn[t - 1] += 1

        blame_at_k = (trace_metrics or {}).get("blame_at_k") or {}
        for k in self.blame_k:
            hit = blame_at_k.get(k)
            if hit == 1 or hit is True:
                self.blame_counts[k] += 1

        patch_locality = (trace_metrics or {}).get("patch_locality") or {}
        self._maybe_append(self.patch_min_distances, patch_locality.get("min_distance"))
        self._maybe_append(self.patch_mean_distances, patch_locality.get("mean_distance"))
        self._maybe_append(self.patch_mean_ious, patch_locality.get("mean_iou"))
        self._maybe_append(self.patch_line_counts, patch_locality.get("line_count_mean"))
        hit = patch_locality.get("hit_anchor")
        if isinstance(hit, bool):
            self.patch_hits.append(int(hit))

        self._maybe_append(self.precision_at_1, (trace_metrics or {}).get("precision_at_1"))
        self._maybe_append(self.cf_valid_at_1, (trace_metrics or {}).get("cf_valid_at_1"))

        # metrics_v2 aggregation
        tm = trace_metrics or {}
        self._maybe_append(self.outside_g_values, tm.get("outside_g"))
        self._maybe_append(self.regression_rate_values, tm.get("regression_rate"))
        self._maybe_append(self.trajectory_slopes, tm.get("trajectory_slope"))
        self._maybe_append(self.trajectory_r2s, tm.get("trajectory_r2"))
        if isinstance(tm.get("repeats"), int):
            self.repeats_per_problem.append(tm["repeats"])
        if isinstance(tm.get("test_without_edit"), int):
            self.twe_per_problem.append(tm["test_without_edit"])

        # Keep a slim per-problem record for downstream bootstrap CI / slicing.
        self.per_problem.append({
            "solved": bool(problem_log.get("solved")),
            "first_success_turn": problem_log.get("first_success_turn"),
            "blame_at_1": int(blame_at_k.get(1) == 1 or blame_at_k.get(1) is True),
            "outside_g": tm.get("outside_g"),
            "regression_rate": tm.get("regression_rate"),
            "trajectory_slope": tm.get("trajectory_slope"),
            "repeats": tm.get("repeats"),
            "test_without_edit": tm.get("test_without_edit"),
            "trace_id": problem_log.get("problem_id") or problem_log.get("trace_id"),
        })

    def aggregate(self) -> Dict[str, Any]:
        total = self.total_problems
        success_rate = (self.successful / total) if total else 0.0

        pass_at_turn = {k: (self.pass_counts.get(k, 0) / total) if total else 0.0 for k in self.turn_buckets}
        blame_at_k = {k: (self.blame_counts.get(k, 0) / total) if total else 0.0 for k in self.blame_k}

        patch_locality = {
            "min_distance_mean": mean(self.patch_min_distances) if self.patch_min_distances else None,
            "mean_distance": mean(self.patch_mean_distances) if self.patch_mean_distances else None,
            "mean_iou": mean(self.patch_mean_ious) if self.patch_mean_ious else None,
            "line_count_mean": mean(self.patch_line_counts) if self.patch_line_counts else None,
        }
        anchor_hit_rate = (mean(self.patch_hits) if self.patch_hits else None)

        pass_rate_by_turn = [(cnt / total) if total else 0.0 for cnt in self.success_by_turn]
        pass_slope, pass_r2 = self._linear_fit(pass_rate_by_turn)

        return {
            "success_rate": success_rate,
            "pass_at_turn": pass_at_turn,
            "blame_at_k": blame_at_k,
            "patch_locality": patch_locality,
            "anchor_hit_rate": anchor_hit_rate,
            "precision_at_1": mean(self.precision_at_1) if self.precision_at_1 else None,
            "cf_valid_at_1": mean(self.cf_valid_at_1) if self.cf_valid_at_1 else None,
            "pass_rate_by_turn": pass_rate_by_turn,
            "pass_slope": pass_slope,
            "pass_r2": pass_r2,
            # metrics_v2 aggregates
            "outside_g": mean(self.outside_g_values) if self.outside_g_values else None,
            "regression_rate": mean(self.regression_rate_values) if self.regression_rate_values else None,
            "trajectory_slope_mean": mean(self.trajectory_slopes) if self.trajectory_slopes else None,
            "trajectory_r2_mean": mean(self.trajectory_r2s) if self.trajectory_r2s else None,
            "repeats_mean": mean(self.repeats_per_problem) if self.repeats_per_problem else None,
            "test_without_edit_mean": mean(self.twe_per_problem) if self.twe_per_problem else None,
            # Per-problem records for downstream slicing / bootstrap
            "per_problem_records": self.per_problem,
        }

    @staticmethod
    def _maybe_append(container: List[float], value: Optional[float]) -> None:
        if value is None:
            return
        try:
            container.append(float(value))
        except (TypeError, ValueError):
            # Skip malformed numeric values without failing the evaluation
            return

    @staticmethod
    def _linear_fit(y_values: List[float]) -> tuple:
        """Compute slope and R^2 for y over turns (1..T)."""
        n = len(y_values)
        if n == 0:
            return 0.0, None
        xs = list(range(1, n + 1))
        mean_x = sum(xs) / n
        mean_y = sum(y_values) / n

        var_x = sum((x - mean_x) ** 2 for x in xs)
        cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, y_values))
        slope = cov_xy / var_x if var_x != 0 else 0.0
        intercept = mean_y - slope * mean_x

        y_pred = [slope * x + intercept for x in xs]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(y_values, y_pred))
        ss_tot = sum((y - mean_y) ** 2 for y in y_values)
        if ss_tot == 0:
            r2 = 1.0
        else:
            r2 = 1 - ss_res / ss_tot
        return slope, r2


def _load_checkpoint(path: Path) -> Dict[tuple, Dict[str, Any]]:
    if not path.exists():
        return {}
    records: Dict[tuple, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Use config_name for 4-config system, fallback to mode for old checkpoints
                config = obj.get("config_name") or obj.get("mode")
                trace_id = obj.get("trace_id")
                if config and trace_id:
                    key = (config, trace_id)
                    records[key] = obj
            except Exception:
                continue
    return records


def _append_checkpoint(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fout:
        fout.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_tracebench_eval(
    tracebench_path: str,
    run_debug_session: Callable[..., Dict[str, Any]],
    max_turns: int = 5,
    blame_k: Optional[List[int]] = None,
    checkpoint_path: Optional[str] = None,
    detailed_output_dir: Optional[str] = None,
    force_llm_on_raw: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate baseline vs error-aware debugging loops on TraceBench.

    Args:
        tracebench_path: Path to the TraceBench JSON file (list of entries).
        run_debug_session: Callable that executes the multi-turn debugging loop.
        max_turns: Maximum turns per problem for the debugging loop.
        blame_k: Optional list of k values for blame@k; defaults to [1, 3, 5].
        checkpoint_path: Optional path to checkpoint file for resuming runs.
        detailed_output_dir: Optional directory to save detailed per-problem results.
    """
    tracebench_file = Path(tracebench_path)
    with tracebench_file.open("r", encoding="utf-8") as fin:
        data = json.load(fin)
    if not isinstance(data, list):
        raise ValueError("TraceBench file must contain a list of entries.")

    if force_llm_on_raw:
        # Copy entries and blank out corrupted_code to force LLM generation.
        patched = []
        for entry in data:
            try:
                entry = dict(entry)
                code_ctx = dict(entry.get("code_context") or {})
                code_ctx["corrupted_code"] = ""
                entry["code_context"] = code_ctx
            except Exception:
                pass
            patched.append(entry)
        data = patched

    blame_values = blame_k or [1, 3, 5]
    tm = TraceabilityMetrics(k_values=blame_values)

    ckpt_file = Path(checkpoint_path) if checkpoint_path else None
    checkpoint = _load_checkpoint(ckpt_file) if ckpt_file else {}

    detailed_dir = Path(detailed_output_dir) if detailed_output_dir else None
    if detailed_dir:
        detailed_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {}
    problem_results: Dict[str, List[Dict[str, Any]]] = {}

    # 2 种模式：Vanilla（固定参数）vs Strategy（自适应参数）
    modes = [
        ("baseline", False),      # Vanilla - 固定参数
        ("error_aware", True),    # Strategy - 自适应参数
    ]

    for mode, enable_adaptive in modes:
        aggregator = MetricAggregator(blame_k=blame_values, turn_buckets=PASS_AT_TURN_BUCKETS, max_turns=max_turns)
        problem_results[mode] = []

        print(f"\n{'='*80}", file=sys.stderr)
        print(f"Running mode: {mode}", file=sys.stderr)
        print(f"  - Decoding: {'Adaptive Strategy' if enable_adaptive else 'Vanilla (fixed)'}", file=sys.stderr)
        print(f"{'='*80}\n", file=sys.stderr)

        for idx, entry in enumerate(data, 1):
            trace_id = entry.get("trace_id") or entry.get("original_source_id") or "unknown"
            key = (mode, trace_id)

            resumed = False
            if key in checkpoint:
                cached = checkpoint[key]
                problem_log = cached.get("problem_log", {})
                trace_metrics = cached.get("trace_metrics", {})
                resumed = True
            else:
                problem_log = run_debug_session(
                    entry,
                    mode=mode,
                    enable_adaptive_decoding=enable_adaptive,
                    max_turns=max_turns
                )
                # Multi-turn entries often lack code_context.file_path; default to a stable name
                file_path = (
                    entry.get("code_context", {}).get("file_path")
                    or entry.get("file_path")
                    or "solution.py"
                )
                trace_metrics = tm.analyze(
                    tracebench_entry=entry,
                    problem_log=problem_log,
                    file_path=file_path,
                )

                if ckpt_file:
                    record = {
                        "mode": mode,
                        "enable_adaptive_decoding": enable_adaptive,
                        "trace_id": trace_id,
                        "entry": entry,  # 保存完整 entry 以便后续重新计算 metrics
                        "problem_log": problem_log,
                        "trace_metrics": trace_metrics,
                    }
                    _append_checkpoint(ckpt_file, record)

            solved = problem_log.get("solved", False)
            first_turn = problem_log.get("first_success_turn")
            status = "PASS" if solved else "FAIL"
            resume_tag = " (resumed)" if resumed else ""

            print(f"[{mode}] {idx}/{len(data)} {trace_id}: {status} (turn={first_turn}){resume_tag}", flush=True, file=sys.stderr)

            aggregator.add_result(problem_log, trace_metrics)

            problem_summary = {
                "trace_id": trace_id,
                "problem_index": idx,
                "solved": solved,
                "first_success_turn": first_turn,
                "total_turns": problem_log.get("total_turns"),
                "trace_metrics": trace_metrics,
            }
            problem_results[mode].append(problem_summary)

            # 每 10 个问题输出一次总结
            if idx % 10 == 0:
                current_results = problem_results[mode]
                solved_count = sum(1 for r in current_results if r.get("solved", False))
                pass_rate = solved_count / len(current_results) * 100 if current_results else 0
                avg_turn = sum(r.get("first_success_turn", 0) or 0 for r in current_results if r.get("solved")) / max(solved_count, 1)
                print(f"  ► Progress: {idx}/{len(data)} | Solved: {solved_count}/{len(current_results)} ({pass_rate:.1f}%) | Avg turn: {avg_turn:.2f}", flush=True, file=sys.stderr)

            if detailed_dir and not resumed:
                detail_file = detailed_dir / f"{mode}_{trace_id}.json"
                detail_data = {
                    "trace_id": trace_id,
                    "mode": mode,
                    "enable_adaptive_decoding": enable_adaptive,
                    "entry": entry,
                    "problem_log": problem_log,
                    "trace_metrics": trace_metrics,
                }
                with detail_file.open("w", encoding="utf-8") as fout:
                    json.dump(detail_data, fout, indent=2, ensure_ascii=False)

        results[mode] = aggregator.aggregate()

    results["per_problem_results"] = problem_results
    return results
