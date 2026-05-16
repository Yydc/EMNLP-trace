"""Unit tests for the active-fault labeler."""

import pytest

from src.core.active_fault_labeler import (
    _apply_counterfactual_lines,
    _build_full_code,
    _is_active_with_cf,
    label_entry,
)


def test_apply_counterfactual_replaces_window():
    corrupted = "a\nb_BUG\nc\nd\n"
    clean = "a\nb_OK\nc\nd\n"
    out = _apply_counterfactual_lines(corrupted, clean, inj_line=2, radius=0)
    assert out.splitlines()[1] == "b_OK"


def test_apply_counterfactual_respects_radius():
    corrupted = "a\nb_BUG\nc\nd\n"
    clean = "a\nb_OK\nc_OK\nd\n"
    out = _apply_counterfactual_lines(corrupted, clean, inj_line=2, radius=1)
    # Lines 1, 2, 3 (0-indexed) are reverted = a, b, c
    assert out.splitlines()[1] == "b_OK"
    assert out.splitlines()[2] == "c_OK"


def test_build_full_code_handles_empty_context():
    assert _build_full_code("", "x = 1") == "x = 1"
    assert _build_full_code("y = 2", "") == "y = 2"
    assert _build_full_code("y = 2", "x = 1") == "y = 2\n\nx = 1"


def test_is_active_classification():
    corrupted = "def f(x): return x + 9999"
    cf = "def f(x): return x + 1"
    tests = ["assert f(1) == 2"]
    label, _ = _is_active_with_cf(corrupted, cf, tests, "solution.py")
    assert label == "active"


def test_is_active_no_failure_returns_no_failure_label():
    code = "def f(x): return x + 1"
    tests = ["assert f(1) == 2"]
    label, _ = _is_active_with_cf(code, code, tests, "solution.py")
    assert label == "inactive_no_failure"


def test_is_active_cf_no_fix_when_revert_doesnt_help():
    # Both fail.
    bad = "def f(x): return 99"
    other_bad = "def f(x): return 100"
    tests = ["assert f(1) == 2"]
    label, _ = _is_active_with_cf(bad, other_bad, tests, "solution.py")
    # Should not be "active" because revert doesn't fix the failure.
    assert label != "active"


def test_label_entry_single_turn_legacy_schema():
    entry = {
        "code_context": {"corrupted_code": "def f(x): return x + 9999", "file_path": "s.py"},
        "original_code": "def f(x): return x + 1",
        "injections": [{
            "injection_id": "INJ_LEGACY",
            "anchor": {"anchor_line": 1},
        }],
        "evaluation": {"test_cases": ["assert f(1) == 2"]},
    }
    labels = label_entry(entry)
    # Turn 0 should claim INJ_LEGACY as active.
    assert labels.get("0") == ["INJ_LEGACY"]


def test_label_entry_empty_schema_returns_empty():
    assert label_entry({}) == {}
