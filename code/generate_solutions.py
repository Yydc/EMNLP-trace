#!/usr/bin/env python3
"""
TraceBench Solution Generator (Harness-validated)
-------------------------------------------------
Generates Python solutions from CodeFlowBench problems, then executes the
dataset's tracebench tests via the local harness to keep only passing outputs.

Key choices:
- C++ aware: detokenizes CodeFlowBench C++ snippets before translation.
- Test-aware prompts: injects sample tests and calling conventions into the LLM.
- Harness validation: every candidate is executed against provided tests.
"""

import argparse
import ast
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Run `pip install requests`.")
    sys.exit(1)

try:
    from harness import TestHarness
except ImportError:
    print("Error: 'harness.py' not found in current directory.")
    sys.exit(1)


class LLMClient:
    """Thin wrapper to talk to multiple providers."""

    ENV_MAP = {
        "together": "TOGETHER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",  # aka GEMINI_API_KEY
    }

    def __init__(self, provider: str, model: str, api_key: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._resolve_api_key(provider)
        if not self.api_key:
            raise ValueError(f"{self.ENV_MAP.get(provider, 'API_KEY')} is not set.")

    def _resolve_api_key(self, provider: str) -> Optional[str]:
        env_var = self.ENV_MAP.get(provider)
        if provider == "gemini":
            return os.getenv("GEMINI_API_KEY") or os.getenv(env_var, None)
        return os.getenv(env_var, None)

    def chat(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int, request_timeout: int = 60) -> str:
        if self.provider == "together":
            return self._call_together(messages, temperature, max_tokens, request_timeout)
        if self.provider == "openai":
            return self._call_openai(messages, temperature, max_tokens, request_timeout)
        if self.provider == "anthropic":
            return self._call_anthropic(messages, temperature, max_tokens, request_timeout)
        if self.provider == "gemini":
            return self._call_gemini(messages, temperature, max_tokens, request_timeout)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _call_together(self, messages, temperature, max_tokens, request_timeout) -> str:
        url = "https://api.together.xyz/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        res = requests.post(url, headers=headers, json=payload, timeout=request_timeout)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    def _call_openai(self, messages, temperature, max_tokens, request_timeout) -> str:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        # codex/davinci/babbage are non-chat models, use /v1/completions
        is_codex_model = "codex" in self.model.lower() or self.model in ["davinci-002", "babbage-002"]

        if is_codex_model:
            # Use legacy completions API for non-chat models
            url = f"{base_url}/completions"
            prompt_text = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
            payload = {
                "model": self.model,
                "prompt": prompt_text,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            res = requests.post(url, headers=headers, json=payload, timeout=60)
            if not res.ok:
                raise RuntimeError(f"OpenAI completions API error {res.status_code}: {res.text}")
            return res.json()["choices"][0]["text"]

        # For chat models (gpt-4, gpt-3.5-turbo, etc.)
        url = f"{base_url}/chat/completions"

        # GPT-5 series uses max_completion_tokens and may have special params
        is_gpt5 = self.model.startswith("gpt-5")
        token_param = "max_completion_tokens" if is_gpt5 else "max_tokens"

        payload = {
            "model": self.model,
            "messages": messages,
            token_param: max_tokens,
        }

        # GPT-5.1 reasoning models only support temperature=1 (default)
        # Don't send temperature parameter for GPT-5 models
        if not is_gpt5 and temperature is not None:
            payload["temperature"] = temperature

        # GPT-5.1 supports reasoning_effort parameter for speed/intelligence tradeoff
        if is_gpt5 and os.getenv("GPT5_REASONING_EFFORT"):
            payload["reasoning_effort"] = os.getenv("GPT5_REASONING_EFFORT")

        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if not res.ok:
            raise RuntimeError(f"OpenAI chat API error {res.status_code}: {res.text}")
        return res.json()["choices"][0]["message"]["content"]

    def _call_anthropic(self, messages, temperature, max_tokens) -> str:
        # Anthropic: system is separate; wrap content in text parts
        system_prompts = [m["content"] for m in messages if m["role"] == "system"]
        sys_prompt = "\n\n".join(system_prompts)
        filtered = [m for m in messages if m["role"] != "system"]
        anthro_messages = [
            {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
            for m in filtered
        ]
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        url = f"{base_url}/v1/messages"
        payload = {
            "model": self.model,
            "messages": anthro_messages,
            "system": sys_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
        }
        res = requests.post(url, headers=headers, json=payload, timeout=request_timeout)
        if not res.ok:
            raise RuntimeError(f"Anthropic API error {res.status_code}: {res.text[:200]}")
        data = res.json()
        content = data.get("content", [])
        if content and isinstance(content[0], dict):
            return content[0].get("text", "")
        return ""

    def _call_gemini(self, messages, temperature, max_tokens, request_timeout) -> str:
        # Gemini uses a single prompt string; concatenate roles for simplicity
        joined = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": joined}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        res = requests.post(url, params=params, json=payload, timeout=request_timeout)
        res.raise_for_status()
        data = res.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
        return ""


class SolutionGenerator:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
        provider: str = "together",
    ):
        self.model = model
        self.provider = provider
        self.llm = LLMClient(provider=provider, model=model, api_key=api_key)

    def _detokenize_cpp(self, content: str) -> str:
        """
        CodeFlowBench stores C++ tokens line-by-line. This flattens and applies
        a few fixes (includes, std:: spacing) to make it more readable.
        """
        text = content.replace("\\n", "\n").replace("\\t", "\t")
        flattened = " ".join(text.split())
        replacements = {
            "< bits / stdc ++ . h >": "<bits/stdc++.h>",
            "< bits / stdc . h >": "<bits/stdc++.h>",
            "# include": "#include",
            "std ::": "std::",
        }
        for old, new in replacements.items():
            flattened = flattened.replace(old, new)
        # Re-introduce newlines around structural tokens to improve readability for LLMs
        flattened = re.sub(r"(;)(?=\s)", r"\1\n", flattened)
        flattened = re.sub(r"\{\s*", "{\n", flattened)
        flattened = re.sub(r"\}\s*", "}\n", flattened)
        flattened = re.sub(r"\n+", "\n", flattened)
        flattened = flattened.replace("\n#", "\n\n#")  # space out includes/macros a bit
        return flattened.strip()

    def _find_cpp_solution(self, problem: Dict[str, Any]) -> Optional[str]:
        candidates = []
        if "solutions" in problem and isinstance(problem["solutions"], list):
            candidates.extend(problem["solutions"])
        if "reference_code" in problem:
            candidates.append({"content": problem["reference_code"], "type": "code"})

        for sol in candidates:
            if sol.get("type") != "code":
                continue
            content = sol.get("content", "")
            if not content or len(content) < 50:
                continue

            detok = self._detokenize_cpp(content)
            normalized = detok.replace("\n", " ")

            has_include = "#include" in normalized
            has_headers = any(h in normalized for h in ["<iostream>", "<bits/stdc++.h>", "< bits / stdc", "<vector>"])
            has_cpp_keywords = any(kw in normalized for kw in ["using namespace std", "cout", "cin", "endl"])
            is_python = "def " in content and ":" in content

            if has_include and (has_headers or has_cpp_keywords) and not is_python:
                return detok
        return None

    def _extract_cpp_signatures(self, cpp_code: str) -> Dict[str, List[str]]:
        """
        Roughly parse C++ function definitions to recover parameter names.
        This is heuristic but better than guessing from tests.
        """
        sigs: Dict[str, List[str]] = {}
        if not cpp_code:
            return sigs
        pattern = re.compile(
            r"(?:long\\s+long|int|void|double|float|auto|bool|vector<.*?>|string|ll)\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*\\(([^)]*)\\)"
        )
        for match in pattern.finditer(cpp_code):
            name = match.group(1)
            params = match.group(2).strip()
            if name.startswith("operator"):
                continue
            if params == "":
                sigs[name] = []
                continue
            parts = [p.strip() for p in params.split(",") if p.strip()]
            names: List[str] = []
            for p in parts:
                tokens = p.split()
                if tokens:
                    names.append(tokens[-1].replace("&", "").replace("*", ""))
            sigs[name] = names
        return sigs

    def _count_args_from_string(self, raw_input: str) -> Optional[int]:
        """
        Heuristic top-level comma counter for cases where ast.literal_eval fails
        (e.g., defaultdict(...), custom Point(...)). Returns None if unsure.
        """
        if not isinstance(raw_input, str):
            return None
        text = raw_input.strip()
        if not (text.startswith("(") and text.endswith(")")):
            return None

        depth = 0
        count_commas = 0
        for ch in text[1:-1]:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                count_commas += 1
        # If no commas, it could still be a single-arg tuple "(x,)".
        if count_commas == 0:
            if text.endswith(",)"):
                return 1
            return None
        return count_commas + 1

    def _infer_signature(self, subproblem: Dict[str, Any], cpp_sigs: Optional[Dict[str, List[str]]] = None) -> Tuple[str, int, bool, bool]:
        """
        Infer a reasonable function signature from the first test.
        Returns (signature, argc, io_mode, multiline_output_flag).
        """
        name = subproblem.get("name", "func")
        tests = subproblem.get("test_code", [])

        raw_input = tests[0].get("input", "") if tests else ""
        raw_output = tests[0].get("output", "") if tests else ""

        if cpp_sigs and name in cpp_sigs:
            param_names = cpp_sigs[name] or []
            argc = len(param_names)
            params = ", ".join(param_names) if param_names else ""
        else:
            argc = 1
            if tests:
                try:
                    parsed = ast.literal_eval(raw_input)
                    if isinstance(parsed, tuple):
                        argc = len(parsed)
                    else:
                        argc = 1
                except Exception:
                    heuristic = self._count_args_from_string(raw_input)
                    if heuristic:
                        argc = heuristic
            params = ", ".join(f"arg{i+1}" for i in range(argc))

        # Harness IO mode heuristic (matches harness.py)
        io_mode = isinstance(raw_input, str) and raw_input.strip().startswith("['")

        signature = f"def {name}({params}):"

        multiline_output = isinstance(raw_output, str) and "\n" in raw_output
        return signature, argc, io_mode, multiline_output

    def _format_test_examples(self, problem: Dict[str, Any], limit: int = 5) -> str:
        lines: List[str] = []
        for sp in problem.get("subproblems", []):
            name = sp.get("name", "func")
            tests = sp.get("test_code", [])[:limit]
            for t in tests:
                inp = t.get("input", "")
                out = t.get("output", "")
                lines.append(f"{name}{inp} -> {out}")
        return "\n".join(lines)

    def _expected_argc(self, problem: Dict[str, Any]) -> Dict[str, int]:
        """Return expected positional arg counts from test inputs."""
        expected: Dict[str, int] = {}
        for sp in problem.get("subproblems", []):
            name = sp.get("name", "func")
            tests = sp.get("test_code", [])
            if not tests:
                continue
            raw_input = tests[0].get("input", "")
            try:
                parsed = ast.literal_eval(raw_input)
                if isinstance(parsed, tuple):
                    expected[name] = len(parsed)
                else:
                    expected[name] = 1
            except Exception:
                heuristic = self._count_args_from_string(raw_input)
                expected[name] = heuristic if heuristic else None
        return expected

    def _format_subproblem_tests(self, sp: Dict[str, Any]) -> str:
        tests = sp.get("test_code", []) or []
        lines = []
        for idx, t in enumerate(tests, 1):
            lines.append(f"{idx}) input={t.get('input','')}  expected={t.get('output','')}")
        return "\n".join(lines)

    def create_prompt(self, problem: Dict[str, Any], feedback: Optional[str] = None) -> str:
        title = problem.get("title", "Unknown")
        description = problem.get("problem-description", "")[:2000]
        subproblems = problem.get("subproblems", [])
        attempt_hint = problem.get("_attempt_hint")

        cpp_code = self._find_cpp_solution(problem)
        cpp_sigs = self._extract_cpp_signatures(cpp_code) if cpp_code else {}

        sig_infos = [self._infer_signature(sp, cpp_sigs=cpp_sigs) for sp in subproblems]
        req_funcs = [sig for sig, _, _, _ in sig_infos]
        req_funcs_str = "\n".join(req_funcs)
        test_examples = self._format_test_examples(problem)

        # Per-function constraints and hints
        func_hints: List[str] = []
        builtin_conflicts = []
        for sp, sig_info in zip(subproblems, sig_infos):
            name = sp.get("name", "func")
            signature, argc, io_mode, multiline_output = sig_info
            if name in {"set", "list", "dict", "str", "int"}:
                builtin_conflicts.append(name)
            call_example = ""
            tests = sp.get("test_code", [])
            if tests:
                call_example = f"example call: {name}{tests[0].get('input','')} -> {tests[0].get('output','')}"
            output_note = "Return string with '\\n' separators exactly as in expected output." if multiline_output else ""
            if io_mode:
                io_note = "IO MODE: receives full stdin string as a single argument; parse manually and return the exact output string."
            else:
                io_note = f"Functional MODE: called as {name}(*args) with exactly {argc} positional args; do NOT change arity or add defaults."
            func_hints.append(f"- {signature}  ({io_note}) {output_note} {call_example}".strip())

        conflict_warning = ""
        if builtin_conflicts:
            conflict_warning = (
                "\n⚠️  Some function names shadow Python builtins; you must still define them with exactly these names: "
                + ", ".join(sorted(builtin_conflicts))
                + ". Do not rename."
            )

        common_rules = f"""
**Runner Expectations**
- Each function is invoked exactly with the positional args inferred below. Do NOT change parameter counts, add defaults, or use *args/**kwargs.
- If IO MODE is indicated, the harness passes the entire stdin contents as one string argument; parse it yourself and return the full output string (respect newlines).
- If expected output contains newlines, return the string with '\\n' separators exactly as shown.
- No placeholder logic; implement the actual algorithm so tests pass.
- Keep all work inside functions; do not perform I/O, parsing, or main-flow execution at import time.
- Do NOT wrap outputs in extra lists/tuples; return the scalar/string exactly as expected.
- Avoid unsafe parsing: never use eval; in IO mode, parse integers with split/strip.
- This is a translation task: preserve the original algorithm/loops/conditions; do NOT simplify or change the approach. Keep modular arithmetic, prefix sums, DP, binary search, etc., exactly as in the C++ code.

**Required function signatures:**
{req_funcs_str}

**Per-function calling notes:**
{os.linesep.join(func_hints)}

{conflict_warning}

**Example tests (from dataset):**
{test_examples}
"""

        if feedback:
            feedback_block = f"\n\nPrevious attempt failed. Analyze and fix based on the details below:\n{feedback}\n"
        else:
            feedback_block = ""

        if cpp_code:
            print("    [Strategy] 🔵 Translating C++ to Python")
            prompt = f"""You are an expert competitive programmer. Translate the C++ solution to Python 3 that passes the tests.

**Problem**: {title}
**Attempt**: {attempt_hint or 1}
**Description**: {description}

**C++ Source (token-normalized)**:
```cpp
{cpp_code[:12000]}
```

{common_rules}{feedback_block}
Output ONLY the Python code block."""
        else:
            print("    [Strategy] 🟠 Generating from scratch (no C++ found)")
            prompt = f"""You are an expert competitive programmer. Implement the Python 3 solution that passes the tests.

**Problem**: {title}
**Attempt**: {attempt_hint or 1}
**Description**: {description}

{common_rules}{feedback_block}
Output ONLY the Python code block."""

        return prompt

    def generate(
        self,
        problem: Dict[str, Any],
        feedback: Optional[str] = None,
        temperature: float = 0.35,
        max_tokens: int = 4000,
        request_timeout: int = 60,
    ) -> Optional[str]:
        prompt = self.create_prompt(problem, feedback=feedback)
        messages = [
            {"role": "system", "content": "You are a competitive programming expert. Return real, executable Python code."},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(3):
            try:
                content = self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens, request_timeout=request_timeout)
                return self._clean(content)
            except Exception as e:
                print(f"    ⚠️  LLM Error (attempt {attempt+1}): {str(e)[:80]}")
                time.sleep(1)
        return None

    def _clean(self, content: str) -> str:
        if "```python" in content:
            return content.split("```python")[1].split("```")[0].strip()
        if "```" in content:
            return content.split("```")[1].split("```")[0].strip()
        return content.strip()

    def validate_solution(self, solution: str, problem: Dict[str, Any]) -> Tuple[bool, str]:
        if not solution or len(solution) < 50:
            return False, "Code too short"

        if "result = result + i" in solution or "# 初始化变量" in solution:
            return False, "Skeleton code detected"

        expected_argc = self._expected_argc(problem)

        try:
            tree = ast.parse(solution)
        except SyntaxError as e:
            return False, f"Syntax Error: {e}"

        # Required only for subproblems that have tests; others are best-effort
        required = {sp["name"] for sp in problem.get("subproblems", []) if sp.get("test_code")}
        defined_funcs = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        missing = required - set(defined_funcs.keys())

        if missing and "solve" in missing and "main" in defined_funcs:
            print("    🔧 Auto-fix: Renaming main() -> solve()")
            solution = solution.replace("def main(", "def solve(")
            try:
                tree = ast.parse(solution)
                defined_funcs = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
                missing = required - set(defined_funcs.keys())
            except SyntaxError as e:
                return False, f"Syntax Error after rename: {e}"

        if missing:
            return False, f"Missing functions: {missing}"

        # Arity check against test expectations (skip if varargs present)
        for fname, node in defined_funcs.items():
            if fname not in expected_argc:
                continue
            exp = expected_argc[fname]
            if exp is None:
                continue
            if node.args.vararg:
                continue
            actual = len([a for a in node.args.args if a.arg != "self"])
            if actual != exp:
                return False, f"Arity mismatch for {fname}: expected {exp}, got {actual}"

        return True, solution


def main():
    parser = argparse.ArgumentParser(description="Generate Python solutions for CodeFlowBench")
    parser.add_argument("-i", "--input", required=True, help="Input JSON file")
    parser.add_argument("-o", "--output", type=str, help="Output JSON file")
    parser.add_argument("-n", "--num-problems", type=int, default=10, help="Number of problems to process")
    parser.add_argument("--start-index", type=int, default=1, help="1-based start index in the input list")
    parser.add_argument("--retries", type=int, default=3, help="Max LLM attempts per problem (with feedback after first failure)")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8")
    parser.add_argument(
        "--provider",
        type=str,
        default="together",
        choices=["together", "openai", "anthropic", "gemini"],
        help="LLM provider backend",
    )
    parser.add_argument("--api-key", type=str, help="Override API key for the selected provider")
    parser.add_argument("--max-tokens", type=int, default=5000, help="Max completion tokens for generation")
    parser.add_argument("--request-timeout", type=int, default=60, help="HTTP request timeout (seconds) for LLM calls")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: Input file {args.input} not found.")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        problems = json.load(f)

    generator = SolutionGenerator(model=args.model, provider=args.provider, api_key=args.api_key)
    harness = TestHarness()

    total = len(problems)
    start_idx = max(0, args.start_index - 1)
    end_idx = start_idx + args.num_problems if args.num_problems else total
    target_indices = list(range(start_idx, min(end_idx, total)))

    if not target_indices:
        print("No problems to process with the given start/num settings.")
        return

    print(f"🚀 Starting generation for {len(target_indices)} problems (indices {start_idx+1}..{target_indices[-1]+1})")
    print(f"   Provider: {args.provider} | Model: {args.model}")
    print("-" * 60)

    success_count = 0

    def save_progress():
        if not args.output:
            return
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(problems, f, indent=2, ensure_ascii=False)
        print(f"    💾 Progress saved to {args.output}")

    try:
        for run_idx, prob_idx in enumerate(target_indices, start=1):
            prob = problems[prob_idx]
            pid = prob.get("problem-id", f"Index {prob_idx}")
            print(f"[{run_idx}/{len(target_indices)}] Processing {pid} (original idx {prob_idx+1})...")

            last_solution = None
            last_error = None
            expected_argc = generator._expected_argc(prob)

            for attempt in range(args.retries):
                # Vary prompt slightly across retries to reduce identical outputs
                prob_with_attempt = dict(prob)
                prob_with_attempt["_attempt_hint"] = attempt + 1

                feedback = None
                if attempt > 0 and last_error:
                    # Feed previous error and code back to the model
                    snippet = last_solution if last_solution and len(last_solution) < 3500 else (last_solution[:3500] + "\n# ... (truncated)") if last_solution else ""
                    target_name = None
                    # Extract target function from error text
                    m = re.search(r"Arity mismatch for ([A-Za-z_][A-Za-z0-9_]*)", last_error)
                    if m:
                        target_name = m.group(1)
                    elif ":" in last_error:
                        target_name = last_error.split(":")[0].strip()

                    failing_test = None
                    m_test = re.search(r"test\\s+(\\d+)", last_error, re.IGNORECASE)
                    if m_test:
                        failing_test = int(m_test.group(1))

                    tests_block = ""
                    argc_hint = ""
                    expect_actual = ""
                    m2 = re.search(r"Expected '([^']*)', got '([^']*)'", last_error)
                    if m2:
                        expect_actual = f"Expected={m2.group(1)} ; Got={m2.group(2)}"

                    if target_name:
                        for sp in prob.get("subproblems", []):
                            if sp.get("name") == target_name:
                                tests_block = generator._format_subproblem_tests(sp)
                                if target_name in expected_argc and expected_argc[target_name] is not None:
                                    argc_hint = f"Expected args for {target_name}: {expected_argc[target_name]}"
                                if failing_test and 1 <= failing_test <= len(sp.get("test_code", [])):
                                    failing = sp["test_code"][failing_test - 1]
                                    tests_block = f"Failing test input={failing.get('input','')} expected={failing.get('output','')}\n" + tests_block
                                break

                    feedback_parts = [f"Previous failure: {last_error}"]
                    if argc_hint:
                        feedback_parts.append(argc_hint)
                    if tests_block:
                        feedback_parts.append(f"Tests for {target_name}:\n{tests_block}")
                    if expect_actual:
                        feedback_parts.append(f"Observed diff: {expect_actual}")
                    feedback_parts.append(f"Previous code:\n```python\n{snippet}\n```")
                    feedback = "\n".join(feedback_parts)

                # Temperature schedule to escape local minima while keeping first attempt precise
                temp_schedule = [0.2, 0.35, 0.6]
                temp = temp_schedule[attempt] if attempt < len(temp_schedule) else temp_schedule[-1]
                solution = generator.generate(
                    prob_with_attempt,
                    feedback=feedback,
                    temperature=temp,
                    max_tokens=args.max_tokens,
                    request_timeout=args.request_timeout,
                )
                valid, result = generator.validate_solution(solution or "", prob)

                if not valid:
                    print(f"    ✗ {result}")
                    if attempt + 1 < args.retries:
                        print("    ... Retrying generation ...")
                    continue

                if isinstance(result, str):
                    solution = result

                passed, error_msg = harness.run_all_tests(solution, prob)
                if passed:
                    print("  ✅ Success")
                    prob["solution"] = solution
                    prob["solution_source"] = "LLM-Verified"
                    success_count += 1
                    break

                print(f"    ✗ {error_msg}")
                last_solution = solution
                last_error = error_msg
                if attempt + 1 < args.retries:
                    print("    ... Retrying generation with feedback ...")

            save_progress()
            time.sleep(1)
    finally:
        harness.cleanup()

    print("-" * 60)
    print(f"Finished. Success Rate: {success_count}/{len(target_indices)}")

    if args.output:
        save_progress()
        print(f"Saved final snapshot to {args.output}")


if __name__ == "__main__":
    main()
