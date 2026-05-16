"""Testing utilities for multi-file problems."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Tuple

# 配置日志记录
logger = logging.getLogger(__name__)


class MultiFileHarness:
    """Execute tests for multi-file submissions in an isolated directory."""

    def __init__(self, temp_root: str = "temp_multifile") -> None:
        self.temp_root = Path(temp_root)
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def run_test(
        self,
        file_contents: Dict[str, str],
        subproblem: Dict,
    ) -> Tuple[bool, str]:
        sandbox_id = f"run_{uuid.uuid4().hex}"
        sandbox = self.temp_root / sandbox_id
        sandbox.mkdir(parents=True, exist_ok=True)

        try:
            for filename, code in file_contents.items():
                target = sandbox / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(code, encoding="utf-8")

            (sandbox / "__init__.py").write_text("# auto-generated\n", encoding="utf-8")

            return self._execute_test(sandbox, subproblem)
        except Exception as exc:
            return False, f"Harness Error: {exc}"
        finally:
            if sandbox.exists():
                try:
                    shutil.rmtree(sandbox)
                except Exception as cleanup_error:
                    logger.warning(f"清理沙盒目录失败 {sandbox}: {cleanup_error}")

    # ------------------------------------------------------------------
    def _execute_test(self, sandbox: Path, subproblem: Dict) -> Tuple[bool, str]:
        test_case = subproblem.get("test_code", [{}])[0]
        test_input = test_case.get("input", "")
        expected_output = str(test_case.get("output", "")).strip()

        file_name = subproblem.get("file", "main.py")
        module_name = Path(file_name).stem
        function_name = subproblem.get("name")

        runner_path = sandbox / "_runner.py"

        is_final = isinstance(test_input, str) and test_input.startswith("['")
        if is_final:
            stdin_data = test_input.strip("[]'").replace("\\n", "\n")
            runner_code = f"""
import sys
sys.path.insert(0, '.')
from {module_name} import {function_name}

{function_name}()
"""
            runner_path.write_text(runner_code, encoding="utf-8")
            process = subprocess.run(
                ["python3", runner_path.name],
                cwd=sandbox,
                capture_output=True,
                text=True,
                input=stdin_data,
                timeout=10,
            )
        else:
            runner_code = f"""
import sys
sys.path.insert(0, '.')
from {module_name} import {function_name}

result = {function_name}{test_input}
print(result)
"""
            runner_path.write_text(runner_code, encoding="utf-8")
            process = subprocess.run(
                ["python3", runner_path.name],
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=10,
            )

        if process.returncode != 0:
            return False, f"Execution Error:\nSTDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"

        actual_output = process.stdout.strip()
        if actual_output == expected_output:
            return True, actual_output
        return (
            False,
            f"Output Mismatch:\nExpected:\n{expected_output}\nGot:\n{actual_output}",
        )


__all__ = ["MultiFileHarness"]




