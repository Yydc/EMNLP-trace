from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from .risk_analyzer import Span
from . import metrics_v2

# Default test timeout mirrors runner defaults.
TEST_TIMEOUT = int(os.getenv("TRACEBENCH_TEST_TIMEOUT", "120"))


class TraceabilityMetrics:
    """Compute per-problem traceability metrics for TraceBench."""

    def __init__(self, k_values: Optional[List[int]] = None) -> None:
        self.k_values = sorted(set(k_values or [1, 3, 5]))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze(
        self,
        tracebench_entry: Dict[str, Any],
        problem_log: Dict[str, Any],
        file_path: str,
    ) -> Dict[str, Any]:
        # Normalize entry to ensure metrics have the required fields even for multi-turn data.
        entry = self._enrich_entry(tracebench_entry, file_path)

        bug_spans = self._extract_bug_spans(entry, file_path)

        # Normalize multi-turn format to single-turn format for metric computation
        normalized_log = self._normalize_problem_log(problem_log)

        top1_blame = self._select_top1_blame(normalized_log)
        blame = self._compute_blame_at_k(normalized_log, bug_spans)
        patch_locality = self._compute_patch_locality(normalized_log, bug_spans)
        precision_at_1 = self._compute_precision_at_1(top1_blame, bug_spans)
        cf_valid_at_1 = self._compute_cf_valid_at_1(entry, bug_spans, top1_blame)

        # New paper-aligned metrics (Outside-G, RegressionRate, per-traj slope,
        # repeats, test-without-edit). All graceful-degrade to None if the
        # required attempt-level fields are absent.
        v2 = self._compute_metrics_v2(entry, problem_log, file_path)

        return {
            "blame_at_k": blame,
            "patch_locality": patch_locality,
            "precision_at_1": precision_at_1,
            "cf_valid_at_1": cf_valid_at_1,
            **v2,
        }

    def _compute_metrics_v2(
        self,
        entry: Dict[str, Any],
        problem_log: Dict[str, Any],
        file_path: str,
    ) -> Dict[str, Any]:
        """Compute Outside-G / RegressionRate / per-traj slope / repeats / TWE.

        The raw problem_log preserves per-turn structure; metrics_v2 needs
        attempts grouped by turn (so each turn has its own active spans).
        """
        # Per-turn attempt grouping. Prefer multi-turn schema; fall back to
        # the flattened "subproblems" form.
        turn_blocks: List[Tuple[Any, List[Dict[str, Any]]]] = []
        if "turn_results" in problem_log:
            for tr in problem_log["turn_results"]:
                turn_blocks.append((tr.get("turn_id"), tr.get("attempts", []) or []))
        else:
            # Single-turn / legacy form: use turn_id=0
            for sub in problem_log.get("subproblems", []):
                turn_blocks.append((0, sub.get("attempts", []) or []))

        # Compute per-turn Outside-G then mean across turns.
        og_values: List[float] = []
        for turn_id, attempts in turn_blocks:
            active_spans = metrics_v2.active_spans_from_entry(entry, turn_id)
            v = metrics_v2.outside_g_trajectory(attempts, active_spans)
            if v is not None:
                og_values.append(v)
        outside_g = sum(og_values) / len(og_values) if og_values else None

        # RegressionRate: per-turn using each turn's test_cases. The full
        # ``evaluation.test_cases`` is too broad — paper RegRate is per-edit
        # within a turn.
        rr_values: List[float] = []
        for (turn_id, attempts), turn in zip(turn_blocks, (entry.get("conversation_history") or [])):
            tests = turn.get("test_cases") or []
            if not tests:
                continue
            v = metrics_v2.regression_rate_trajectory(attempts, tests, file_path)
            if v is not None:
                rr_values.append(v)
        # Fall back to entry-level tests if multi-turn structure missing.
        if not rr_values:
            all_tests = entry.get("evaluation", {}).get("test_cases") or []
            flat_attempts = [a for _, atts in turn_blocks for a in atts]
            v = metrics_v2.regression_rate_trajectory(flat_attempts, all_tests, file_path)
            if v is not None:
                rr_values.append(v)
        regression_rate = sum(rr_values) / len(rr_values) if rr_values else None

        # Per-trajectory slope: flatten attempts in order, fit one line.
        flat_attempts = [a for _, atts in turn_blocks for a in atts]
        traj_slope, traj_r2 = metrics_v2.per_trajectory_slope_r2(flat_attempts)

        repeats = metrics_v2.repeated_submissions(flat_attempts)
        twe = metrics_v2.count_test_without_edit(flat_attempts)

        return {
            "outside_g": outside_g,
            "regression_rate": regression_rate,
            "trajectory_slope": traj_slope,
            "trajectory_r2": traj_r2,
            "repeats": repeats,
            "test_without_edit": twe,
        }

    def _enrich_entry(self, entry: Dict[str, Any], default_file: str) -> Dict[str, Any]:
        """
        Fill missing fields so precision / CF metrics can still be computed on multi-turn data:
        - Ensure code_context exists with file_path and corrupted_code.
        - Ensure evaluation.test_cases exists (fallback to last turn tests).
        """
        entry = dict(entry)

        # code_context
        code_ctx = dict(entry.get("code_context") or {})
        code_ctx.setdefault("file_path", default_file or "solution.py")

        # Reconstruct a best-effort corrupted_code from the final turn if missing.
        if not code_ctx.get("corrupted_code") and entry.get("multi_turn") and entry.get("conversation_history"):
            try:
                last_turn = entry["conversation_history"][-1]
                ctx = last_turn.get("context", "") or ""
                tgt = last_turn.get("target_code", "") or ""
                combined = (ctx + "\n\n" + tgt).strip()
                if combined:
                    code_ctx["corrupted_code"] = combined
            except Exception:
                pass
        entry["code_context"] = code_ctx

        # evaluation.test_cases
        eval_block = dict(entry.get("evaluation") or {})
        if not eval_block.get("test_cases"):
            # 采用多轮测试用例的并集，避免只用最后一轮导致覆盖不全
            convo = entry.get("conversation_history") or []
            aggregated_tests: List[str] = []
            for turn in convo:
                aggregated_tests.extend(turn.get("test_cases") or [])
            if aggregated_tests:
                eval_block["test_cases"] = aggregated_tests
        if eval_block:
            entry["evaluation"] = eval_block

        return entry

    def _normalize_problem_log(self, problem_log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize multi-turn format to single-turn format.
        Multi-turn: {turn_results: [{turn_id, solved, attempts: [...]}]}
        Single-turn: {subproblems: [{attempts: [...]}]}
        """
        # If already in single-turn format, return as-is
        if "subproblems" in problem_log:
            return problem_log

        # Convert multi-turn format
        turn_results = problem_log.get("turn_results", [])
        if not turn_results:
            return {"subproblems": []}

        # Flatten all attempts from all turns into subproblems
        subproblems = []
        for turn in turn_results:
            attempts = turn.get("attempts", [])
            if attempts:
                subproblems.append({"attempts": attempts})

        return {"subproblems": subproblems}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_bug_spans(self, entry: Dict[str, Any], file_path: str) -> List[Span]:
        spans: List[Span] = []
        injections = entry.get("injections", [])
        for inj in injections:
            anchor = inj.get("anchor", {}) or {}
            location = inj.get("location", {}) or {}
            line = anchor.get("anchor_line") or location.get("line_approx")
            if line is None:
                continue
            try:
                line_num = int(line)
            except (TypeError, ValueError):
                continue
            spans.append(Span(file_path=file_path, start_line=line_num, end_line=line_num, score=1.0))
        return spans

    def _compute_blame_at_k(self, problem_log: Dict[str, Any], bug_spans: List[Span]) -> Dict[int, int]:
        # Default: all zeros if we cannot compute.
        if not bug_spans:
            return {k: 0 for k in self.k_values}

        def overlaps(span: Span, bug: Span) -> bool:
            if span.file_path != bug.file_path:
                return False
            return not (span.end_line < bug.start_line or span.start_line > bug.end_line)

        hit_by_k = {k: 0 for k in self.k_values}
        for sub in problem_log.get("subproblems", []):
            for attempt in sub.get("attempts", []):
                blame_spans = attempt.get("blame_spans") or []
                if not blame_spans:
                    continue
                # Sort by score descending (default score 0 if missing)
                sorted_spans = sorted(
                    blame_spans,
                    key=lambda s: s.get("score", 0),
                    reverse=True,
                )
                for k in self.k_values:
                    topk = sorted_spans[:k]
                    for cand in topk:
                        try:
                            span = Span(
                                file_path=cand.get("file_path", ""),
                                start_line=int(cand.get("start_line", 0) or 0),
                                end_line=int(cand.get("end_line", 0) or 0),
                                score=float(cand.get("score", 0) or 0.0),
                            )
                        except (TypeError, ValueError):
                            continue
                        if any(overlaps(span, bug) for bug in bug_spans):
                            hit_by_k[k] = 1
                            break
                    # If already hit at smaller k, higher k also considered hit
                    if k > 1 and hit_by_k.get(k - 1):
                        hit_by_k[k] = 1
        return hit_by_k

    def _compute_patch_locality(self, problem_log: Dict[str, Any], bug_spans: List[Span]) -> Dict[str, Optional[float]]:
        if not bug_spans:
            return {
                "min_distance": None,
                "mean_distance": None,
                "mean_iou": None,
                "line_count_mean": None,
                "hit_anchor": None,
            }

        min_distances: List[float] = []
        mean_distances: List[float] = []
        ious: List[float] = []
        line_counts: List[int] = []

        def span_distance(patch: Span, bug: Span) -> float:
            if patch.file_path != bug.file_path:
                return float("inf")
            if patch.end_line < bug.start_line:
                return bug.start_line - patch.end_line
            if patch.start_line > bug.end_line:
                return patch.start_line - bug.end_line
            return 0.0

        def span_iou(patch: Span, bug: Span) -> float:
            if patch.file_path != bug.file_path:
                return 0.0
            inter_start = max(patch.start_line, bug.start_line)
            inter_end = min(patch.end_line, bug.end_line)
            if inter_end < inter_start:
                return 0.0
            inter = inter_end - inter_start + 1
            union = (patch.end_line - patch.start_line + 1) + (bug.end_line - bug.start_line + 1) - inter
            return inter / union if union > 0 else 0.0

        for sub in problem_log.get("subproblems", []):
            for attempt in sub.get("attempts", []):
                for p in attempt.get("patch_spans", []) or []:
                    try:
                        span = Span(
                            file_path=p.get("file_path", ""),
                            start_line=int(p.get("start_line", 0) or 0),
                            end_line=int(p.get("end_line", 0) or 0),
                            score=1.0,
                        )
                    except (TypeError, ValueError):
                        continue

                    # Choose nearest / best-matching bug span
                    distances = [span_distance(span, bug) for bug in bug_spans]
                    iou_scores = [span_iou(span, bug) for bug in bug_spans]

                    finite_dists = [d for d in distances if d != float("inf")]
                    if not finite_dists:
                        continue

                    min_distances.append(min(finite_dists))
                    mean_distances.append(mean(finite_dists))
                    ious.append(max(iou_scores))
                    line_counts.append(max(1, span.end_line - span.start_line + 1))

        min_dist = min(min_distances) if min_distances else None
        mean_dist = mean(mean_distances) if mean_distances else None
        mean_iou_val = mean(ious) if ious else None
        hit_anchor = None
        if min_dist is not None or mean_iou_val is not None:
            hit_anchor = False
            if min_dist == 0 or (ious and max(ious) > 0):
                hit_anchor = True

        return {
            "min_distance": min_dist,
            "mean_distance": mean_dist,
            "mean_iou": mean_iou_val,
            "line_count_mean": mean(line_counts) if line_counts else None,
            "hit_anchor": hit_anchor,
        }

    # ------------------------------------------------------------------
    # New helpers: precision@1, CF-Valid@1, blame selection, test runner
    # ------------------------------------------------------------------
    def _select_top1_blame(self, problem_log: Dict[str, Any]) -> Optional[Span]:
        """Pick the first available top-1 blame span (sorted by score)."""
        for sub in problem_log.get("subproblems", []):
            for attempt in sub.get("attempts", []):
                blame_spans = attempt.get("blame_spans") or []
                if not blame_spans:
                    continue
                sorted_spans = sorted(
                    blame_spans,
                    key=lambda s: s.get("score", 0),
                    reverse=True,
                )
                top = sorted_spans[0]
                try:
                    return Span(
                        file_path=top.get("file_path", ""),
                        start_line=int(top.get("start_line", 0) or 0),
                        end_line=int(top.get("end_line", 0) or 0),
                        score=float(top.get("score", 0) or 0.0),
                    )
                except (TypeError, ValueError):
                    return None
        return None

    def _compute_precision_at_1(self, top1_blame: Optional[Span], bug_spans: List[Span]) -> Optional[float]:
        """Top-1 blamed span overlaps any bug span."""
        if not top1_blame or not bug_spans:
            return None
        for bug in bug_spans:
            if top1_blame.file_path != bug.file_path:
                continue
            if not (top1_blame.end_line < bug.start_line or top1_blame.start_line > bug.end_line):
                return 1.0
        return 0.0

    def _compute_cf_valid_at_1(
        self,
        entry: Dict[str, Any],
        bug_spans: List[Span],
        top1_blame: Optional[Span],
    ) -> Optional[float]:
        """
        CF-Valid@1: replace GT-overlapping lines inside top-1 blame with clean code,
        check fail→pass transition.
        """
        if not top1_blame or not bug_spans:
            return None

        tests = entry.get("evaluation", {}).get("test_cases") or []
        if not tests:
            return None

        buggy_code = entry.get("code_context", {}).get("corrupted_code") or entry.get("original_code", "")
        clean_code = entry.get("original_code", "")
        file_path = entry.get("code_context", {}).get("file_path", "solution.py")

        if not buggy_code or not clean_code:
            return None

        target_lines = self._overlap_lines(top1_blame, bug_spans)
        if not target_lines:
            return 0.0

        cf_code = self._apply_cf_patch(buggy_code, clean_code, target_lines)
        if cf_code is None:
            return None

        bug_pass = self._run_test_bundle(buggy_code, tests, file_path)
        cf_pass = self._run_test_bundle(cf_code, tests, file_path)

        if bug_pass is None or cf_pass is None:
            return None
        if (not bug_pass) and cf_pass:
            return 1.0
        return 0.0

    def _overlap_lines(self, top: Span, bug_spans: List[Span]) -> List[int]:
        lines: List[int] = []
        for bug in bug_spans:
            if top.file_path != bug.file_path:
                continue
            start = max(top.start_line, bug.start_line)
            end = min(top.end_line, bug.end_line)
            if start <= end:
                lines.extend(range(start, end + 1))
        return sorted(set(lines))

    def _apply_cf_patch(self, buggy: str, clean: str, lines: List[int]) -> Optional[str]:
        buggy_lines = buggy.splitlines()
        clean_lines = clean.splitlines()
        if not buggy_lines or not clean_lines:
            return None
        patched = list(buggy_lines)
        for ln in lines:
            idx = ln - 1
            if 0 <= idx < len(clean_lines) and 0 <= idx < len(patched):
                patched[idx] = clean_lines[idx]
        return "\n".join(patched)

    def _run_test_bundle(self, code: str, tests: List[str], file_path: str) -> Optional[bool]:
        """Execute provided test snippets against a code string."""
        if not tests:
            return None
        try:
            with tempfile.TemporaryDirectory(prefix="tracebench_cf_") as tmpdir:
                script_name = Path(file_path).name or "candidate.py"
                script_path = Path(tmpdir) / script_name
                main_block = "\n".join(f"    {t}" for t in tests)
                script_body = f"{code}\n\nif __name__ == '__main__':\n{main_block or '    pass'}\n"
                script_path.write_text(script_body, encoding="utf-8")

                proc = subprocess.run(
                    [sys.executable, script_path.name],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=TEST_TIMEOUT,
                )
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return None
