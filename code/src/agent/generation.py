import sys
import os

# Prompt templates and code extraction utilities
from src.agent.prompts import PROMPT1, PROMPT2, PROMPT3, PROMPT4, PROMPT5, extract_code

class CodeGenerator:
    """
    负责与大语言模型API通信，生成代码。
    """
    def __init__(self, api_key, api_url):
        self.api_key = api_key
        self.api_url = api_url
        # OpenAI-compatible client (Together/Gateway/OpenAI)
        try:
            import openai
            self.client = openai.OpenAI(api_key=self.api_key, base_url=self.api_url)
        except Exception:
            self.client = None

        # Anthropic native client (for claude models)
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        try:
            import anthropic  # type: ignore
            self.anthropic_client = anthropic.Anthropic(
                api_key=self.anthropic_key,
                base_url=self.anthropic_base,
            ) if self.anthropic_key else None
        except Exception:
            self.anthropic_client = None

    def generate(self, model_name, prompt, max_tokens=4000, temperature=0.6, timeout=None):
        """
        调用API并返回生成的代码。
        """
        if timeout is None:
            timeout = int(os.getenv("TRACEBENCH_API_TIMEOUT", "120"))

        # If using Claude and Anthropic key is available, call Anthropic natively.
        if "claude" in model_name.lower():
            # Try native Anthropic client first
            if self.anthropic_client:
                try:
                    resp = self.anthropic_client.messages.create(
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=[{"role": "user", "content": prompt}],
                        timeout=float(timeout),
                    )
                    text = ""
                    if resp and getattr(resp, "content", None):
                        block = resp.content[0]
                        text = getattr(block, "text", "") if hasattr(block, "text") else block.get("text", "")
                    return extract_code(text or "")
                except Exception as e:
                    print(f"  [!!] Anthropic API error: {e}")
            # Fallback: raw HTTP to Anthropic if key exists
            if self.anthropic_key:
                import requests
                url = f"{self.anthropic_base.rstrip('/')}/v1/messages"
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                headers = {
                    "x-api-key": self.anthropic_key,
                    "Content-Type": "application/json",
                    "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
                }
                try:
                    res = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    res.raise_for_status()
                    data = res.json()
                    content = data.get("content", [])
                    if content and isinstance(content[0], dict):
                        return extract_code(content[0].get("text", "") or "")
                except Exception as e:
                    print(f"  [!!] Anthropic HTTP error: {e}")
            # If all Anthropic paths fail, do not fallback to OpenAI client
            return None

        if not self.client:
            print("  [!!] OpenAI-compatible client not initialized and Anthropic unavailable.")
            return None

        try:
            def do_call(temp_val):
                """Call helper that handles max_tokens / max_completion_tokens differences."""
                try:
                    return self.client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temp_val,
                        top_p=1,
                        frequency_penalty=0,
                        timeout=timeout
                    )
                except Exception as inner_err:
                    msg = str(inner_err)
                    if "max_tokens" in msg and "unsupported" in msg:
                        return self.client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                            max_completion_tokens=max_tokens,
                            temperature=temp_val,
                            top_p=1,
                            frequency_penalty=0,
                            timeout=timeout
                        )
                    raise

            # 首次按请求的 temperature 调用；若模型不支持该温度，回退到默认 1
            try:
                response = do_call(temperature)
            except Exception as inner_err:
                msg = str(inner_err)
                if "temperature" in msg and "unsupported" in msg:
                    response = do_call(1)
                else:
                    raise

            generated_text = response.choices[0].message.content
            return extract_code(generated_text)
        except Exception as e:
            print(f"  [!!] API error: {e}")
            return None


