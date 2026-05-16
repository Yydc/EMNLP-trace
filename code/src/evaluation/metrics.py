"""Metric aggregation for the CodeFlow evaluation pipeline.

The tracker is designed around the metric taxonomy discussed with the user:

    A. Correctness & Efficiency
    B. Traceability
    C. Error Accumulation & Recovery
    D. Distribution Shift Robustness
    E. Strong Verification / Collapse analysis

The implementation is intentionally tolerant to partially-populated logs – if a
datum is missing we simply skip it instead of failing the whole evaluation.
"""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from src.core import config


class MetricsTracker:
    """Accumulates per-problem logs and produces aggregated metrics."""

    def __init__(self) -> None:
        self.reset()

    # ------------------------------------------------------------------
    # state helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.metrics: Dict[str, Any] = {
            "correctness": {
                "pass_at_turn": {k: 0 for k in config.PASS_AT_TURN_BUCKETS},
                "first_success_turns": [],
                "total_problems": 0,
                "successful_problems": 0,
                "first_success_turn_list": [],
                "first_success_turn_problem_ids": [],
                "patch_diff_hunks": [],
                "patch_lines_changed": [],
            },
            "traceability": {
                "evidence_hits": [],
                "replay_consistency": [],
                "routing_cost": [],
                "audit_trails_missing": 0,
            },
            "error_accumulation": {
                "failure_streaks": [],
                "recovery_by_streak": defaultdict(list),
                "rollback_triggers": 0,
                "rollback_success": 0,
            },
            "distribution_shift": {
                "temporal": defaultdict(list),
                "api": defaultdict(list),
                "structure": defaultdict(list),
                "boundary": defaultdict(list),
                "turn_buckets": defaultdict(list),
            },
            "verification": {
                "stage_pass_count": defaultdict(int),
                "stage_total": defaultdict(int),
                "collapse_count": 0,
            },
            "details": {
                "attempts_per_subproblem": [],
                "temperatures": [],
                "error_types": defaultdict(int),
            },
            # NEW: Attribution Metrics
            "attribution": {
                "hit_at_attempt": {k: 0 for k in config.ATTEMPT_HIT_BUCKETS},
                "precision_at_k": {k: [] for k in config.PRECISION_K_VALUES},
                "first_success_attempts": [],  # 每个subproblem的首次成功attempt编号
                "total_subproblems": 0,
                "successful_subproblems": 0,
            },
            # NEW: Propagation Metrics
            "propagation": {
                "depth_gaps": [],  # 失败subproblem的depth差距
                "depths_by_success": {"success": [], "failure": []},  # 按成功/失败分组的depth
                "turn_pass_rates": [],  # 每轮的通过率（用于slope计算）
            },
            # NEW: Depth-Stratified Metrics
            "depth_stratified": defaultdict(lambda: {
                "total": 0,
                "success": 0,
                "failure_streaks": [],
                "attempts": [],
                "error_types": defaultdict(int),
            }) if config.ENABLE_DEPTH_STRATIFICATION else {},
        }

    # ------------------------------------------------------------------
    # ingestion
    # ------------------------------------------------------------------

    def record_problem_result(self, problem_log: Dict[str, Any]) -> None:
        """Record the detailed log of a single problem run."""

        self.metrics["correctness"]["total_problems"] += 1
        problem_id = problem_log.get("problem_id")
        overall_depth = problem_log.get("overall-depth", 0)

        # Determine first success turn & attempts
        first_success_turn: Optional[int] = None
        turn_count = len(problem_log.get("subproblems", []))

        for turn_index, subproblem in enumerate(problem_log.get("subproblems", []), start=1):
            attempts = subproblem.get("attempts", [])
            self.metrics["details"]["attempts_per_subproblem"].append(len(attempts))

            for attempt in attempts:
                self.metrics["details"]["temperatures"].append(attempt.get("temperature", 0.0))
                if not attempt.get("success", False):
                    self._record_error_type(attempt.get("test_result", ""))

            if subproblem.get("solved") and first_success_turn is None:
                first_success_turn = turn_index

            self._record_traceability(subproblem)
            self._record_verification(subproblem)

            # NEW: Record attribution, propagation, and depth-stratified metrics
            self._record_attribution(subproblem)
            self._record_propagation(subproblem, overall_depth)
            self._record_depth_stratified(subproblem)

        if first_success_turn is not None:
            self.metrics["correctness"]["successful_problems"] += 1
            self.metrics["correctness"]["first_success_turns"].append(first_success_turn)
            self.metrics["correctness"]["first_success_turn_problem_ids"].append(problem_id)
            for bucket in config.PASS_AT_TURN_BUCKETS:
                if first_success_turn <= bucket:
                    self.metrics["correctness"]["pass_at_turn"][bucket] += 1

        # patch statistics
        patch_stats = problem_log.get("patch_stats", {})
        if patch_stats:
            if "diff_hunks" in patch_stats:
                self.metrics["correctness"]["patch_diff_hunks"].append(patch_stats["diff_hunks"])
            if "lines_changed" in patch_stats:
                self.metrics["correctness"]["patch_lines_changed"].append(
                    patch_stats["lines_changed"]
                )

        self._record_error_accumulation(problem_log)
        self._record_distribution_shift(problem_log, turn_count)

    # ------------------------------------------------------------------
    # traceability helpers
    # ------------------------------------------------------------------

    def _record_traceability(self, subproblem_log: Dict[str, Any]) -> None:
        evidence_map = subproblem_log.get("evidence_map")
        if evidence_map:
            hit = any(
                any(token.lower() in str(entry).lower() for token in config.TRACE_EVIDENCE_KEYS)
                for entry in evidence_map
            )
            self.metrics["traceability"]["evidence_hits"].append(hit)

        replay_results = subproblem_log.get("replay_consistency")
        if isinstance(replay_results, list) and replay_results:
            consistent = all(replay_results)
            self.metrics["traceability"]["replay_consistency"].append(consistent)

        routing_cost = subproblem_log.get("routing_cost")
        if routing_cost is not None:
            self.metrics["traceability"]["routing_cost"].append(float(routing_cost))

        if subproblem_log.get("attempts") is None:
            self.metrics["traceability"]["audit_trails_missing"] += 1

    # ------------------------------------------------------------------
    # verification helpers
    # ------------------------------------------------------------------

    def _record_verification(self, subproblem_log: Dict[str, Any]) -> None:
        verification = subproblem_log.get("verification")
        if not verification:
            return

        stage_results = verification.get("stages", {})
        collapse_detected = False
        previous_pass = True

        for stage in config.VERIFICATION_STAGES:
            if stage not in stage_results:
                continue
            passed = bool(stage_results[stage])
            self.metrics["verification"]["stage_total"][stage] += 1
            if passed:
                self.metrics["verification"]["stage_pass_count"][stage] += 1
            if previous_pass and not passed:
                collapse_detected = True
            previous_pass = previous_pass and passed

        if collapse_detected:
            self.metrics["verification"]["collapse_count"] += 1

    # ------------------------------------------------------------------
    # error accumulation helpers
    # ------------------------------------------------------------------

    def _record_error_accumulation(self, problem_log: Dict[str, Any]) -> None:
        current_streak = 0

        for subproblem in problem_log.get("subproblems", []):
            for attempt in subproblem.get("attempts", []):
                if attempt.get("success"):
                    if current_streak > 0:
                        self.metrics["error_accumulation"]["failure_streaks"].append(current_streak)
                        self.metrics["error_accumulation"]["recovery_by_streak"][current_streak].append(True)
                    current_streak = 0
                else:
                    current_streak += 1

            rollback = subproblem.get("rollback")
            if rollback:
                self.metrics["error_accumulation"]["rollback_triggers"] += 1
                if rollback.get("successful"):
                    self.metrics["error_accumulation"]["rollback_success"] += 1

        if current_streak > 0:
            self.metrics["error_accumulation"]["failure_streaks"].append(current_streak)
            self.metrics["error_accumulation"]["recovery_by_streak"][current_streak].append(False)

    # ------------------------------------------------------------------
    # distribution shift helpers
    # ------------------------------------------------------------------

    def _record_distribution_shift(self, problem_log: Dict[str, Any], turns: int) -> None:
        buckets = self.metrics["distribution_shift"]

        buckets["turn_buckets"][turns].append(bool(problem_log.get("solved")))

        temporal = problem_log.get("temporal_slice")
        if temporal:
            buckets["temporal"][temporal].append(bool(problem_log.get("solved")))

        api_variant = problem_log.get("api_variant")
        if api_variant:
            buckets["api"][api_variant].append(bool(problem_log.get("solved")))

        structure_bucket = problem_log.get("structure_bucket")
        if structure_bucket:
            buckets["structure"][structure_bucket].append(bool(problem_log.get("solved")))

        boundary_bucket = problem_log.get("boundary_bucket")
        if boundary_bucket:
            buckets["boundary"][boundary_bucket].append(bool(problem_log.get("solved")))

    # ------------------------------------------------------------------
    # error taxonomy helper
    # ------------------------------------------------------------------

    def _record_error_type(self, error_message: str) -> None:
        msg = error_message.lower()
        bucket = "other"
        if "output" in msg or "mismatch" in msg:
            bucket = "output_mismatch"
        elif "typeerror" in msg:
            bucket = "type_error"
        elif "index" in msg or "keyerror" in msg:
            bucket = "index_error"
        elif "timeout" in msg:
            bucket = "timeout"
        self.metrics["details"]["error_types"][bucket] += 1

    # ------------------------------------------------------------------
    # NEW: attribution metrics helpers
    # ------------------------------------------------------------------

    def _record_attribution(self, subproblem_log: Dict[str, Any]) -> None:
        """Record attribution metrics (Hit@attempt, Precision@k) for each subproblem."""
        attempts = subproblem_log.get("attempts", [])
        if not attempts:
            return

        self.metrics["attribution"]["total_subproblems"] += 1

        # Find first successful attempt
        first_success_attempt = None
        successful_attempts = 0

        for idx, attempt in enumerate(attempts, start=1):
            if attempt.get("success", False):
                successful_attempts += 1
                if first_success_attempt is None:
                    first_success_attempt = idx

        # Record Hit@attempt<=k
        if first_success_attempt is not None:
            self.metrics["attribution"]["successful_subproblems"] += 1
            self.metrics["attribution"]["first_success_attempts"].append(first_success_attempt)

            for k in config.ATTEMPT_HIT_BUCKETS:
                if first_success_attempt <= k:
                    self.metrics["attribution"]["hit_at_attempt"][k] += 1

        # Record Precision@k
        for k in config.PRECISION_K_VALUES:
            attempts_to_consider = min(k, len(attempts))
            if attempts_to_consider > 0:
                successes_in_k = sum(
                    1 for attempt in attempts[:attempts_to_consider]
                    if attempt.get("success", False)
                )
                precision = successes_in_k / attempts_to_consider
                self.metrics["attribution"]["precision_at_k"][k].append(precision)

    # ------------------------------------------------------------------
    # NEW: propagation metrics helpers
    # ------------------------------------------------------------------

    def _record_propagation(self, subproblem_log: Dict[str, Any], overall_depth: int) -> None:
        """Record propagation metrics (Depth Gap, depth distribution)."""
        subproblem_depth = subproblem_log.get("depth")
        solved = subproblem_log.get("solved", False)

        if subproblem_depth is None:
            return

        # Record depth by success/failure
        if solved:
            self.metrics["propagation"]["depths_by_success"]["success"].append(subproblem_depth)
        else:
            self.metrics["propagation"]["depths_by_success"]["failure"].append(subproblem_depth)
            # Record depth gap for failed subproblems
            depth_gap = overall_depth - subproblem_depth
            self.metrics["propagation"]["depth_gaps"].append(depth_gap)

    # ------------------------------------------------------------------
    # NEW: depth-stratified metrics helpers
    # ------------------------------------------------------------------

    def _record_depth_stratified(self, subproblem_log: Dict[str, Any]) -> None:
        """Record metrics stratified by depth level."""
        if not config.ENABLE_DEPTH_STRATIFICATION:
            return

        depth = subproblem_log.get("depth")
        if depth is None:
            return

        depth_metrics = self.metrics["depth_stratified"][depth]
        depth_metrics["total"] += 1

        attempts = subproblem_log.get("attempts", [])
        depth_metrics["attempts"].append(len(attempts))

        if subproblem_log.get("solved", False):
            depth_metrics["success"] += 1

        # Record error types by depth
        for attempt in attempts:
            if not attempt.get("success", False):
                error_msg = attempt.get("test_result", "").lower()
                bucket = self._classify_error_type(error_msg)
                depth_metrics["error_types"][bucket] += 1

    def _classify_error_type(self, error_message: str) -> str:
        """Classify error message into bucket (helper for depth-stratified metrics)."""
        msg = error_message.lower()
        if "output" in msg or "mismatch" in msg:
            return "output_mismatch"
        elif "typeerror" in msg:
            return "type_error"
        elif "index" in msg or "keyerror" in msg:
            return "index_error"
        elif "timeout" in msg:
            return "timeout"
        else:
            return "other"

    # ------------------------------------------------------------------
    # aggregation
    # ------------------------------------------------------------------

    def compute_final_metrics(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        correctness = self.metrics["correctness"]
        total = correctness["total_problems"]
        successes = correctness["successful_problems"]

        if total:
            result["success_rate"] = successes / total
            result["pass_at_turn"] = {
                bucket: val / total for bucket, val in correctness["pass_at_turn"].items()
            }
        else:
            result["success_rate"] = 0.0
            result["pass_at_turn"] = {bucket: 0.0 for bucket in correctness["pass_at_turn"]}

        first_success_turns = correctness["first_success_turns"]
        if first_success_turns:
            result["mean_first_success_turn"] = mean(first_success_turns)
            result["mrr"] = mean(1.0 / turn for turn in first_success_turns)
        else:
            result["mean_first_success_turn"] = None
            result["mrr"] = 0.0

        if correctness["patch_diff_hunks"]:
            result["patch_diff_hunks_mean"] = mean(correctness["patch_diff_hunks"])
        if correctness["patch_lines_changed"]:
            result["patch_lines_changed_mean"] = mean(correctness["patch_lines_changed"])

        # Traceability
        trace = self.metrics["traceability"]
        if trace["evidence_hits"]:
            result["evidence_hit_rate"] = sum(trace["evidence_hits"]) / len(trace["evidence_hits"])
        if trace["replay_consistency"]:
            result["replay_consistency"] = sum(trace["replay_consistency"]) / len(trace["replay_consistency"])
        if trace["routing_cost"]:
            result["avg_routing_cost"] = mean(trace["routing_cost"])
        result["missing_audit_trails"] = trace["audit_trails_missing"]

        # Error accumulation
        error_section = self.metrics["error_accumulation"]
        streaks = error_section["failure_streaks"]
        if streaks:
            result["mean_failure_streak"] = mean(streaks)
            result["max_failure_streak"] = max(streaks)
        else:
            result["mean_failure_streak"] = 0.0
            result["max_failure_streak"] = 0

        recovery_stats = {
            streak: sum(values) / len(values) if values else 0.0
            for streak, values in error_section["recovery_by_streak"].items()
        }
        result["recovery_probability_by_streak"] = recovery_stats
        result["rollback_trigger_rate"] = error_section["rollback_triggers"]
        result["rollback_success_rate"] = (
            error_section["rollback_success"] / error_section["rollback_triggers"]
            if error_section["rollback_triggers"]
            else None
        )

        # Distribution shift
        distribution = self.metrics["distribution_shift"]
        result["distribution_shift"] = {
            key: {
                bucket: self._success_rate(values)
                for bucket, values in buckets.items()
            }
            for key, buckets in distribution.items()
        }

        # Verification
        verification = self.metrics["verification"]
        stage_summary = {}
        for stage, total_count in verification["stage_total"].items():
            passed = verification["stage_pass_count"].get(stage, 0)
            stage_summary[stage] = {
                "pass_rate": passed / total_count if total_count else None,
                "count": total_count,
            }
        result["verification"] = {
            "stages": stage_summary,
            "collapse_count": verification["collapse_count"],
        }

        # Detailed stats
        details = self.metrics["details"]
        if details["attempts_per_subproblem"]:
            result["mean_attempts_per_subproblem"] = mean(details["attempts_per_subproblem"])
            result["median_attempts_per_subproblem"] = median(details["attempts_per_subproblem"])
        if details["temperatures"]:
            result["temperature_progression"] = {
                "mean": mean(details["temperatures"]),
                "max": max(details["temperatures"]),
            }
        result["error_type_histogram"] = dict(details["error_types"])

        # NEW: Attribution Metrics
        attribution = self.metrics["attribution"]
        total_subproblems = attribution["total_subproblems"]
        if total_subproblems > 0:
            result["hit_at_attempt"] = {
                k: val / total_subproblems for k, val in attribution["hit_at_attempt"].items()
            }
        else:
            result["hit_at_attempt"] = {k: 0.0 for k in config.ATTEMPT_HIT_BUCKETS}

        result["precision_at_k"] = {}
        for k, precision_list in attribution["precision_at_k"].items():
            if precision_list:
                result["precision_at_k"][k] = mean(precision_list)
            else:
                result["precision_at_k"][k] = 0.0

        if attribution["first_success_attempts"]:
            result["mean_first_success_attempt"] = mean(attribution["first_success_attempts"])
            result["attempt_mrr"] = mean(1.0 / attempt for attempt in attribution["first_success_attempts"])
        else:
            result["mean_first_success_attempt"] = None
            result["attempt_mrr"] = 0.0

        result["subproblem_success_rate"] = (
            attribution["successful_subproblems"] / total_subproblems
            if total_subproblems > 0
            else 0.0
        )

        # NEW: Propagation Metrics
        propagation = self.metrics["propagation"]
        if propagation["depth_gaps"]:
            result["mean_depth_gap"] = mean(propagation["depth_gaps"])
            result["max_depth_gap"] = max(propagation["depth_gaps"])
        else:
            result["mean_depth_gap"] = 0.0
            result["max_depth_gap"] = 0

        result["depth_distribution"] = {
            "success": self._compute_depth_stats(propagation["depths_by_success"]["success"]),
            "failure": self._compute_depth_stats(propagation["depths_by_success"]["failure"]),
        }

        # NEW: Pass-rate Slope (computed from turn_buckets in distribution_shift)
        turn_buckets = self.metrics["distribution_shift"]["turn_buckets"]
        if len(turn_buckets) >= config.PASS_RATE_SLOPE_MIN_TURNS:
            pass_rates_by_turn = []
            for turn in sorted(turn_buckets.keys()):
                outcomes = turn_buckets[turn]
                if outcomes:
                    pass_rate = sum(outcomes) / len(outcomes)
                    pass_rates_by_turn.append(pass_rate)

            if len(pass_rates_by_turn) >= config.PASS_RATE_SLOPE_MIN_TURNS:
                # Linear regression to compute slope
                x = np.arange(len(pass_rates_by_turn))
                slope, intercept = np.polyfit(x, pass_rates_by_turn, 1)
                result["pass_rate_slope"] = float(slope)
                result["pass_rate_intercept"] = float(intercept)
                result["pass_rates_by_turn"] = pass_rates_by_turn
            else:
                result["pass_rate_slope"] = None
        else:
            result["pass_rate_slope"] = None

        # NEW: Depth-Stratified Metrics
        if config.ENABLE_DEPTH_STRATIFICATION and self.metrics["depth_stratified"]:
            depth_stratified_summary = {}
            for depth, metrics_dict in self.metrics["depth_stratified"].items():
                total = metrics_dict["total"]
                if total > 0:
                    depth_stratified_summary[depth] = {
                        "total": total,
                        "success_rate": metrics_dict["success"] / total,
                        "mean_attempts": mean(metrics_dict["attempts"]) if metrics_dict["attempts"] else 0.0,
                        "error_types": dict(metrics_dict["error_types"]),
                    }
            result["depth_stratified"] = depth_stratified_summary
        else:
            result["depth_stratified"] = {}

        return result

    # ------------------------------------------------------------------
    # persistence helpers
    # ------------------------------------------------------------------

    def save_metrics(self, filepath: str) -> None:
        payload = {
            "raw_metrics": self.metrics,
            "computed_metrics": self.compute_final_metrics(),
        }
        with open(filepath, "w", encoding="utf-8") as fout:
            json.dump(payload, fout, ensure_ascii=False, indent=2, default=str)

    def generate_metrics_report(self, filepath: str) -> None:
        metrics = self.compute_final_metrics()

        with open(filepath, "w", encoding="utf-8") as fout:
            fout.write("# Evaluation Metrics Report\n\n")

            fout.write("## A. Correctness & Efficiency\n\n")
            fout.write(f"- Success Rate: {metrics.get('success_rate', 0)*100:.2f}%\n")
            if "pass_at_turn" in metrics:
                fout.write("- pass@turn<=T:\n")
                for bucket, val in metrics["pass_at_turn"].items():
                    fout.write(f"  - T={bucket}: {val*100:.2f}%\n")
            fout.write(f"- MRR: {metrics.get('mrr', 0):.4f}\n")
            if metrics.get("patch_diff_hunks_mean") is not None:
                fout.write(
                    f"- Patch Minimality (hunks): {metrics['patch_diff_hunks_mean']:.2f}\n"
                )
            if metrics.get("patch_lines_changed_mean") is not None:
                fout.write(
                    f"- Patch Minimality (lines): {metrics['patch_lines_changed_mean']:.2f}\n"
                )

            fout.write("\n## B. Traceability\n\n")
            if "evidence_hit_rate" in metrics:
                fout.write(f"- Evidence Hit Rate: {metrics['evidence_hit_rate']*100:.2f}%\n")
            if "replay_consistency" in metrics:
                fout.write(
                    f"- Replay Consistency: {metrics['replay_consistency']*100:.2f}%\n"
                )
            if "avg_routing_cost" in metrics:
                fout.write(f"- Mean Routing Cost: {metrics['avg_routing_cost']:.2f}\n")
            fout.write(
                f"- Missing Audit Trails: {metrics.get('missing_audit_trails', 0)} entries\n"
            )

            fout.write("\n## C. Error Accumulation & Recovery\n\n")
            fout.write(
                f"- Mean Failure Streak: {metrics.get('mean_failure_streak', 0):.2f}\n"
            )
            fout.write(f"- Max Failure Streak: {metrics.get('max_failure_streak', 0)}\n")
            fout.write("- Recovery Probability by Streak:\n")
            for streak, rate in sorted(
                metrics.get("recovery_probability_by_streak", {}).items()
            ):
                fout.write(f"  - Streak {streak}: {rate*100:.1f}%\n")
            fout.write(
                f"- Rollback Triggered: {metrics.get('rollback_trigger_rate', 0)} times\n"
            )
            if metrics.get("rollback_success_rate") is not None:
                fout.write(
                    f"- Rollback Success Rate: {metrics['rollback_success_rate']*100:.1f}%\n"
                )

            fout.write("\n## D. Distribution Shift Robustness\n\n")
            for shift_type, bucket_stats in metrics.get("distribution_shift", {}).items():
                if not bucket_stats:
                    continue
                fout.write(f"### {shift_type.title()}\n")
                for bucket, stats in sorted(bucket_stats.items()):
                    fout.write(f"- {bucket}: {stats['success_rate']*100:.1f}% (n={stats['count']})\n")
                fout.write("\n")

            fout.write("## E. Strong Verification\n\n")
            for stage, summary in metrics.get("verification", {}).get("stages", {}).items():
                if summary["pass_rate"] is None:
                    continue
                fout.write(
                    f"- {stage}: {summary['pass_rate']*100:.1f}% (n={summary['count']})\n"
                )
            fout.write(
                f"- Collapse Count: {metrics.get('verification', {}).get('collapse_count', 0)}\n"
            )

            fout.write("\n## Supplementary Statistics\n\n")
            if metrics.get("mean_attempts_per_subproblem") is not None:
                fout.write(
                    f"- Mean Attempts / Subproblem: {metrics['mean_attempts_per_subproblem']:.2f}\n"
                )
            if metrics.get("median_attempts_per_subproblem") is not None:
                fout.write(
                    f"- Median Attempts / Subproblem: {metrics['median_attempts_per_subproblem']:.2f}\n"
                )
            fout.write(
                f"- Error Types: {json.dumps(metrics.get('error_type_histogram', {}), indent=2)}\n"
            )

            # NEW: Attribution Metrics Section
            fout.write("\n## F. Attribution Metrics\n\n")
            if "hit_at_attempt" in metrics:
                fout.write("- Hit@attempt<=k:\n")
                for k, val in sorted(metrics["hit_at_attempt"].items()):
                    fout.write(f"  - k={k}: {val*100:.2f}%\n")

            if "precision_at_k" in metrics:
                fout.write("- Precision@k:\n")
                for k, val in sorted(metrics["precision_at_k"].items()):
                    fout.write(f"  - k={k}: {val*100:.2f}%\n")

            if metrics.get("attempt_mrr") is not None:
                fout.write(f"- Attempt MRR: {metrics['attempt_mrr']:.4f}\n")
            if metrics.get("mean_first_success_attempt") is not None:
                fout.write(f"- Mean First Success Attempt: {metrics['mean_first_success_attempt']:.2f}\n")
            if "subproblem_success_rate" in metrics:
                fout.write(f"- Subproblem Success Rate: {metrics['subproblem_success_rate']*100:.2f}%\n")

            # NEW: Propagation Metrics Section
            fout.write("\n## G. Propagation Metrics\n\n")
            if metrics.get("mean_depth_gap") is not None:
                fout.write(f"- Mean Depth Gap (on failures): {metrics['mean_depth_gap']:.2f}\n")
            if metrics.get("max_depth_gap") is not None:
                fout.write(f"- Max Depth Gap: {metrics['max_depth_gap']}\n")

            depth_dist = metrics.get("depth_distribution", {})
            if depth_dist:
                fout.write("- Depth Distribution:\n")
                for category in ["success", "failure"]:
                    stats = depth_dist.get(category, {})
                    if stats.get("count", 0) > 0:
                        fout.write(f"  - {category.capitalize()}: mean={stats.get('mean', 0):.2f}, "
                                   f"median={stats.get('median', 0):.1f}, "
                                   f"range=[{stats.get('min', 0)}, {stats.get('max', 0)}], "
                                   f"count={stats.get('count', 0)}\n")

            if metrics.get("pass_rate_slope") is not None:
                fout.write(f"- Pass-rate Slope: {metrics['pass_rate_slope']:.4f}\n")
                if "pass_rates_by_turn" in metrics:
                    fout.write(f"  - Pass rates by turn: {[f'{r:.2%}' for r in metrics['pass_rates_by_turn']]}\n")

            # NEW: Depth-Stratified Metrics Section
            if metrics.get("depth_stratified"):
                fout.write("\n## H. Depth-Stratified Metrics\n\n")
                for depth in sorted(metrics["depth_stratified"].keys()):
                    depth_metrics = metrics["depth_stratified"][depth]
                    fout.write(f"### Depth {depth}\n")
                    fout.write(f"- Total subproblems: {depth_metrics['total']}\n")
                    fout.write(f"- Success rate: {depth_metrics['success_rate']*100:.2f}%\n")
                    fout.write(f"- Mean attempts: {depth_metrics['mean_attempts']:.2f}\n")
                    if depth_metrics.get("error_types"):
                        fout.write(f"- Error types: {json.dumps(depth_metrics['error_types'], indent=2)}\n")
                    fout.write("\n")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _success_rate(outcomes: Iterable[bool]) -> Dict[str, Any]:
        outcomes = list(outcomes)
        if not outcomes:
            return {"success_rate": 0.0, "count": 0}
        success_rate = sum(bool(x) for x in outcomes) / len(outcomes)
        return {"success_rate": success_rate, "count": len(outcomes)}

    @staticmethod
    def _compute_depth_stats(depths: List[int]) -> Dict[str, Any]:
        """Compute statistics for a list of depths."""
        if not depths:
            return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
        return {
            "count": len(depths),
            "mean": mean(depths),
            "median": median(depths),
            "min": min(depths),
            "max": max(depths),
        }


__all__ = ["MetricsTracker"]


