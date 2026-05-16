"""Process-level metrics for TraceBench (paper Section 3).

This module implements the four primary metrics that the paper claims but
that ``traceability_metrics.py`` does not (yet) cover:

    Outside-G           = fraction of edited lines outside the active fault region
    RegressionRate      = fraction of previously passing tests that newly fail after an edit
    per-traj slope/R^2  = least-squares fit to the per-instance ρ_t curve
    repeats / TWE       = repeated submissions + test-without-edit counts

Each metric is a *pure function* over a normalized problem_log + tests
list. Use these for unit testing; the wiring into ``MetricAggregator``
lives in ``traceability_metrics.py``.
"""

from __future__ import annotations

import hashlib
import math
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .test_runner import run_tests_per_test


# ----------------------------------------------------------------------
# Edit footprint helpers
# ----------------------------------------------------------------------

def edited_lines_from_diff(before: str, after: str) -> List[int]:
    """Return 1-based line indices in `after` that differ from `before`.

    Uses difflib's opcodes. Insertions are recorded at their post-edit
    position; deletions are recorded at the line they precede in `after`.
    """
    import difflib

    b_lines = before.splitlines()
    a_lines = after.splitlines()
    edited = []
    matcher = difflib.SequenceMatcher(a=b_lines, b=a_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "insert"):
            for j in range(j1, j2):
                edited.append(j + 1)  # 1-based in after
        elif tag == "delete":
            # Record the line position where deletion happened (in `after`).
            edited.append(max(1, j1 + 1))
    return sorted(set(edited))


# ----------------------------------------------------------------------
# Outside-G
# ----------------------------------------------------------------------

def outside_g_for_attempt(
    edited_lines: List[int],
    active_spans: List[Tuple[int, int]],
    neighborhood: int = 3,
) -> Optional[float]:
    """Compute Outside-G for a single (P_t, P_{t+1}) edit.

    Outside-G = |{ℓ ∈ edited_lines : d(ℓ, G) > neighborhood}| / |edited_lines|

    where G is the union of active fault line ranges and d(ℓ, G) is the
    Chebyshev distance to the nearest span. neighborhood=3 follows the
    paper's "fault region" convention (a few lines around the anchor).

    Returns None if there are no edits (denominator is 0); the caller
    should skip None.
    """
    if not edited_lines:
        return None
    if not active_spans:
        # No grounded region → every edit is outside by convention.
        return 1.0

    def distance(ln: int) -> int:
        best = math.inf
        for lo, hi in active_spans:
            if lo <= ln <= hi:
                return 0
            best = min(best, abs(ln - lo), abs(ln - hi))
        return int(best)

    outside = sum(1 for ln in edited_lines if distance(ln) > neighborhood)
    return outside / len(edited_lines)


def outside_g_trajectory(
    attempts: Iterable[Dict[str, Any]],
    active_spans: List[Tuple[int, int]],
    neighborhood: int = 3,
) -> Optional[float]:
    """Mean Outside-G across all edit transitions in a trajectory.

    Each attempt must carry an ``edited_lines`` field. Attempts without
    one are skipped.
    """
    per = []
    for att in attempts:
        edits = att.get("edited_lines") or []
        v = outside_g_for_attempt(edits, active_spans, neighborhood)
        if v is not None:
            per.append(v)
    if not per:
        return None
    return mean(per)


# ----------------------------------------------------------------------
# RegressionRate
# ----------------------------------------------------------------------

def regression_rate_for_pair(
    code_before: str,
    code_after: str,
    tests: List[str],
    file_path: str = "solution.py",
) -> Optional[float]:
    """Run tests on both code states, return fraction of newly-failed tests.

    RegressionRate = |{t : t passed under code_before AND failed under code_after}| /
                     max(|tests passed under code_before|, 1)

    Returns None if neither code state runs, or if no tests were specified.
    """
    if not tests:
        return None
    r_before = run_tests_per_test(code_before, tests, file_path)
    r_after = run_tests_per_test(code_after, tests, file_path)
    if r_before.error or r_after.error:
        return None

    passed_before = r_before.passed_set
    passed_after = r_after.passed_set
    if not passed_before:
        return 0.0  # no prior progress to regress

    newly_failed = passed_before - passed_after
    return len(newly_failed) / len(passed_before)


def regression_rate_trajectory(
    attempts: List[Dict[str, Any]],
    tests: List[str],
    file_path: str = "solution.py",
) -> Optional[float]:
    """Mean RegressionRate across consecutive (P_t, P_{t+1}) attempts.

    Each attempt must carry ``code_before`` (the code that was tested at
    that attempt) and ``generated_code`` (the new code). Lacking
    ``code_before``, we infer it from the prior attempt's ``generated_code``.
    """
    if len(attempts) < 2:
        return None
    rates = []
    prev_code = None
    for att in attempts:
        code_before = att.get("code_before") or prev_code
        code_after = att.get("generated_code")
        if code_before and code_after:
            r = regression_rate_for_pair(code_before, code_after, tests, file_path)
            if r is not None:
                rates.append(r)
        prev_code = att.get("generated_code") or prev_code
    if not rates:
        return None
    return mean(rates)