def create_initial_prompt(subproblem, turn_number, overall_turns, problem_description, history):
    """
    构建初次尝试解决子问题时的提示词，使用增强版prompt提升准确率。
    """
    history_all = "\n\n".join(f'```python\n{item}\n```' for item in history) if history else ""

    test_cases = subproblem.get("test_code", [])

    # 构建增强的测试用例说明
    test_case_details = ""
    if test_cases and isinstance(test_cases, list):
        test_case_details = "## Test Cases:\n"
        for idx, tc in enumerate(test_cases[:3], 1):  # 显示前3个测试用例
            inp = tc.get('input', '')
            out = tc.get('output', '')
            test_case_details += f"Test {idx}:\n  Input: {inp}\n  Expected Output: {out}\n"
        test_case_details += "\nIMPORTANT: Your function MUST return/output exactly the Expected Output format.\n"

    # 根据不同阶段选择基础prompt
    if turn_number == 1 and turn_number != overall_turns:
        base_prompt = PROMPT1
        format_args = {
            "problem_description": problem_description,
            "name": subproblem["name"],
            "statement": subproblem["statement"],
            "sample_test_case": test_cases[0] if test_cases else ""
        }
    elif turn_number == overall_turns:
        if subproblem.get("dependencies"):
            base_prompt = PROMPT3
            format_args = {
                "problem_description": problem_description,
                "name": subproblem["name"],
                "statement": subproblem["statement"],
                "dependencies": subproblem["dependencies"],
                "history": history_all
            }
        else:
            base_prompt = PROMPT4
            format_args = {
                "problem_description": problem_description,
                "name": subproblem["name"],
                "statement": subproblem["statement"],
                "history": history_all
            }
    elif subproblem.get("dependencies"):
        base_prompt = PROMPT2
        format_args = {
            "problem_description": problem_description,
            "name": subproblem["name"],
            "statement": subproblem["statement"],
            "dependencies": subproblem["dependencies"],
            "history": history_all,
            "sample_test_case": test_cases[0] if test_cases else ""
        }
    else:
        base_prompt = PROMPT5
        format_args = {
            "problem_description": problem_description,
            "name": subproblem["name"],
            "statement": subproblem["statement"],
            "history": history_all,
            "sample_test_case": test_cases[0] if test_cases else ""
        }

    # 增强指导
    enhanced_guidelines = """

## CRITICAL REQUIREMENTS:
1. Function Signature: Carefully analyze the test cases to determine correct parameter names and types
2. Return Type: Match the exact output format shown in test cases (int, str, list, etc.)
3. Edge Cases: Handle boundary conditions (empty inputs, zero, negative numbers)
4. Dependencies: If dependencies are provided, YOU MUST call them directly - don't reimplement
5. Testing: Mentally verify your code against ALL provided test cases before submitting

## Common Mistakes to AVOID:
- Wrong return type (returning string instead of int, or vice versa)
- Off-by-one errors in loops or ranges
- Not handling empty/None inputs
- Reimplementing dependency functions instead of calling them
- Incorrect variable scoping
"""

    return base_prompt.format(**format_args) + test_case_details + enhanced_guidelines


def create_reflection_prompt(subproblem, problem_description, history, failed_code, error_log):
    """
    当测试失败时，构建一个增强的"反思提示词"，提供详细的调试指导。
    """
    history_all = "\n\n".join(f'```python\n{item}\n```' for item in history) if history else ""

    # 分析错误类型提供针对性建议
    debugging_hints = ""
    if "Output Mismatch" in error_log:
        debugging_hints = """
## Debugging Hints for Output Mismatch:
- Check if your return type matches expected (int vs str vs float)
- Verify you're not adding extra spaces, newlines, or formatting
- Ensure calculations are correct (order of operations, integer division)
- Check if you need to convert types before returning
- Review if you're processing ALL required inputs"""
    elif "TypeError" in error_log:
        debugging_hints = """
## Debugging Hints for TypeError:
- Verify function signature matches test case arguments
- Check if you're calling dependency functions with correct parameters
- Ensure variable types are compatible with operations
- Look for None values that should be initialized"""
    elif "IndexError" in error_log or "KeyError" in error_log:
        debugging_hints = """
## Debugging Hints for Index/Key Error:
- Check array/list bounds before accessing
- Verify loop ranges are correct (0-indexed vs 1-indexed)
- Ensure dictionaries have keys before access
- Check if input data structure matches your assumptions"""
    else:
        debugging_hints = """
## Debugging Hints:
- Read the error message carefully to locate the issue
- Check function signature and parameter usage
- Verify all variables are properly initialized
- Ensure correct use of pre-implemented functions"""

    test_cases = subproblem.get("test_code", [])
    test_case_reminder = ""
    if test_cases:
        test_case_reminder = "\n## ALL Test Cases (Your code MUST pass ALL of them):\n"
        for idx, tc in enumerate(test_cases, 1):
            test_case_reminder += f"Test {idx}: Input={tc.get('input', '')} → Expected={tc.get('output', '')}\n"
        test_case_reminder += "\nVerify your fix passes EVERY test case above!\n"

    REFLECTION_PROMPT = """You are a Programming Expert specializing in debugging and code correction.

## Background of the whole problem:
{problem_description}

## Subproblem Description:
You need to complete the `{name}` function.
{statement}

## Pre-implemented functions (if any):
{history}

## Your Previous Attempt:
```python
{failed_code}
```

## Test Result (FAILED):
```
{error_log}
```
{debugging_hints}
{test_case_reminder}

## Your Task:
1. ANALYZE: Identify the root cause of the error
2. FIX: Correct the bug(s) in your implementation
3. VERIFY: Mentally test against all test cases
4. SUBMIT: Return ONLY the corrected function code

CRITICAL: Focus on fixing the SPECIFIC error shown above. Don't rewrite from scratch unless necessary.

Return your corrected function:
```python
"""
    return REFLECTION_PROMPT.format(
        problem_description=problem_description,
        name=subproblem["name"],
        statement=subproblem["statement"],
        history=history_all,
        failed_code=failed_code,
        error_log=error_log,
        debugging_hints=debugging_hints,
        test_case_reminder=test_case_reminder
    )
