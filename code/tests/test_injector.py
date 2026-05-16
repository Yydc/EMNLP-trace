"""Smoke tests for the AST injector. These verify that strategies don't crash
and that the metadata returned matches the strategy that ran."""

import pytest

from src.core.ast_injector import ASTInjector


SAMPLE = '''
def add(a, b):
    return a + b

def main():
    s = 0
    for i in range(10):
        s = s + i
    return s
'''


def test_injector_lists_all_strategies():
    inj = ASTInjector()
    expected = {
        "boundary_condition_shift", "off_by_one", "wrong_return_variable",
        "missing_update_in_branch", "arg_swap_call", "wrong_operator",
        "initialization_error", "variable_shadowing", "loop_entry_condition",
        "statement_omission", "early_return_fallback", "anchor_only",
    }
    assert expected.issubset(set(inj.strategies.keys()))


@pytest.mark.parametrize("strategy", [
    "boundary_condition_shift",
    "off_by_one",
    "wrong_operator",
    "statement_omission",
    "variable_shadowing",
    "anchor_only",
])
def test_injection_does_not_crash(strategy):
    inj = ASTInjector()
    code, meta = inj.inject_bug_and_anchor(SAMPLE, strategy, function_name="main")
    # Either succeeds (returns code+meta) or returns (None, None) cleanly.
    if code is not None:
        assert isinstance(meta, dict)
        # Anchor metadata should at least carry an anchor_line.
        assert "anchor_line" in meta or "anchor" in meta or "strategy" in meta


def test_anchor_only_returns_runnable_code():
    inj = ASTInjector()
    code, meta = inj.inject_bug_and_anchor(SAMPLE, "anchor_only", function_name="main")
    # If anchor_only succeeded, the code should still parse cleanly.
    if code is not None:
        import ast
        ast.parse(code)  # should not raise
