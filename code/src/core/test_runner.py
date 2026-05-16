"""Per-test execution utility.

The legacy ``traceability_metrics._run_test_bundle`` returns a single
all-or-nothing bool. RegressionRate needs per-test pass/fail to diff the
pass set across edits, so this module provides that primitive.

Public API::

    from src.core.test_runner import run_tests_per_test, TestResult

    result: TestResult = run_tests_per_test(code, tests, file_path="solution.py")
    # result.per_test : Dict[int, bool]   (test_index → pass)
    # result.all_pass : bool
    # result.error    : Optional[str]
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

TEST_TIMEOUT = int(os.getenv("TRACEBENCH_TEST_TIMEOUT", "120"))


@dataclass
class TestResult:
    """Per-test execution outcome.

    Attributes:
        per_test: Map from test_index (0-based, matches order in input list)
                  to pass/fail bool. Missing test_index ⇒ infrastructure error.
        all_pass: True if every test in the input list ran and passed.
        error:    None if the code ran (regardless of test outcome). Non-None
                  if the code itself failed to import, timed out, or otherwise
                  could not be executed.
        stderr:   captured stderr (truncated to 4 KB) — useful for traceback
                  inspection regardless of per-test outcomes.
    """
    per_test: Dict[int, bool] = field(default_factory=dict)
    all_pass: bool = False
    error: Optional[str] = None
    stderr: str = ""

    @property
    def passed_set(self) -> set:
        return {i for i, ok in self.per_test.items() if ok}

    @property
    def failed_set(self) -> set:
        return {i for i, ok in self.per_test.items() if not ok}


def run_tests_per_test(
    code: str,
    tests: List[str],
    file_path: str = "solution.py",
    timeout: int = TEST_TIMEOUT,
) -> TestResult:
    """Execute each test in `tests` independently against `code`.

    Each test is wrapped in a try/except so a single failure does not abort
    later tests. Returns a TestResult with per-test bool. If the code itself
    fails to import (SyntaxError) or times out, returns a TestResult with
    `error` set and `per_test = {}`.
    """
    if not tests:
        return TestResult(per_test={}, all_pass=True, error=None)

    # Build a driver script that runs every test inside its own try/except
    # block, writes one line per test of the form "TEST_RESULT i PASS|FAIL"
    # to stdout, then exits 0.
    driver_lines = [
        "import sys, traceback",
        "RESULTS = {}",
    ]
    for idx, test in enumerate(tests):
        # Escape the test source for safe inclusion. We rely on triple-quote
        # delimiters; reject tests that contain the exact delimiter rather
        # than try to escape recursively.
        safe = test.replace('"""', '\\"\\"\\"')
        driver_lines.append(f"try:")
        # Indent the test body so SyntaxError inside doesn't crash the wrapper.
        driver_lines.append(f"    exec(r'''{safe}''')")
        driver_lines.append(f"    RESULTS[{idx}] = True")
        driver_lines.append(f"except Exception:")
        driver_lines.append(f"    RESULTS[{idx}] = False")
        driver_lines.append(f"    sys.stderr.write('TEST_FAIL {idx}: ' + traceback.format_exc() + chr(10))")
    driver_lines.append("for i, ok in sorted(RESULTS.items()):")
    driver_lines.append("    sys.stdout.write(f'TEST_RESULT {i} {\"PASS\" if ok else \"FAIL\"}\\n')")
    driver = "\n".join(driver_lines)

    try:
        with tempfile.TemporaryDirectory(prefix="tracebench_pertest_") as tmpdir:
            script_name = Path(file_path).name or "candidate.py"
            script_path = Path(tmpdir) / script_name
            script_body = f"{code}\n\nif __name__ == '__main__':\n"
            # Indent the driver body by 4 spaces.
            for ln in driver.splitlines():
                script_body += f"    {ln}\n"
            script_path.write_text(script_body, encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, script_path.name],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        return TestResult(per_test={}, all_pass=False, error="timeout", stderr="")
    except Exception as exc:
        return TestResult(per_test={}, all_pass=False, error=f"runner_exception: {exc}", stderr="")

    # Parse stdout for TEST_RESULT lines.
    per_test: Dict[int, bool] = {}
    for line in (proc.stdout or "").splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0] == "TEST_RESULT":
            try:
                idx = int(parts[1])
                per_test[idx] = parts[2] == "PASS"
            except ValueError:
                continue

    stderr_clip = (proc.stderr or "")[:4096]

    # If we got no TEST_RESULT lines at all, the code itself probably failed
    # to load (SyntaxError, ImportError at module level, etc.).
    if not per_test:
        return TestResult(per_test={}, all_pass=False, error="code_load_failed", stderr=stderr_clip)

    # Fill in any missing test indices as failed (defensive — shouldn't
    # happen if the driver ran to completion).
    for i in range(len(tests)):
        per_test.setdefault(i, False)

    return TestResult(
        per_test=per_test,
        all_pass=all(per_test.values()),
        error=None,
        stderr=stderr_clip,
    )
