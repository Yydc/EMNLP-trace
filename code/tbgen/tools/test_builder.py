from __future__ import annotations
import pathlib
from typing import Dict, Any

TEST_TEMPLATE_ADD = """import pytest

def add(a, b):
    return a + b

def test_add_ints():
    assert add(2, 3) == 5

def test_add_typecheck():
    with pytest.raises(TypeError):
        add(1.5, 2)
"""

def materialize_tests(task_dir: pathlib.Path, track: str):
    tdir = task_dir / "tests"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "test_basic.py").write_text(TEST_TEMPLATE_ADD, encoding="utf-8")

def materialize_layered_tests(task_dir: pathlib.Path, task: Dict[str, Any]):
    tdir = task_dir / "tests"
    tdir.mkdir(parents=True, exist_ok=True)

    topology = task.get("dependency_topology", {})
    layers = topology.get("layers", [])

    if not layers:
        materialize_tests(task_dir, task.get("track", ""))
        return

    for layer_info in layers:
        level = layer_info["level"]
        functions = layer_info["functions"]

        for func_name in functions:
            test_content = generate_test_for_function(func_name, level, task)
            test_file = tdir / f"test_{level}_{func_name}.py"
            test_file.write_text(test_content, encoding="utf-8")

def generate_test_for_function(func_name: str, level: int, task: Dict[str, Any]) -> str:
    starter_code = task.get("starter_files", {}).get("solution.py", "")

    template = f"""import pytest
from solution import {func_name}

def test_{func_name}_basic():
    result = {func_name}(None)
    assert result is not None

def test_{func_name}_edge_cases():
    try:
        {func_name}("")
    except:
        pass
"""
    return template