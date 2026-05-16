import subprocess
import os
import uuid

def run_test(full_code, subproblem):
    """
    在一个临时的沙箱环境中执行给定的完整代码，并根据子问题的测试用例进行评估。

    Args:
        full_code (str): 包含了所有依赖函数和当前待测函数的完整Python代码。
        subproblem (dict): 当前子问题的数据，包含 'name' 和 'test_code'。

    Returns:
        tuple: (bool, str)
               - bool: 测试是否通过。
               - str: 如果失败，返回详细的错误日志；如果成功，返回stdout。
    """
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # 使用UUID确保临时文件名唯一，并将 '-' 替换为 '_' 使其成为合法的Python模块名
    unique_id = str(uuid.uuid4()).replace('-', '_')
    temp_code_path = os.path.join(temp_dir, f"temp_code_{unique_id}.py")
    test_runner_path = os.path.join(temp_dir, f"test_runner_{unique_id}.py")

    try:
        # 1. 写入包含所有生成代码的临时模块文件
        with open(temp_code_path, 'w', encoding='utf-8') as f:
            f.write(full_code)

        # 2. 根据子问题是中间步骤还是最终步骤，创建不同的测试运行器
        test_case = subproblem['test_code'][0]
        test_input = test_case.get('input', '')

        # 判断是否是最终子问题：如果input以 "['" 开头，则是stdin输入
        is_final_subproblem = isinstance(test_input, str) and test_input.startswith("['")

        if is_final_subproblem:
            # 最终子问题：通常涉及stdin和stdout
            stdin_input = test_input.strip("[]'").replace('\\n', '\n')
            expected_output = test_case['output'].replace('\\n', '\n').strip()

            runner_code = f"""
import sys
from {os.path.splitext(os.path.basename(temp_code_path))[0]} import *

{subproblem['name']}()
"""
            with open(test_runner_path, 'w', encoding='utf-8') as f:
                f.write(runner_code)

            process = subprocess.run(
                ["python3", test_runner_path],
                capture_output=True, text=True, input=stdin_input, timeout=10
            )

        else:
            # 中间子问题：通常是函数调用和返回值检查
            if not subproblem.get('test_code') or not isinstance(subproblem['test_code'], list):
                return False, "Invalid or missing test_code for intermediate subproblem."

            # 从测试用例中提取参数，例如 "(11,)" 或 "(10)"
            function_args = test_input
            function_call = f"{subproblem['name']}{function_args}"
            expected_output = str(test_case.get('output', '')).strip()

            runner_code = f"""
from {os.path.splitext(os.path.basename(temp_code_path))[0]} import *

result = {function_call}
print(result)
"""
            with open(test_runner_path, 'w', encoding='utf-8') as f:
                f.write(runner_code)

            process = subprocess.run(
                ["python3", test_runner_path],
                capture_output=True, text=True, timeout=10
            )

        # 3. 分析执行结果
        if process.returncode != 0:
            error_log = f"Execution Error:\nSTDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
            return False, error_log

        actual_output = process.stdout.strip()
        
        if actual_output == expected_output:
            return True, actual_output
        else:
            error_log = f"Output Mismatch:\nExpected:\n{expected_output}\nGot:\n{actual_output}"
            return False, error_log

    except subprocess.TimeoutExpired:
        return False, "Execution Timed Out (10 seconds)."
    except Exception as e:
        return False, f"An unexpected error occurred in harness: {e}"
    finally:
        # 4. 清理临时文件
        if os.path.exists(temp_code_path):
            os.remove(temp_code_path)
        if os.path.exists(test_runner_path):
            os.remove(test_runner_path)