# ----------------------------------------------------------------------
# Per-trajectory slope / R^2
# ----------------------------------------------------------------------

def progress_curve(attempts: List[Dict[str, Any]]) -> List[float]:
    """Reconstruct per-attempt pass ratio ρ_t from attempt logs.

    Looks for ``per_test_results: {idx: bool}``; if absent falls back to
    the all-or-nothing ``success: bool``.
    """
    rhos = []
    for att in attempts:
        per = att.get("per_test_results")
        if isinstance(per, dict) and per:
            rhos.append(sum(1 for v in per.values() if v) / len(per))
        elif "success" in att:
            rhos.append(1.0 if att["success"] else 0.0)
    return rhos


def slope_r2(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """Least-squares slope and R^2 for y over x=1..n. Returns (None, None) if n<2."""
    n = len(values)
    if n < 2:
        return None, None
    xs = list(range(1, n + 1))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    if var_x == 0:
        return 0.0, None
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x
    y_pred = [slope * x + intercept for x in xs]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(values, y_pred))
    ss_tot = sum((y - mean_y) ** 2 for y in values)
    r2 = 1.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    return slope, r2


def per_trajectory_slope_r2(attempts: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    """Slope and R^2 of the per-attempt progress curve."""
    return slope_r2(progress_curve(attempts))


# ----------------------------------------------------------------------
# Repeats / Test-Without-Edit
# ----------------------------------------------------------------------

def _hash_code(code: str) -> str:
    return hashlib.sha1(code.encode("utf-8", errors="replace")).hexdigest()


def repeated_submissions(attempts: List[Dict[str, Any]]) -> int:
    """Count attempts whose generated_code matches any prior attempt."""
    seen = set()
    repeats = 0
    for att in attempts:
        code = att.get("generated_code") or ""
        if not code:
            continue
        h = _hash_code(code)
        if h in seen:
            repeats += 1
        seen.add(h)
    return repeats


def count_test_without_edit(attempts: List[Dict[str, Any]]) -> int:
    """Count attempts where the generated_code is byte-identical to the
    immediately preceding attempt's generated_code (model re-tested without
    editing — wasted turn signal).

    Renamed from ``test_without_edit`` to avoid pytest treating it as a test
    when imported into test modules.
    """
    twe = 0
    prev = None
    for att in attempts:
        code = att.get("generated_code") or ""
        if prev is not None and code and code == prev:
            twe += 1
        if code:
            prev = code
    return twe


# Backward-compat alias (kept short so any caller that imported the old name
# still works). Marked __test__=False so pytest does not collect it.
test_without_edit = count_test_without_edit
test_without_edit.__test__ = False  # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Span helpers — convert injection metadata into active span ranges
# ----------------------------------------------------------------------

def active_spans_from_entry(
    entry: Dict[str, Any],
    turn_id: Any,
    radius: int = 3,
) -> List[Tuple[int, int]]:
    """Resolve the active fault line spans for a given turn.

    Looks up ``entry['active_faults_per_turn'][str(turn_id)]`` if present
    and maps each active injection_id back to its anchor_line. Falls back
    to "all injections at this turn" (multi-turn) or "all injections"
    (single-turn) if no active labels are stored.

    Returns a list of (start_line, end_line) tuples; each is anchor_line ±
    radius (clamped at 1).
    """
    afpt = entry.get("active_faults_per_turn") or {}
    active_ids = set(afpt.get(str(turn_id), []))

    # Build inj_id → anchor_line map across both schemas.
    inj_lines: Dict[str, int] = {}
    for inj in entry.get("injections", []) or []:
        line = inj.get("anchor", {}).get("anchor_line") or inj.get("location", {}).get("line_approx")
        if line is None:
            continue
        inj_id = inj.get("injection_id") or f"anon@L{line}"
        inj_lines[inj_id] = int(line)
    for turn in entry.get("conversation_history") or []:
        if str(turn.get("turn_id")) != str(turn_id):
            continue
        for inj in turn.get("injections", []) or []:
            line = inj.get("anchor", {}).get("anchor_line")
            if line is None:
                continue
            inj_id = (
                inj.get("injection_id")
                or inj.get("anchor", {}).get("anchor_func_name")
                or f"anon@L{line}"
            )
            inj_lines.setdefault(inj_id, int(line))

    # If we have active labels, use them; otherwise fall back to all
    # injections whose turn_id matches.
    if active_ids:
        lines = [v for k, v in inj_lines.items() if k in active_ids]
    else:
        lines = []
        for inj in entry.get("injections") or []:
            line = inj.get("anchor", {}).get("anchor_line") or inj.get("location", {}).get("line_approx")
            tid = inj.get("turn_id")
            if line is not None and (tid is None or str(tid) == str(turn_id)):
                lines.append(int(line))

    return [(max(1, ln - radius), ln + radius) for ln in lines]
