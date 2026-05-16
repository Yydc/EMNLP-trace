"""Slice per-problem metric records by difficulty / depth band.

Paper Table tab:difficulty-plan reports metrics across 3 bands:
    easy_med (easy + medium + unrated)
    hard
    very_hard_plus (very_hard + extreme)
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, Iterable, List, Optional


DIFFICULTY_TO_BAND: Dict[str, str] = {
    "easy": "easy_med",
    "medium": "easy_med",
    "unrated": "easy_med",
    "hard": "hard",
    "very_hard": "very_hard_plus",
    "extreme": "very_hard_plus",
}

BAND_DISPLAY: Dict[str, str] = {
    "easy_med": "Easy / Medium",
    "hard": "Hard",
    "very_hard_plus": "VeryHard+",
}

BAND_ORDER = ["easy_med", "hard", "very_hard_plus"]


def slice_by_band(
    per_problem_records: List[Dict[str, Any]],
    entries_by_trace_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Group per-problem records into difficulty bands and aggregate.

    Args:
        per_problem_records: from MetricAggregator.per_problem
        entries_by_trace_id: lookup map (trace_id → original dataset entry)
                             so we can find each problem's difficulty field.

    Returns:
        {band: {pass_at_1, blame_at_1, outside_g, regression_rate, gap,
                avg_turns, n, ...}}
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {b: [] for b in BAND_ORDER}
    for rec in per_problem_records:
        tid = rec.get("trace_id")
        entry = entries_by_trace_id.get(tid)
        if entry is None:
            continue
        band = DIFFICULTY_TO_BAND.get(entry.get("difficulty", "unrated"), "easy_med")
        buckets[band].append(rec)

    result: Dict[str, Dict[str, Any]] = {}
    for band in BAND_ORDER:
        recs = buckets[band]
        n = len(recs)
        if n == 0:
            result[band] = {"n": 0}
            continue

        def _mean_of(key: str) -> Optional[float]:
            vs = [r[key] for r in recs if r.get(key) is not None]
            return mean(vs) if vs else None

        pass_at_1 = sum(1 for r in recs if r.get("solved")) / n
        blame_at_1 = sum(r.get("blame_at_1", 0) for r in recs) / n
        result[band] = {
            "n": n,
            "pass_at_1": pass_at_1,
            "blame_at_1": blame_at_1,
            "gap": pass_at_1 - blame_at_1,
            "outside_g": _mean_of("outside_g"),
            "regression_rate": _mean_of("regression_rate"),
            "avg_turns": _mean_of("first_success_turn"),
        }
    return result


def slice_by_depth(
    per_problem_records: List[Dict[str, Any]],
    entries_by_trace_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Group by call-graph depth: ≤2, =3, ≥4."""
    buckets: Dict[str, List[Dict[str, Any]]] = {"depth_le_2": [], "depth_3": [], "depth_ge_4": []}
    for rec in per_problem_records:
        entry = entries_by_trace_id.get(rec.get("trace_id"))
        if entry is None:
            continue
        depth = entry.get("depth") or 0
        if depth <= 2:
            buckets["depth_le_2"].append(rec)
        elif depth == 3:
            buckets["depth_3"].append(rec)
        else:
            buckets["depth_ge_4"].append(rec)

    result: Dict[str, Dict[str, Any]] = {}
    for k, recs in buckets.items():
        n = len(recs)
        if n == 0:
            result[k] = {"n": 0}
            continue

        def _mean_of(key: str) -> Optional[float]:
            vs = [r[key] for r in recs if r.get(key) is not None]
            return mean(vs) if vs else None

        pass_at_1 = sum(1 for r in recs if r.get("solved")) / n
        blame_at_1 = sum(r.get("blame_at_1", 0) for r in recs) / n
        result[k] = {
            "n": n,
            "pass_at_1": pass_at_1,
            "blame_at_1": blame_at_1,
            "gap": pass_at_1 - blame_at_1,
            "outside_g": _mean_of("outside_g"),
            "regression_rate": _mean_of("regression_rate"),
            "avg_turns": _mean_of("first_success_turn"),
        }
    return result


def render_band_table(bands: Dict[str, Dict[str, Any]]) -> str:
    """Render the band breakdown as a Markdown table."""
    rows = ["| Band | n | Pass@1 | Blame@1 | Gap | Outside-G | RegRate | AvgTurns |",
            "|------|--:|-------:|--------:|----:|----------:|--------:|---------:|"]
    for band in BAND_ORDER:
        b = bands.get(band, {})
        n = b.get("n", 0)
        if n == 0:
            rows.append(f"| {BAND_DISPLAY[band]} | 0 | — | — | — | — | — | — |")
            continue
        def fmt(v): return f"{v:.3f}" if isinstance(v, (int, float)) else "—"
        rows.append(
            f"| {BAND_DISPLAY[band]} | {n} | {fmt(b['pass_at_1'])} | {fmt(b['blame_at_1'])} | "
            f"{fmt(b['gap'])} | {fmt(b.get('outside_g'))} | {fmt(b.get('regression_rate'))} | "
            f"{fmt(b.get('avg_turns'))} |"
        )
    return "\n".join(rows)
