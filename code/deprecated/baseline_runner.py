#!/usr/bin/env python3
"""
Baseline Runner for TraceBench Evaluation
------------------------------------------
This runner simulates a simple debugging session that:
- In 'baseline' mode: tries to fix errors without tracing information
- In 'error_aware' mode: uses injected error locations to guide fixes

This is a minimal implementation for testing the evaluation pipeline.
For real evaluation, you would replace this with your actual debugging agent.
"""

from typing import Any, Dict, Optional
import random


def run_debug_session(entry: Dict[str, Any], mode: str = "baseline", max_turns: int = 5) -> Dict[str, Any]:
    """
    Simulate a multi-turn debugging session on a TraceBench entry.

    Args:
        entry: TraceBench entry containing:
            - problem_id: str
            - code_context: dict with original_code, file_path, etc.
            - injected_errors: list of injected error info
            - subproblems: list of subproblem definitions
            - test_cases: list of test cases
        mode: "baseline" or "error_aware"
        max_turns: Maximum debugging turns allowed

    Returns:
        problem_log: Dict containing debugging session results
    """
    problem_id = entry.get("problem_id", "unknown")
    injected_errors = entry.get("injected_errors", [])
    subproblems = entry.get("subproblems", [])
    test_cases = entry.get("test_cases", [])

    # Initialize session state
    solved = False
    first_success_turn = None
    turn_results = []

    # Simulate debugging turns
    for turn in range(1, max_turns + 1):
        # In baseline mode: random chance of fixing errors (simulates blind debugging)
        # In error_aware mode: higher chance if we "use" the error locations
        if mode == "error_aware":
            # Simulate using error trace information
            success_rate = 0.7 if injected_errors else 0.3
        else:
            # Baseline has lower success rate (no error information)
            success_rate = 0.3

        # Simulate attempting to fix each subproblem
        turn_solved = random.random() < success_rate

        turn_result = {
            "turn": turn,
            "solved": turn_solved,
            "attempts": [
                {
                    "success": turn_solved,
                    "test_result": "PASSED" if turn_solved else "FAILED: output mismatch",
                }
            ],
        }
        turn_results.append(turn_result)

        if turn_solved and not solved:
            solved = True
            first_success_turn = turn
            break

    # Construct problem log matching expected format
    problem_log = {
        "problem_id": problem_id,
        "mode": mode,
        "solved": solved,
        "first_success_turn": first_success_turn,
        "total_turns": len(turn_results),
        "subproblems": turn_results,
    }

    return problem_log


def run_debug_session_with_oracle(entry: Dict[str, Any], mode: str = "baseline", max_turns: int = 5) -> Dict[str, Any]:
    """
    Oracle runner that uses the original correct solution.
    This should achieve 100% success rate in turn 1.

    Use this to verify the evaluation pipeline is working correctly.
    """
    problem_id = entry.get("problem_id", "unknown")

    # Oracle: we have the correct solution, so we always succeed in turn 1
    problem_log = {
        "problem_id": problem_id,
        "mode": mode,
        "solved": True,
        "first_success_turn": 1,
        "total_turns": 1,
        "subproblems": [
            {
                "turn": 1,
                "solved": True,
                "attempts": [
                    {
                        "success": True,
                        "test_result": "PASSED",
                    }
                ],
            }
        ],
    }

    return problem_log


if __name__ == "__main__":
    # Test the runner with a dummy entry
    dummy_entry = {
        "problem_id": "test_001",
        "injected_errors": [{"line": 10, "type": "off_by_one"}],
        "subproblems": [{"name": "solve", "depth": 1}],
    }

    print("Testing baseline runner...")
    result = run_debug_session(dummy_entry, mode="baseline", max_turns=5)
    print(f"Result: {result}")

    print("\nTesting oracle runner...")
    oracle_result = run_debug_session_with_oracle(dummy_entry, mode="baseline", max_turns=5)
    print(f"Oracle Result: {oracle_result}")
