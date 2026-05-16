"""Regression test for finding #4 / patch #5.

Asserts that ``multi_model_runner.run_multi_turn_debug_session`` actually
enters the repair loop and accumulates tokens on a ``multi_turn=True``
entry. Before patch #5 the call site used ``run_debug_session`` (single-turn)
which short-circuited with ``total_attempts=0`` because the tests live at
``conversation_history[i].test_cases``, not at ``evaluation.test_cases``.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# multi_model_runner.py lives at code/; tracebench_runner.py too.
sys.path.insert(0, str(REPO_ROOT / "code"))
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))

import pytest


@pytest.fixture
def multi_turn_entry():
    """Two-turn entry where every turn carries a guaranteed-failing test."""
    return {
        "problem_id": "TEST001",
        "trace_id": "test-trace",
        "multi_turn": True,
        "code_context": {"file_path": "solution.py"},
        "conversation_history": [
            {
                "turn_id": 0,
                "subproblems": ["f"],
                "context": "",
                "target_code": "def f():\n    return 0\n",
                "has_error": True,
                "test_cases": ["assert False, 'forced fail turn 0'"],
            },
            {
                "turn_id": 1,
                "subproblems": ["g"],
                "context": "",
                "target_code": "def g():\n    return 0\n",
                "has_error": True,
                "test_cases": ["assert False, 'forced fail turn 1'"],
            },
        ],
    }


def test_multi_turn_runner_actually_calls_llm(monkeypatch, multi_turn_entry):
    """The runner must enter the repair loop; token totals must match call count."""
    import multi_model_runner as mmr

    calls = {"n": 0}

    def fake_generate(self, prompt, temperature=0.35, max_tokens=4096):
        calls["n"] += 1
        self.last_usage = {"input_tokens": 100, "output_tokens": 50}
        return "```python\ndef f():\n    return 1\n```"

    monkeypatch.setattr(mmr.MultiModelGenerator, "generate", fake_generate)

    result = mmr.run_multi_turn_debug_session(
        multi_turn_entry,
        mode="baseline",
        max_turns=2,
        provider="qwen",        # MultiModelGenerator(provider="qwen") needs no real key
        model="fake-model",
        temperature=0.2,
        max_attempts_per_turn=3,
    )

    assert calls["n"] >= 1, "fake generator never called — silent vacuous-success regressed"
    assert result["total_attempts"] >= 1, f"expected >=1 attempt, got {result['total_attempts']}"
    assert result["total_input_tokens"] == 100 * calls["n"], (
        f"input token total mismatch: {result['total_input_tokens']} vs {100 * calls['n']}"
    )
    assert result["total_output_tokens"] == 50 * calls["n"], (
        f"output token total mismatch: {result['total_output_tokens']} vs {50 * calls['n']}"
    )

    assert len(result["turn_results"]) >= 1
    for ts in result["turn_results"]:
        assert ts["attempts"] >= 1, f"turn {ts.get('turn')} recorded 0 attempts"

    for field in (
        "problem_id", "provider", "model", "solved",
        "total_turns", "total_attempts",
        "total_input_tokens", "total_output_tokens",
        "turn_results", "subproblems",
    ):
        assert field in result, f"missing required output field: {field}"


def test_multi_turn_runner_handles_empty_history():
    """Empty conversation_history should return zeros, not crash."""
    import multi_model_runner as mmr

    entry = {
        "problem_id": "EMPTY",
        "multi_turn": True,
        "code_context": {"file_path": "solution.py"},
        "conversation_history": [],
    }
    result = mmr.run_multi_turn_debug_session(
        entry, mode="baseline", provider="qwen", model="fake-model",
    )
    assert result["solved"] is False
    assert result["total_attempts"] == 0
    assert result["total_input_tokens"] == 0
    assert result["total_output_tokens"] == 0
    assert result["turn_results"] == []
