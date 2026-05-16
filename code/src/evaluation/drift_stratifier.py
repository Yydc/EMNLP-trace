"""Stratify trajectories by whether the FIRST blame attempt hits the active fault.

Paper Table tab:early-drift reports (Miss − Hit) deltas on:
    - Cumulative patch size       (downstream lines edited summed across attempts)
    - Outside-G                   (mean over trajectory)
    - Final Blame@1               (whether final-turn top blame hits)

The classifier walks each trajectory in chronological order, looks at the
first attempt with non-empty blame_spans, and decides hit vs miss.
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _first_attempt_with_blame(
    problem_log: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return the chronologically first attempt that produced blame_spans."""
    # multi-turn
    for tr in problem_log.get("turn_results", []) or []:
        for att in tr.get("attempts", []) or []:
            if att.get("blame_spans"):
                return att
    # single-turn / legacy
    for sub in problem_log.get("subproblems", []) or []:
        for att in sub.get("attempts", []) or []:
            if att.get("blame_spans"):
                return att
    return None


def _spans_overlap_any(
    blame_spans: List[Dict[str, Any]],
    active_spans: List[Tuple[int, int]],
) -> bool:
    """True if any blame span overlaps any active fault span."""
    for span in blame_spans or []:
        s = int(span.get("start_line", 0) or 0)
        e = int(span.get("end_line", s) or s)
        for lo, hi in active_spans:
            if not (e < lo or s > hi):
                return True
    return False


def classify_first_blame(
    problem_log: Dict[str, Any],
    active_spans: List[Tuple[int, int]],
) -> str:
    """Classify a trajectory's first-blame as 'hit', 'miss', or 'no_blame'."""
    first = _first_attempt_with_blame(problem_log)
    if first is None:
        return "no_blame"
    return "hit" if _spans_overlap_any(first.get("blame_spans") or [], active_spans) else "miss"


def trajectory_summary(
    problem_log: Dict[str, Any],
    rec: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute the downstream metrics that the paper's Miss-Hit table uses."""
    # Flatten all attempts in order.
    attempts: List[Dict[str, Any]] = []
    for tr in problem_log.get("turn_results", []) or []:
        attempts.extend(tr.get("attempts", []) or [])
    if not attempts:
        for sub in problem_log.get("subproblems", []) or []:
            attempts.extend(sub.get("attempts", []) or [])

    # Cumulative patch size = sum over attempts of (end - start + 1) per span.
    cum_patch = 0
    for att in attempts:
        for sp in att.get("patch_spans", []) or []:
            try:
                start = int(sp.get("start_line", 0) or 0)
                end = int(sp.get("end_line", start) or start)
                cum_patch += max(0, end - start + 1)
            except (TypeError, ValueError):
                continue

    # Final Blame@1 hit (per-problem aggregate); reuse the record we have.
    final_blame_at_1 = int(rec.get("blame_at_1", 0))

    return {
        "cum_patch_size": cum_patch,
        "outside_g": rec.get("outside_g"),
        "final_blame_at_1": final_blame_at_1,
    }


def stratify_problems(
    per_problem: List[Dict[str, Any]],
    problem_logs_by_id: Dict[str, Dict[str, Any]],
    entries_by_id: Dict[str, Dict[str, Any]],
    active_spans_fn,
) -> Dict[str, Dict[str, Any]]:
    """Build the Hit/Miss/no_blame strata and aggregate.

    active_spans_fn(entry) → List[Tuple[lo, hi]] should resolve the active
    fault region for a given entry (typically the union across turns when
    we're aggregating at the problem level).

    Returns ``{stratum: {n, cum_patch_size_mean, outside_g_mean,
                          final_blame_at_1_rate}}``
    and a top-level ``{"miss_minus_hit": {...}}`` block.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {"hit": [], "miss": [], "no_blame": []}

    for rec in per_problem:
        tid = rec.get("trace_id")
        log = problem_logs_by_id.get(tid)
        entry = entries_by_id.get(tid)
        if log is None or entry is None:
            continue
        active = active_spans_fn(entry)
        stratum = classify_first_blame(log, active)
        summary = trajectory_summary(log, rec)
        buckets[stratum].append(summary)

    def _aggregate(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(items)
        if n == 0:
            return {"n": 0}

        def _mean(key: str) -> Optional[float]:
            vs = [it[key] for it in items if it.get(key) is not None]
            return mean(vs) if vs else None

        return {
            "n": n,
            "cum_patch_size_mean": _mean("cum_patch_size"),
            "outside_g_mean": _mean("outside_g"),
            "final_blame_at_1_rate": _mean("final_blame_at_1"),
        }

    result = {k: _aggregate(v) for k, v in buckets.items()}

    # Miss − Hit deltas (paper Table values).
    hit = result.get("hit") or {}
    miss = result.get("miss") or {}

    def _delta(key: str) -> Optional[float]:
        m, h = miss.get(key), hit.get(key)
        if m is None or h is None:
            return None
        return m - h

    result["miss_minus_hit"] = {
        "cum_patch_size": _delta("cum_patch_size_mean"),
        "outside_g": _delta("outside_g_mean"),
        "final_blame_at_1": _delta("final_blame_at_1_rate"),
    }
    return result
