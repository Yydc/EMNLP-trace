"""Lightweight multi-file dataset generator.

This module derives simple multi-file variants from the existing single-file
CodeFlowBench problems.  It keeps the original logic and tests intact, but
augments the metadata with file assignments so that the evaluation pipeline can
exercise multi-module reasoning and the dedicated multi-file harness.

Design goals:
* deterministic structure – every generated problem contains `main.py` plus a
  small set of helper modules so downstream orchestration stays simple;
* zero impact on original semantics – tests and statements are untouched except
  for the added `file` annotations;
* compatibility with the agent workflow – subproblems continue to look like the
  single-file format, therefore the same prompting logic applies while the
  harness is responsible for creating the multi-file environment.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_FILE_ORDER: Iterable[str] = (
    "main.py",
    "helpers.py",
    "utils.py",
)


def _assign_files_to_subproblems(subproblems: List[Dict], file_cycle: List[str]) -> List[Dict]:
    """Attach a `file` field to each subproblem following a round-robin scheme."""

    assigned: List[Dict] = []
    for idx, subproblem in enumerate(subproblems):
        enriched = copy.deepcopy(subproblem)
        enriched["file"] = file_cycle[idx % len(file_cycle)]
        assigned.append(enriched)
    return assigned


def _build_file_manifest(file_names: List[str]) -> List[Dict]:
    """Create a manifest describing the available files for a problem."""

    manifest: List[Dict] = []
    for name in file_names:
        if name == "main.py":
            purpose = "Entry point orchestrating helper modules"
        elif name == "helpers.py":
            purpose = "Shared helper functions"
        else:
            purpose = "Utility methods reused across modules"
        manifest.append({
            "filename": name,
            "purpose": purpose,
        })
    return manifest


def convert_to_multifile_problem(problem: Dict, *, difficulty: str = "hard") -> Dict:
    """Return a shallow multi-file variant of the given problem."""

    file_list = list(DEFAULT_FILE_ORDER)
    if len(problem.get("subproblems", [])) <= 2:
        file_list = file_list[:2]

    multifile_problem = copy.deepcopy(problem)
    multifile_problem["problem-id"] = f"{problem['problem-id']}_MULTIFILE"
    multifile_problem["is_multifile"] = True
    multifile_problem["multifile_difficulty"] = difficulty
    multifile_problem["files"] = _build_file_manifest(file_list)
    multifile_problem["subproblems"] = _assign_files_to_subproblems(
        problem.get("subproblems", []),
        file_list,
    )

    return multifile_problem


def generate_multifile_dataset(
    input_file: str,
    output_file: str,
    *,
    difficulty: str = "hard",
    num_problems: int = 10,
) -> List[Dict]:
    """Create a multi-file dataset from an existing single-file JSON dataset."""

    source_path = Path(input_file)
    if not source_path.exists():
        raise FileNotFoundError(f"Input dataset not found: {input_file}")

    with source_path.open("r", encoding="utf-8") as fin:
        original = json.load(fin)

    multifile_problems: List[Dict] = []
    for problem in original[:num_problems]:
        multifile_problems.append(
            convert_to_multifile_problem(problem, difficulty=difficulty)
        )

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fout:
        json.dump(multifile_problems, fout, ensure_ascii=False, indent=2)

    return multifile_problems


__all__ = [
    "generate_multifile_dataset",
    "convert_to_multifile_problem",
]




