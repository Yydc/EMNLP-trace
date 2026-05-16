"""Unit tests for the metric primitives.

Run with: pytest code/tests/test_metrics.py -v
"""

import pytest

from src.core.metrics_v2 import (
    edited_lines_from_diff,
    outside_g_for_attempt,
    outside_g_trajectory,
    regression_rate_for_pair,
    regression_rate_trajectory,
    progress_curve,
    slope_r2,
    per_trajectory_slope_r2,
    repeated_submissions,
    count_test_without_edit,
    active_spans_from_entry,
)


# ---------- edited_lines_from_diff ----------

def test_edited_lines_single_replace():
    before = "a = 1\nb = 2\nc = 3\n"
    after = "a = 1\nb = 99\nc = 3\n"
    assert edited_lines_from_diff(before, after) == [2]


def test_edited_lines_insert():
    before = "a\nc\n"
    after = "a\nb\nc\n"
    assert 2 in edited_lines_from_diff(before, after)


def test_edited_lines_no_change():
    assert edited_lines_from_diff("x\ny\n", "x\ny\n") == []


# ---------- Outside-G ----------

def test_outside_g_all_inside():
    # All edits within fault region neighborhood → 0.0
    assert outside_g_for_attempt([10, 11, 12], [(10, 12)], neighborhood=3) == pytest.approx(0.0)


def test_outside_g_all_outside():
    # All edits far from fault → 1.0
    assert outside_g_for_attempt([1, 2, 30], [(10, 12)], neighborhood=3) == pytest.approx(1.0)


def test_outside_g_half_outside():
    assert outside_g_for_attempt([10, 30], [(10, 12)], neighborhood=3) == pytest.approx(0.5)


def test_outside_g_no_active_span():
    # Without grounded region, paper convention = 1.0 (every edit outside)
    assert outside_g_for_attempt([1, 2, 3], [], neighborhood=3) == pytest.approx(1.0)


def test_outside_g_trajectory_mean():
    attempts = [
        {"edited_lines": [10]},                # 0.0 (inside)
        {"edited_lines": [100]},               # 1.0 (outside)
        {"edited_lines": []},                  # skip (None)
    ]
    assert outside_g_trajectory(attempts, [(10, 12)]) == pytest.approx(0.5)


# ---------- RegressionRate ----------

def test_regression_rate_pure_regression():
    code_good = "def f(x): return x + 1"
    code_bad = "def f(x): return x + 2"
    tests = ["assert f(1) == 2", "assert f(2) == 3"]
    assert regression_rate_for_pair(code_good, code_bad, tests) == pytest.approx(1.0)


def test_regression_rate_no_regression():
    code = "def f(x): return x + 1"
    tests = ["assert f(1) == 2"]
    assert regression_rate_for_pair(code, code, tests) == pytest.approx(0.0)


def test_regression_rate_partial():
    code_good = "def f(x): return x + 1"
    code_partial = "def f(x):\n    return x + 1 if x < 5 else 0"
    tests = ["assert f(1) == 2", "assert f(5) == 6"]
    # Both pass under good; second fails under partial.
    assert regression_rate_for_pair(code_good, code_partial, tests) == pytest.approx(0.5)


def test_regression_rate_trajectory_handles_missing_fields():
    # If attempts lack code_before / generated_code, return None gracefully.
    attempts = [{"foo": "bar"}, {"baz": "qux"}]
    assert regression_rate_trajectory(attempts, ["assert True"]) is None


# ---------- Per-trajectory slope ----------

def test_progress_curve_from_per_test():
    attempts = [
        {"per_test_results": {0: True, 1: False, 2: False}},
        {"per_test_results": {0: True, 1: True, 2: False}},
        {"per_test_results": {0: True, 1: True, 2: True}},
    ]
    assert progress_curve(attempts) == pytest.approx([1/3, 2/3, 1.0])


def test_progress_curve_falls_back_to_success():
    attempts = [{"success": False}, {"success": True}]
    assert progress_curve(attempts) == [0.0, 1.0]


def test_slope_r2_monotone_increasing():
    slope, r2 = slope_r2([0.0, 0.5, 1.0])
    assert slope == pytest.approx(0.5)
    assert r2 == pytest.approx(1.0)


def test_slope_r2_short_input_returns_none():
    assert slope_r2([0.5]) == (None, None)


def test_per_trajectory_slope_r2_integration():
    attempts = [
        {"per_test_results": {0: False, 1: False}},
        {"per_test_results": {0: True, 1: False}},
        {"per_test_results": {0: True, 1: True}},
    ]
    slope, r2 = per_trajectory_slope_r2(attempts)
    assert slope == pytest.approx(0.5)
    assert r2 == pytest.approx(1.0)


# ---------- Repeats / TWE ----------

def test_repeated_submissions_counts_each_repeat():
    attempts = [
        {"generated_code": "v1"},
        {"generated_code": "v2"},
        {"generated_code": "v1"},  # repeat
        {"generated_code": "v2"},  # repeat
    ]
    assert repeated_submissions(attempts) == 2


def test_count_test_without_edit_only_counts_consecutive():
    attempts = [
        {"generated_code": "v1"},
        {"generated_code": "v1"},  # TWE 1
        {"generated_code": "v2"},
        {"generated_code": "v2"},  # TWE 2
        {"generated_code": "v3"},
    ]
    assert count_test_without_edit(attempts) == 2


def test_repeats_ignores_empty_strings():
    attempts = [{"generated_code": ""}, {"generated_code": ""}, {"generated_code": "v1"}]
    assert repeated_submissions(attempts) == 0


# ---------- Active spans resolution ----------

def test_active_spans_uses_labels_if_present():
    entry = {
        "injections": [
            {"injection_id": "INJ1", "anchor": {"anchor_line": 10}, "turn_id": 1},
            {"injection_id": "INJ2", "anchor": {"anchor_line": 25}, "turn_id": 1},
        ],
        "active_faults_per_turn": {"1": ["INJ1"]},
    }
    spans = active_spans_from_entry(entry, 1)
    # Only INJ1 (line 10) ± 3
    assert spans == [(7, 13)]


def test_active_spans_falls_back_to_all_when_no_labels():
    entry = {
        "injections": [
            {"injection_id": "INJ1", "anchor": {"anchor_line": 10}, "turn_id": 1},
            {"injection_id": "INJ2", "anchor": {"anchor_line": 25}, "turn_id": 1},
        ],
        # no active_faults_per_turn
    }
    spans = active_spans_from_entry(entry, 1)
    assert (7, 13) in spans
    assert (22, 28) in spans
