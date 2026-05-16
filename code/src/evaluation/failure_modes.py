"""Rule-based failure-mode classifier (paper Table tab:taxonomy).

Five modes:

  - precise_repair       : solved + first blame hits + low Outside-G
  - symptom_patch        : solved + first blame misses
  - semantic_drift       : not solved + first blame misses + Outside-G high
  - regression_loop      : RegressionRate > threshold over ≥2 transitions
  - diagnostic_recovery  : early miss → later blame hit → final pass

Thresholds are conservative defaults; ablation can sweep them in the paper.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


DEFAULT_THRESHOLDS = {
    "outside_g_low": 0.30,
    "outside_g_high": 0.50,
    "regression_rate_loop": 0.20,
}

MODES = [
    "precise_repair",
    "symptom_patch",
    "semantic_drift",
    "regression_loop",
    "diagnostic_recovery",
    "unclassified",
]


def _attempt_stream(problem_log: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten attempts in chronological order across turns."""
    attempts: List[Dict[str, Any]] = []
    for tr in problem_log.get("turn_results", []) or []:
        attempts.extend(tr.get("attempts", []) or [])
    if not attempts:
        for sub in problem_log.get("subproblems", []) or []:
            attempts.extend(sub.get("attempts", []) or [])
    return attempts


def _spans_overlap_any(blame_spans, active_spans) -> bool:
    for span in blame_spans or []:
        try:
            s = int(span.get("start_line", 0))
            e = int(span.get("end_line", s))
        except (TypeError, ValueError):
            continue
        for lo, hi in active_spans:
            if not (e < lo or s > hi):
                return True
    return False


def classify_trajectory(
    problem_log: Dict[str, Any],
    rec: Dict[str, Any],
    active_spans: List[Tuple[int, int]],
    thresholds: Optional[Dict[str, float]] = None,
) -> str:
    """Classify a single trajectory into one of the 5 failure modes."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    attempts = _attempt_stream(problem_log)

    # Identify first and last attempt with non-empty blame.
    first_blame_att = next((a for a in attempts if a.get("blame_spans")), None)
    last_blame_att = next((a for a in reversed(attempts) if a.get("blame_spans")), None)

    first_hit = (
        _spans_overlap_any(first_blame_att.get("blame_spans"), active_spans)
        if first_blame_att else False
    )
    last_hit = (
        _spans_overlap_any(last_blame_att.get("blame_spans"), active_spans)
        if last_blame_att else False
    )

    solved = bool(rec.get("solved"))
    og = rec.get("outside_g") or 0.0
    rr = rec.get("regression_rate") or 0.0

    # Regression loop dominates: if the model destabilized previously
    # passing tests across multiple transitions, classify as regression_loop
    # regardless of final outcome.
    if rr >= th["regression_rate_loop"]:
        return "regression_loop"

    if solved:
        if first_blame_att is None:
            # Solved without ever blaming a span → treat as symptom_patch
            # (no auditable causal claim).
            return "symptom_patch"
        if first_hit and og <= th["outside_g_low"]:
            return "precise_repair"
        if not first_hit and last_hit:
            return "diagnostic_recovery"
        if not first_hit:
            return "symptom_patch"
        return "precise_repair"  # first hit, slightly diffuse but still solved

    # Unsolved branch.
    if first_blame_att is not None and not first_hit and og >= th["outside_g_high"]:
        return "semantic_drift"
    return "unclassified"


def classify_all(
    per_problem: List[Dict[str, Any]],
    problem_logs_by_id: Dict[str, Dict[str, Any]],
    entries_by_id: Dict[str, Dict[str, Any]],
    active_spans_fn,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Classify every trajectory and return frequency table + per-problem labels."""
    labels: Dict[str, str] = {}
    counts: Dict[str, int] = {m: 0 for m in MODES}
    for rec in per_problem:
        tid = rec.get("trace_id")
        log = problem_logs_by_id.get(tid)
        entry = entries_by_id.get(tid)
        if log is None or entry is None:
            labels[tid or ""] = "unclassified"
            counts["unclassified"] += 1
            continue
        active = active_spans_fn(entry)
        mode = classify_trajectory(log, rec, active, thresholds)
        labels[tid or ""] = mode
        counts[mode] = counts.get(mode, 0) + 1

    total = sum(counts.values()) or 1
    fractions = {m: counts[m] / total for m in counts}
    return {"counts": counts, "fractions": fractions, "labels": labels}


def render_taxonomy_table(result: Dict[str, Any]) -> str:
    """Render the frequency table as Markdown."""
    counts = result["counts"]
    fractions = result["fractions"]
    rows = ["| Failure mode | Count | Fraction |", "|------|------:|---------:|"]
    for m in MODES:
        rows.append(f"| {m} | {counts.get(m, 0)} | {fractions.get(m, 0):.3f} |")
    return "\n".join(rows)
