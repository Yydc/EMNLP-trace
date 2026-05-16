"""Unit tests for fault-family rollup."""

import pytest

from src.core.fault_families import (
    STRATEGY_TO_FAMILY,
    FAMILY_ORDER,
    family_of,
    family_counts,
    family_counts_by_difficulty,
    render_family_table,
)


def test_family_of_known_strategies():
    assert family_of("off_by_one") == "boundary_off_by_one"
    assert family_of("boundary_condition_shift") == "boundary_off_by_one"
    assert family_of("wrong_operator") == "wrong_op_cond"
    assert family_of("statement_omission") == "omission_missing_branch"
    assert family_of("variable_shadowing") == "dependency_misuse"
    assert family_of("initialization_error") == "corner_case_type"


def test_family_of_unknown_returns_unknown():
    assert family_of("totally_made_up") == "unknown"


def test_family_counts_aggregates():
    entries = [
        {"injections": [{"type": "off_by_one"}, {"type": "wrong_operator"}]},
        {"injections": [{"type": "off_by_one"}]},
    ]
    counts = family_counts(entries)
    assert counts["boundary_off_by_one"] == 2
    assert counts["wrong_op_cond"] == 1


def test_family_counts_by_difficulty_buckets():
    entries = [
        {"difficulty": "easy", "injections": [{"type": "off_by_one"}]},
        {"difficulty": "hard", "injections": [{"type": "off_by_one"}]},
        {"difficulty": "extreme", "injections": [{"type": "wrong_operator"}]},
    ]
    counts = family_counts_by_difficulty(entries)
    assert counts["boundary_off_by_one"]["easy_med"] == 1
    assert counts["boundary_off_by_one"]["hard"] == 1
    assert counts["wrong_op_cond"]["very_hard_plus"] == 1


def test_render_family_table_has_5_data_rows_plus_header():
    entries = [{"difficulty": "easy", "injections": [{"type": "off_by_one"}]}]
    md = render_family_table(entries)
    lines = md.splitlines()
    # header + separator + 5 family rows + total row = 8
    assert len(lines) >= 8


def test_all_strategies_in_ast_injector_are_mapped():
    """Every strategy known to ASTInjector should be in STRATEGY_TO_FAMILY."""
    # Strategies enumerated in src/core/ast_injector.py
    expected = {
        "boundary_condition_shift", "off_by_one", "wrong_return_variable",
        "missing_update_in_branch", "arg_swap_call", "wrong_operator",
        "initialization_error", "variable_shadowing", "loop_entry_condition",
        "statement_omission", "early_return_fallback", "anchor_only",
    }
    missing = expected - set(STRATEGY_TO_FAMILY.keys())
    assert not missing, f"Strategies not mapped to a family: {missing}"
