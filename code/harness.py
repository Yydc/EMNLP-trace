#!/usr/bin/env python3
import sys
import os
import ast
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any


class TestHarness:
    """在隔离的子进程中运行生成的代码并验证"""

    def __init__(self, temp_dir: str = "temp_sandbox"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

    def cleanup(self):
        """清理临时文件"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_driver_script(self, solution_module_name: str, func_name: str, is_io_mode: bool) -> str:
        """动态生成 Python 驱动脚本"""
        if is_io_mode:
            # IO 模式: 读取 stdin，传递给函数
            return f"""
import sys
import os
sys.path.append(os.getcwd())
from {solution_module_name} import *

if __name__ == "__main__":
    try:
        input_data = sys.stdin.read()

        if '{func_name}' in globals():
            func = globals()['{func_name}']
            result = func(input_data)
            if result is not None:
                print(str(result).strip())
        else:
            pass  # 找不到入口函数
    except Exception as e:
        print(f"RUNTIME_ERROR: {{e}}", file=sys.stderr)
        sys.exit(1)
"""
        else:
            # Functional 模式: 解析参数后调用函数
            return f"""
import sys
import os
import ast
sys.path.append(os.getcwd())
from {solution_module_name} import *

if __name__ == "__main__":
    try:
        input_str = sys.stdin.read().strip()
        if not input_str:
            sys.exit(0)

        # 安全解析参数
        try:
            args = ast.literal_eval(input_str)
            if not isinstance(args, tuple):
                args = (args,)
        except:
            args = (input_str,)

        func = globals()['{func_name}']
        result = func(*args)

        print(str(result).strip())

    except Exception as e:
        print(f"RUNTIME_ERROR: {{e}}", file=sys.stderr)
        sys.exit(1)
"""

    def run_test_case(self, solution_code: str, subproblem: Dict) -> Tuple[bool, str]:
        """针对单个 subproblem 的测试用例运行验证"""
        unique_id = str(uuid.uuid4()).replace('-', '_')
        sol_filename = f"sol_{unique_id}.py"
        driver_filename = f"driver_{unique_id}.py"

        sol_path = self.temp_dir / sol_filename
        driver_path = self.temp_dir / driver_filename

        # 1. 写入 Solution 文件
        with open(sol_path, 'w', encoding='utf-8') as f:
            f.write(solution_code)

        # 2. 分析测试类型
        test_cases = subproblem.get('test_code', [])
        if not test_cases:
            return True, "No test cases"

        # 限制测试用例数量（避免浪费时间）
        test_cases = test_cases[:5]

        first_input = test_cases[0].get('input', '')
        is_io_mode = isinstance(first_input, str) and first_input.strip().startswith("['")

        # 3. 写入 Driver 文件
        driver_code = self._create_driver_script(sol_filename[:-3], subproblem['name'], is_io_mode)
        with open(driver_path, 'w', encoding='utf-8') as f:
            f.write(driver_code)

        # 4. 循环执行测试用例
        for idx, test in enumerate(test_cases):
            raw_input = test.get('input', '')
            expected_out = str(test.get('output', '')).strip()

            # 准备 stdin 数据
            if is_io_mode:
                try:
                    parsed = ast.literal_eval(raw_input)
                    stdin_data = parsed[0] if isinstance(parsed, list) else raw_input
                except:
                    stdin_data = raw_input.strip("[]'\"")

                # 处理转义字符（关键！）
                stdin_data = stdin_data.replace('\\n', '\n')
            else:
                stdin_data = raw_input

            try:
                cmd = [sys.executable, driver_filename]
                process = subprocess.run(
                    cmd,
                    cwd=self.temp_dir,
                    input=stdin_data,
                    text=True,
                    capture_output=True,
                    timeout=5  # 增加到 5 秒
                )

                if process.returncode != 0:
                    error = process.stderr.strip()[:100]
                    return False, f"Runtime Error (test {idx+1}/{len(test_cases)}): {error}"

                actual_out = process.stdout.strip()

                if actual_out != expected_out:
                    return False, f"Logic Error (test {idx+1}): Expected '{expected_out}', got '{actual_out}'"

            except subprocess.TimeoutExpired:
                return False, f"Timeout (test {idx+1}): Infinite loop or too slow"
            except Exception as e:
                return False, f"System Error: {e}"

        # 清理临时文件
        if sol_path.exists():
            os.remove(sol_path)
        if driver_path.exists():
            os.remove(driver_path)

        return True, f"All {len(test_cases)} tests passed"

    def run_all_tests(self, solution_code: str, problem: Dict) -> Tuple[bool, str]:
        """运行所有 subproblems 的测试"""
        subproblems = problem.get('subproblems', [])

        for sp in subproblems:
            passed, error_msg = self.run_test_case(solution_code, sp)
            if not passed:
                return False, f"{sp['name']}: {error_msg}"

        return True, "All subproblems passed"
