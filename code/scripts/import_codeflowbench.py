#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List

def download_codeflowbench():
    """
    Download CodeFlowBench from HuggingFace.
    For now, this is a placeholder - implement actual download.
    """
    try:
        from datasets import load_dataset
        dataset = load_dataset("WaterWang-001/CodeFlowBench-2505")
        return dataset
    except ImportError:
        print("Install datasets: pip install datasets")
        return None

def convert_to_tracebench_format(codeflow_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert CodeFlowBench item to TraceBench task format.
    """
    task_id = f"flow:codeflow:{codeflow_item['id']}"

    track = codeflow_item.get("track", "function")
    if track == "function_flow":
        track = "function_flow"

    task = {
        "task_id": task_id,
        "track": track,
        "title": codeflow_item.get("id", ""),
        "spec_md": codeflow_item.get("spec_md", ""),
        "difficulty": codeflow_item.get("difficulty", "medium"),
        "starter_files": {
            "solution.py": codeflow_item.get("starter_code", "")
        },
        "tests": {
            "unit": {
                "paths": codeflow_item.get("tests", {}).get("unit", [])
            },
            "oracle_turns": codeflow_item.get("tests", {}).get("oracle_turns", 1)
        },
        "rationales": codeflow_item.get("rationales", {}),
        "scenarios": codeflow_item.get("scenarios", {}),
        "shift_tags": [
            f"difficulty:{codeflow_item.get('difficulty', 'medium')}",
            f"track:{track}"
        ],
        "source": "CodeFlowBench"
    }

    return task

def import_codeflowbench(output_dir: str, limit: int = None):
    """
    Import CodeFlowBench dataset and convert to TraceBench format.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    dataset = download_codeflowbench()
    if not dataset:
        print("Using mock data for demonstration")
        return create_mock_codeflow_tasks(output_path)

    tasks_created = 0
    for item in dataset:
        if limit and tasks_created >= limit:
            break

        task = convert_to_tracebench_format(item)
        task_dir = output_path / task["task_id"].replace(":", "__")
        task_dir.mkdir(parents=True, exist_ok=True)

        task_file = task_dir / "task.json"
        with open(task_file, 'w') as f:
            json.dump(task, f, indent=2, ensure_ascii=False)

        if task.get("starter_files"):
            for fname, content in task["starter_files"].items():
                (task_dir / fname).write_text(content, encoding='utf-8')

        tasks_created += 1
        print(f"Created: {task['task_id']}")

    print(f"\nImported {tasks_created} tasks to {output_dir}")
    return tasks_created

def create_mock_codeflow_tasks(output_path: Path) -> int:
    """
    Create mock tasks based on CodeFlowBench format for testing.
    """
    mock_task = {
        "task_id": "flow:codeflow:simple_chunk_list",
        "track": "function",
        "title": "Chunk List Implementation",
        "spec_md": "Implement chunk(arr, k) that splits array into chunks of size k. Raise ValueError if k<=0. Preserve order.",
        "difficulty": "simple",
        "starter_files": {
            "solution.py": """def chunk(arr, k):
    if k == 0:
        return [arr]
    arr.sort()
    out = []
    i = 0
    while i < len(arr):
        out.append(arr[i:i+k])
        i += k
    return out
"""
        },
        "tests": {
            "unit": {
                "paths": ["tests/test_chunk.py"]
            },
            "oracle_turns": 1
        },
        "rationales": {
            "clean": {
                "rid": "R1",
                "content": "If k<=0 raise ValueError. Do not sort. Use slicing."
            },
            "noisy": [
                {
                    "rid": "R2",
                    "noise_type": "partially_correct",
                    "content": "If k<0 use |k|, if 0 use 1."
                },
                {
                    "rid": "R3",
                    "noise_type": "off_task",
                    "content": "Pad last chunk with None for consistency."
                }
            ]
        },
        "scenarios": {
            "one_shot_pass": {
                "expected_turns": 1,
                "success": True
            }
        },
        "shift_tags": ["difficulty:simple", "track:function"],
        "source": "CodeFlowBench:mock"
    }

    task_dir = output_path / mock_task["task_id"].replace(":", "__")
    task_dir.mkdir(parents=True, exist_ok=True)

    with open(task_dir / "task.json", 'w') as f:
        json.dump(mock_task, f, indent=2, ensure_ascii=False)

    (task_dir / "solution.py").write_text(
        mock_task["starter_files"]["solution.py"],
        encoding='utf-8'
    )

    tests_dir = task_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    test_content = """import pytest
from solution import chunk

def test_chunk_basic():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

def test_chunk_preserve_order():
    result = chunk([1, 3, 2], 2)
    assert result == [[1, 3], [2]]

def test_chunk_invalid_k():
    with pytest.raises(ValueError):
        chunk([1, 2], 0)

    with pytest.raises(ValueError):
        chunk([1, 2], -1)

def test_chunk_large_array():
    arr = list(range(100))
    result = chunk(arr, 10)
    assert len(result) == 10
    assert all(len(chunk) == 10 for chunk in result)
"""

    (tests_dir / "test_chunk.py").write_text(test_content, encoding='utf-8')

    print(f"Created mock task: {mock_task['task_id']}")
    return 1

if __name__ == "__main__":
    import sys
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "data/codeflowbench"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    import_codeflowbench(output_dir, limit)
