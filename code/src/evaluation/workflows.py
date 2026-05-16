"""Agentic workflow used during evaluation.

This module implements a lightweight self-refinement loop that interacts with
Together API through the shared `agent.generation.CodeGenerator`.  The
implementation mirrors the version used prior to refactoring but now consumes
runtime settings from `config` so the pipeline can be configured without
editing source files.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import sys
from pathlib import Path
# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.generation import (
    CodeGenerator,
    create_initial_prompt,
    create_reflection_prompt,
)
from src.agent.harness import run_test
from src.evaluation.harness import MultiFileHarness
from src.core import config


def solve_problem(problem: Dict[str, Any], code_generator: CodeGenerator, *, model_name: str) -> Tuple[str, bool, Dict[str, Any]]:  # noqa: D401 - passthrough docs
    """Solve a single CodeFlowBench problem using generate-test-reflect loop."""

    verified_history: List[str] = []
    problem_description = problem.get("problem-description", "")
    overall_turns = problem.get("overall-turns", len(problem.get("subproblems", [])))

    detailed_log: Dict[str, Any] = {
        "problem_id": problem.get("problem-id"),
        "problem_description": problem_description,
        "overall_turns": overall_turns,
        "subproblems": [],
        "solved": False,
        "structure_bucket": problem.get("structure_bucket"),
        "temporal_slice": problem.get("temporal_slice"),
        "api_variant": problem.get("api_variant"),
        "boundary_bucket": problem.get("boundary_bucket"),
    }

    for turn_index, subproblem in enumerate(problem.get("subproblems", []), start=1):
        sub_log: Dict[str, Any] = {
            "name": subproblem.get("name"),
            "statement": subproblem.get("statement"),
            "dependencies": subproblem.get("dependencies", []),
            "attempts": [],
            "solved": False,
        }

        temperature = config.INITIAL_TEMPERATURE
        success = False
        last_code = ""
        last_error = ""

        for attempt_idx in range(1, config.MAX_ATTEMPTS + 1):
            if attempt_idx == 1:
                prompt = create_initial_prompt(
                    subproblem,
                    turn_index,
                    overall_turns,
                    problem_description,
                    verified_history,
                )
                attempt_type = "Initial"
            else:
                prompt = create_reflection_prompt(
                    subproblem,
                    problem_description,
                    verified_history,
                    last_code,
                    last_error,
                )
                temperature = min(temperature + config.TEMPERATURE_INCREASE, config.MAX_TEMPERATURE)
                attempt_type = "Reflection"

            generated_code = code_generator.generate(
                model_name,
                prompt,
                temperature=temperature,
            )

            attempt_log: Dict[str, Any] = {
                "attempt_number": attempt_idx,
                "type": attempt_type,
                "temperature": temperature,
                "prompt_tokens": len(prompt.split()),
                "generated_code": generated_code,
            }

            if not generated_code:
                attempt_log["success"] = False
                attempt_log["test_result"] = "LLM returned empty response"
                sub_log["attempts"].append(attempt_log)
                last_error = attempt_log["test_result"]
                continue

            last_code = generated_code
            candidate_code = "\n\n".join(verified_history + [generated_code])
            success, harness_log = run_test(candidate_code, subproblem)
            attempt_log["success"] = success
            attempt_log["test_result"] = harness_log

            # Capture simple evidence map for traceability
            attempt_log["evidence_map"] = _extract_evidence_tokens(harness_log)

            sub_log["attempts"].append(attempt_log)

            if success:
                verified_history.append(generated_code)
                sub_log["solved"] = True
                sub_log["final_code"] = generated_code
                break
            else:
                last_error = harness_log

        if not success:
            detailed_log["subproblems"].append(sub_log)
            return "", False, detailed_log

        detailed_log["subproblems"].append(sub_log)

    detailed_log["solved"] = True
    final_solution = "\n\n".join(verified_history)
    return final_solution, True, detailed_log


def generate_readable_report(detailed_logs: List[Dict[str, Any]], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "detailed_report.md")

    with open(report_path, "w", encoding="utf-8") as fout:
        fout.write("# Agentic Evaluation Report\n\n")
        fout.write(f"Total problems: {len(detailed_logs)}\n\n")

        for log in detailed_logs:
            fout.write(f"## Problem: {log.get('problem_id')}\n\n")
            fout.write(f"### Description\n{log.get('problem_description', '')}\n\n")

            for sub in log.get("subproblems", []):
                fout.write(f"#### Subproblem: {sub.get('name')}\n\n")
                fout.write(f"Status: {'✅' if sub.get('solved') else '❌'}\n\n")
                for attempt in sub.get("attempts", []):
                    fout.write(
                        f"- Attempt {attempt['attempt_number']} ({attempt['type']}, T={attempt['temperature']:.2f})\n"
                    )
                    if attempt.get("generated_code"):
                        fout.write("```python\n" + attempt["generated_code"] + "\n```\n")
                    fout.write("```\n" + str(attempt.get("test_result", "")) + "\n```\n")
                fout.write("\n")

    return report_path


def _extract_evidence_tokens(test_log: str) -> List[str]:
    tokens: List[str] = []
    lower_log = str(test_log).lower()
    for key in config.TRACE_EVIDENCE_KEYS:
        if key in lower_log:
            tokens.append(key)
    return tokens


def solve_multifile_problem(
    problem: Dict[str, Any],
    code_generator: CodeGenerator,
    *,
    model_name: str,
) -> Tuple[Dict[str, str], bool, Dict[str, Any]]:
    """Multi-module variant of :func:`solve_problem`."""

    harness = MultiFileHarness()
    files_meta = problem.get("files") or [{"filename": "main.py"}]
    file_names = [meta.get("filename", "main.py") for meta in files_meta]
    verified_code: Dict[str, List[str]] = {name: [] for name in file_names}

    problem_description = problem.get("problem-description", "")
    overall_turns = problem.get("overall-turns", len(problem.get("subproblems", [])))

    detailed_log: Dict[str, Any] = {
        "problem_id": problem.get("problem-id"),
        "problem_description": problem_description,
        "overall_turns": overall_turns,
        "subproblems": [],
        "solved": False,
        "is_multifile": True,
        "files": file_names,
    }

    for turn_index, subproblem in enumerate(problem.get("subproblems", []), start=1):
        target_file = subproblem.get("file", "main.py")
        sub_log: Dict[str, Any] = {
            "name": subproblem.get("name"),
            "statement": subproblem.get("statement"),
            "dependencies": subproblem.get("dependencies", []),
            "attempts": [],
            "solved": False,
            "file": target_file,
        }

        temperature = config.INITIAL_TEMPERATURE
        success = False
        last_code = ""
        last_error = ""

        for attempt_idx in range(1, config.MAX_ATTEMPTS + 1):
            history_snippets = _build_multifile_history_snippets(verified_code)

            if attempt_idx == 1:
                prompt = create_initial_prompt(
                    subproblem,
                    turn_index,
                    overall_turns,
                    problem_description,
                    history_snippets,
                )
                attempt_type = "Initial"
            else:
                prompt = create_reflection_prompt(
                    subproblem,
                    problem_description,
                    history_snippets,
                    last_code,
                    last_error,
                )
                temperature = min(
                    temperature + config.TEMPERATURE_INCREASE,
                    config.MAX_TEMPERATURE,
                )
                attempt_type = "Reflection"

            generated_code = code_generator.generate(
                model_name,
                prompt,
                temperature=temperature,
            )

            attempt_log: Dict[str, Any] = {
                "attempt_number": attempt_idx,
                "type": attempt_type,
                "temperature": temperature,
                "prompt_tokens": len(prompt.split()),
                "generated_code": generated_code,
            }

            if not generated_code:
                attempt_log["success"] = False
                attempt_log["test_result"] = "LLM returned empty response"
                sub_log["attempts"].append(attempt_log)
                last_error = attempt_log["test_result"]
                continue

            last_code = generated_code
            candidate_files = _compose_candidate_files(verified_code, target_file, generated_code)
            success, harness_log = harness.run_test(candidate_files, subproblem)
            attempt_log["success"] = success
            attempt_log["test_result"] = harness_log
            attempt_log["evidence_map"] = _extract_evidence_tokens(harness_log)
            sub_log["attempts"].append(attempt_log)

            if success:
                verified_code[target_file].append(generated_code)
                sub_log["solved"] = True
                sub_log["final_code"] = generated_code
                break
            else:
                last_error = harness_log

        if not success:
            detailed_log["subproblems"].append(sub_log)
            return {}, False, detailed_log

        detailed_log["subproblems"].append(sub_log)

    detailed_log["solved"] = True
    final_solution = {
        filename: "\n\n".join(chunks).strip()
        for filename, chunks in verified_code.items()
        if chunks
    }
    return final_solution, True, detailed_log


def _build_multifile_history_snippets(verified_code: Dict[str, List[str]]) -> List[str]:
    snippets: List[str] = []
    for filename, pieces in verified_code.items():
        if not pieces:
            continue
        joined = "\n\n".join(pieces)
        snippets.append(f"# File: {filename}\n{joined}")
    return snippets


def _compose_candidate_files(
    verified_code: Dict[str, List[str]],
    target_file: str,
    generated_code: str,
) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for filename, chunks in verified_code.items():
        combined = list(chunks)
        if filename == target_file:
            combined.append(generated_code)
        files[filename] = "\n\n".join(combined).strip()
    return files


__all__ = ["solve_problem", "solve_multifile_problem", "generate_readable_report"]


