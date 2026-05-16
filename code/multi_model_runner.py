#!/usr/bin/env python3
"""
Multi-Model TraceBench Runner

"""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import difflib
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from dataclasses import asdict

# Import core components from existing codebase
from src.core.error_aware import ControlPlan, ErrorAwareController
from src.core.risk_analyzer import RiskAnalyzer, Span


class MultiModelGenerator:
    """Provider-agnostic LLM generator for TraceBench evaluation.

    Switches between Together (Qwen), Anthropic (Claude), and OpenAI (GPT-x).
    """

    def __init__(self, provider: str = "qwen", model: Optional[str] = None):
        """
        初始化代码生成器

        Args:
            provider: "qwen" (Together), "claude" (Anthropic), "openai"
            model: 模型名称，如果为 None 则使用默认值
        """
        self.provider = provider.lower()

        # Token usage from the most recent generate() call.
        # Caller (run_debug_session) reads this after each call to accumulate
        # totals for BudgetGuard.
        self.last_usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

        # 默认模型配置
        if model:
            self.model = model
        elif self.provider == "qwen":
            self.model = "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"
        elif self.provider == "claude":
            self.model = "claude-sonnet-4-5-20250929"
        elif self.provider == "openai":
            self.model = "gpt-4o"
        elif self.provider == "google":
            self.model = "gemini-2.5-pro"
        elif self.provider == "local":
            # When pointing at a local vLLM server, the model name is whatever
            # vLLM was launched with. Caller should set it explicitly.
            self.model = os.getenv("TRACEBENCH_LOCAL_MODEL", "local-model")
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # API 配置
        self._setup_api()

    def _setup_api(self):
        """设置 API 配置"""
        if self.provider == "qwen":
            self.api_key = os.getenv("TOGETHER_API_KEY") or os.getenv("OPENAI_API_KEY") or "EMPTY"
            # Allow override to a local vLLM endpoint via TOGETHER_API_BASE.
            self.api_url = os.getenv("TOGETHER_API_BASE", "https://api.together.xyz/v1")

        elif self.provider == "claude":
            self.api_key = os.getenv("ANTHROPIC_API_KEY")
            if not self.api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is required for Claude")

        elif self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                raise RuntimeError("OPENAI_API_KEY is required for OpenAI")

        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY is required for Gemini")

        elif self.provider == "local":
            # vLLM / OpenAI-compatible server hosted locally.
            self.api_key = os.getenv("OPENAI_API_KEY", "EMPTY")
            self.api_url = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")

        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def generate(self, prompt: str, temperature: float = 0.35, max_tokens: int = 4096) -> str:
        """
        生成代码

        Args:
            prompt: 提示词
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            生成的文本
        """
        if self.provider in ("qwen", "local"):
            return self._generate_openai_compatible(prompt, temperature, max_tokens)
        elif self.provider == "claude":
            return self._generate_claude(prompt, temperature, max_tokens)
        elif self.provider == "openai":
            return self._generate_openai(prompt, temperature, max_tokens)
        elif self.provider == "google":
            return self._generate_google(prompt, temperature, max_tokens)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _generate_openai_compatible(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """使用 OpenAI-compatible API (Together)"""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required. Install: pip install openai")

        client = OpenAI(api_key=self.api_key, base_url=self.api_url)

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            usage = getattr(response, "usage", None)
            self.last_usage = {
                "input_tokens":  getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            }
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"Error calling {self.provider} API: {e}", file=sys.stderr)
            self.last_usage = {"input_tokens": 0, "output_tokens": 0}
            return ""

    def _generate_claude(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """使用 Anthropic Claude API"""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package required. Install: pip install anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            usage = getattr(response, "usage", None)
            self.last_usage = {
                "input_tokens":  getattr(usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            }
            return response.content[0].text if response.content else ""
        except Exception as e:
            print(f"Error calling Claude API: {e}", file=sys.stderr)
            self.last_usage = {"input_tokens": 0, "output_tokens": 0}
            return ""

    def _generate_openai(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """使用 OpenAI API"""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required. Install: pip install openai")

        client = OpenAI(api_key=self.api_key)
        # Optional seed for reproducibility (paper bootstrap CI uses this).
        seed_env = os.getenv("TRACEBENCH_SEED")
        kwargs = {}
        if seed_env:
            try:
                kwargs["seed"] = int(seed_env)
            except ValueError:
                pass

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            usage = getattr(response, "usage", None)
            self.last_usage = {
                "input_tokens":  getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            }
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"Error calling OpenAI API: {e}", file=sys.stderr)
            self.last_usage = {"input_tokens": 0, "output_tokens": 0}
            return ""

    def _generate_google(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """使用 Google Gemini API (google-generativeai SDK).

        Reads GOOGLE_API_KEY (or GEMINI_API_KEY). Defaults to gemini-2.5-pro.
        Disables thinking_tokens to avoid stealth-cost from Gemini 2.5's
        chain-of-thought; if you want reasoning, override at call site.
        """
        try:
            from google import generativeai as genai  # type: ignore
        except ImportError:
            try:
                # Newer SDK path.
                from google import genai  # type: ignore
            except ImportError:
                raise RuntimeError(
                    "google-generativeai>=0.8 required. Install: pip install google-generativeai"
                )

        # Map our `temperature` and `max_tokens` to the SDK's GenerationConfig.
        # The legacy `google.generativeai` and the new `google.genai` SDKs
        # have slightly different surfaces; try each.
        def _capture_gemini_usage(resp) -> None:
            meta = getattr(resp, "usage_metadata", None)
            self.last_usage = {
                "input_tokens":  getattr(meta, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
            }

        try:
            # Newer SDK (`from google import genai`)
            client = genai.Client(api_key=self.api_key)  # type: ignore[attr-defined]
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            _capture_gemini_usage(response)
            return getattr(response, "text", None) or ""
        except (AttributeError, TypeError):
            pass

        # Fall back to the legacy SDK.
        try:
            genai.configure(api_key=self.api_key)  # type: ignore[attr-defined]
            mdl = genai.GenerativeModel(self.model)  # type: ignore[attr-defined]
            response = mdl.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            _capture_gemini_usage(response)
            return getattr(response, "text", "") or ""
        except Exception as e:
            print(f"Error calling Gemini API: {e}", file=sys.stderr)
            self.last_usage = {"input_tokens": 0, "output_tokens": 0}
            return ""


def extract_code(text: str) -> str:
    """从 LLM 响应中提取代码块"""
    if "```python" in text:
        parts = text.split("```python")
        if len(parts) > 1:
            code_part = parts[1].split("```")[0]
            return code_part.strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].strip()
    return text.strip()


def _with_line_numbers(code: str) -> str:
    """为代码添加行号"""
    lines = code.splitlines()
    return "\n".join(f"{idx+1:4d}: {line}" for idx, line in enumerate(lines))


def _get_anchor_lines(entry: Dict[str, Any]) -> List[int]:
    """提取 anchor 行号"""
    anchors: List[int] = []
    for inj in entry.get("injections", []) or []:
        anchor = inj.get("anchor", {}) or {}
        loc = anchor.get("anchor_line") or inj.get("location", {}).get("line_approx")
        try:
            if loc is not None:
                anchors.append(int(loc))
        except (TypeError, ValueError):
            continue
    return anchors


def _build_anchor_notes(entry: Dict[str, Any]) -> str:
    """构建 anchor 提示信息"""
    parts: List[str] = []
    for inj in entry.get("injections", []) or []:
        anchor = inj.get("anchor") or {}
        func = anchor.get("anchor_func_name")
        line = anchor.get("anchor_line")
        tracer = anchor.get("anchor_value")
        if func or line or tracer:
            parts.append(f"{func or 'anchor'}@L{line} → {tracer or ''}".strip())
    return "; ".join(parts) if parts else "None"


def _build_prompt(
    entry: Dict[str, Any],
    current_code: str,
    tests: List[str],
    plan: ControlPlan,
    mode: str,
    last_failure: str,
    suspicious_spans: List[Span],
) -> str:
    """构建调试提示词"""
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")
    allowed = plan.allowed_edit_regions or []
    allowed_text = (
        "; ".join(f"L{s.start_line}-{s.end_line}" for s in allowed)
        if allowed
        else "No hard restriction"
    )

    suspicion_text = (
        "; ".join(f"L{s.start_line}-{s.end_line} (score={s.score:.2f})" for s in suspicious_spans)
        if suspicious_spans
        else "Not provided"
    )

    test_preview = "\n".join(f"- {t}" for t in tests[:5]) if tests else "Tests embedded in the provided assertions."
    failure_section = last_failure.strip() if last_failure else "No test executed yet. Propose a fix and make sure all assertions pass."

    anchor_notes = _build_anchor_notes(entry)

    prompt = f"""You are debugging the Python file `{file_path}`.
Mode: {mode}. Your goal is to produce a minimal patch that makes all tests pass.
Allowed edit regions: {allowed_text}
Suspicious regions (high score = more likely root cause): {suspicion_text}
Anchor hints: {anchor_notes}

Tests to satisfy:
{test_preview}

Last failing trace/output:
{failure_section}

Current code (with line numbers):
{_with_line_numbers(current_code)}

Return the full corrected file. Use a single ```python``` block. Do not include explanations."""
    return prompt


def _compute_patch_spans(old_code: str, new_code: str, file_path: str) -> List[Dict[str, Any]]:
    """计算 patch spans"""
    spans: List[Dict[str, Any]] = []
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            added = max(1, j2 - j1)
            start = max(1, i1 + 1)
            end = start + added - 1
        else:
            start = i1 + 1
            end = max(start, i2)
        spans.append({"file_path": file_path, "start_line": start, "end_line": end})
    if not spans:
        spans.append({"file_path": file_path, "start_line": 1, "end_line": 1})
    return spans


def _spans_to_json(spans: List[Span]) -> List[Dict[str, Any]]:
    """将 Span 对象转换为 JSON"""
    return [asdict(s) for s in spans]


def _extract_anchor_hits(stdout: str, entry: Dict[str, Any]) -> List[int]:
    """从运行输出中提取 anchor hits"""
    hits: List[int] = []
    if "ANCHOR_HIT" not in stdout:
        return hits
    anchor_lines = _get_anchor_lines(entry)
    if anchor_lines:
        hits.extend(anchor_lines)
    return hits


def _run_tracebench_tests(
    code: str, file_path: str, tests: List[str], entry: Dict[str, Any]
) -> Tuple[bool, str, str, List[int]]:
    """运行 TraceBench 测试"""
    if not tests:
        return True, "No tests provided", "", []

    with tempfile.TemporaryDirectory(prefix="tracebench_") as tmpdir:
        script_name = Path(file_path).name or "candidate.py"
        script_path = Path(tmpdir) / script_name
        main_block = "\n".join(f"    {t}" for t in tests)
        script_body = f"{code}\n\nif __name__ == '__main__':\n{main_block or '    pass'}\n"
        script_path.write_text(script_body, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, script_path.name],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=30,
        )

    combined_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    anchor_hits = _extract_anchor_hits(proc.stdout or "", entry)
    return proc.returncode == 0, combined_output.strip(), proc.stderr or "", anchor_hits


def run_debug_session(
    entry: Dict[str, Any],
    mode: str = "baseline",
    max_turns: int = 5,
    provider: str = "qwen",
    model: Optional[str] = None,
    temperature: float = 0.35,
) -> Dict[str, Any]:
    """
    运行多轮调试会话

    Args:
        entry: TraceBench 条目
        mode: "baseline" 或 "error_aware"
        max_turns: 最大轮数
        provider: "qwen", "claude", 或 "openai"
        model: 模型名称 (可选)
        temperature: 温度参数

    Returns:
        problem_log: 包含调试会话结果的字典
    """
    generator = MultiModelGenerator(provider=provider, model=model)
    analyzer = RiskAnalyzer()
    controller = ErrorAwareController()

    problem_id = entry.get("trace_id") or entry.get("problem_id", "unknown")
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")
    tests = entry.get("evaluation", {}).get("test_cases") or []
    baseline_code = entry.get("code_context", {}).get("corrupted_code", "")

    # Seed anchors only for error-aware mode
    anchor_lines = _get_anchor_lines(entry) if mode == "error_aware" else []

    current_code = baseline_code
    previous_code = baseline_code
    failure_streak = 0
    last_trace = ""
    first_success_turn = None
    solved = False

    # Run initial check on corrupted code
    initial_success, initial_output, initial_trace, initial_hits = _run_tracebench_tests(
        baseline_code, file_path, tests, entry
    )
    if initial_success:
        solved = True
        last_trace = initial_output
    else:
        last_trace = initial_trace or initial_output
        failure_streak = 1
        if mode == "error_aware":
            anchor_lines = sorted(set(anchor_lines + initial_hits))

    sub_log: Dict[str, Any] = {
        "name": Path(file_path).stem,
        "attempts": [],
        "solved": False,
    }

    if solved:
        sub_log["solved"] = True
        return {
            "problem_id": problem_id,
            "mode": mode,
            "provider": provider,
            "model": generator.model,
            "solved": True,
            "first_success_turn": 0,
            "total_turns": 0,
            "total_attempts": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "turn_results": [],
            "subproblems": [sub_log],
            "file_path": file_path,
        }

    attempt_counter = 0
    total_input_tokens = 0
    total_output_tokens = 0
    turn_results: List[Dict[str, Any]] = []
    turn = 0  # ensure defined if loop body never runs

    for turn in range(1, max_turns + 1):
        turn_input_tokens = 0
        turn_output_tokens = 0
        turn_attempts = 0
        turn_solved = False
        state = {
            "file_path": Path(file_path).name,
            "last_test_output": last_trace,
            "anchor_hits": anchor_lines if mode == "error_aware" else [],
            "failure_streak": failure_streak,
        }
        risk_vector = analyzer.build_risk_vector(state)

        if mode == "error_aware":
            plan = controller.make_control_plan(risk_vector)
            suspicious_spans = risk_vector.suspicious_spans
            if not suspicious_spans and anchor_lines:
                suspicious_spans = [
                    Span(file_path=file_path, start_line=ln, end_line=ln, score=0.9)
                    for ln in anchor_lines
                ]
        else:
            total_lines = max(1, len(current_code.splitlines()))
            plan = ControlPlan(
                allowed_edit_regions=[Span(file_path=file_path, start_line=1, end_line=total_lines, score=0.1)],
                temperature=max(temperature, 0.2),
                top_k=32,
                num_candidates=1,
                structured_prompt=True,
                enable_rollback=False,
            )
            suspicious_spans = risk_vector.suspicious_spans

        if not plan.allowed_edit_regions:
            total_lines = max(1, len(current_code.splitlines()))
            plan.allowed_edit_regions = [Span(file_path=file_path, start_line=1, end_line=total_lines, score=0.1)]

        prompt = _build_prompt(
            entry=entry,
            current_code=current_code,
            tests=tests,
            plan=plan,
            mode=mode,
            last_failure=last_trace,
            suspicious_spans=suspicious_spans,
        )

        for _ in range(plan.num_candidates):
            attempt_counter += 1
            turn_attempts += 1
            raw_resp = generator.generate(prompt, temperature=plan.temperature)
            # Capture token usage reported by the provider for this call.
            call_in  = int(generator.last_usage.get("input_tokens", 0) or 0)
            call_out = int(generator.last_usage.get("output_tokens", 0) or 0)
            total_input_tokens  += call_in
            total_output_tokens += call_out
            turn_input_tokens   += call_in
            turn_output_tokens  += call_out

            candidate_code = extract_code(raw_resp or "") if raw_resp else ""

            attempt_log: Dict[str, Any] = {
                "attempt_number": attempt_counter,
                "turn": turn,
                "mode": mode,
                "provider": provider,
                "model": generator.model,
                "temperature": plan.temperature,
                "prompt_tokens": len(prompt.split()),
                "input_tokens":  call_in,
                "output_tokens": call_out,
                "blame_spans": _spans_to_json(suspicious_spans),
            }

            if not candidate_code:
                attempt_log["success"] = False
                attempt_log["test_result"] = "LLM returned empty response"
                sub_log["attempts"].append(attempt_log)
                failure_streak += 1
                last_trace = "LLM returned empty response"
                continue

            success, output, trace, anchor_hits = _run_tracebench_tests(candidate_code, file_path, tests, entry)

            attempt_log.update(
                {
                    "success": success,
                    "test_result": output,
                    "generated_code": candidate_code,
                    "patch_spans": _compute_patch_spans(previous_code, candidate_code, file_path),
                }
            )

            sub_log["attempts"].append(attempt_log)

            current_code = candidate_code
            previous_code = candidate_code

            if success:
                solved = True
                turn_solved = True
                sub_log["solved"] = True
                first_success_turn = first_success_turn or turn
                break

            failure_streak += 1
            last_trace = trace or output
            if mode == "error_aware":
                anchor_lines = sorted(set(anchor_lines + anchor_hits))

        turn_results.append({
            "turn": turn,
            "attempts": turn_attempts,
            "solved": turn_solved,
            "input_tokens":  turn_input_tokens,
            "output_tokens": turn_output_tokens,
        })

        if solved:
            break

    problem_log = {
        "problem_id": problem_id,
        "mode": mode,
        "provider": provider,
        "model": generator.model,
        "solved": solved,
        "first_success_turn": first_success_turn,
        "total_turns": turn,
        "total_attempts": attempt_counter,
        "total_input_tokens":  total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "turn_results": turn_results,
        "subproblems": [sub_log],
        "file_path": file_path,
    }
    return problem_log


def run_multi_turn_debug_session(
    entry: Dict[str, Any],
    mode: str = "baseline",
    max_turns: int = 5,
    provider: str = "qwen",
    model: Optional[str] = None,
    temperature: float = 0.35,
    max_attempts_per_turn: int = 3,
) -> Dict[str, Any]:
    """Real multi-turn debug session against a MultiModelGenerator.

    Mirrors tracebench_runner.run_multi_turn_debug_session (line 299): walks
    entry["conversation_history"] turn-by-turn, reads per-turn test_cases /
    target_code / context / subproblems, accumulates code across turns, and
    enters a max_attempts_per_turn repair loop on failure.

    Differs only in that it talks to MultiModelGenerator (provider switching +
    last_usage token capture) instead of CodeGenerator (Together/Anthropic only).

    All multi_turn=True entries in tracebench_full.json store their tests at
    conversation_history[i].test_cases, NOT at evaluation.test_cases. The
    single-turn run_debug_session above mis-reads the latter and short-circuits;
    use this function for any multi_turn=True data.
    """
    # Deferred import: tracebench_runner triggers a side-effect print at import
    # time, and we only need two helpers it owns.
    from tracebench_runner import _build_multi_turn_prompt, _anchor_alignment_score

    generator = MultiModelGenerator(provider=provider, model=model)

    problem_id = entry.get("trace_id") or entry.get("problem_id", "unknown")
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")
    conversation_history = entry.get("conversation_history", [])[:max_turns]

    if not conversation_history:
        return {
            "problem_id": problem_id, "mode": mode,
            "provider": provider, "model": generator.model,
            "solved": False, "first_success_turn": None,
            "total_turns": 0, "total_attempts": 0,
            "total_input_tokens": 0, "total_output_tokens": 0,
            "turn_results": [], "subproblems": [],
            "file_path": file_path,
            "error": "No conversation history in multi-turn entry",
        }

    dialogue_chain: List[Dict[str, Any]] = []
    accumulated_code = entry.get("code_context", {}).get("corrupted_code", "") or ""
    turn_summaries: List[Dict[str, Any]] = []
    subproblems_log: List[Dict[str, Any]] = []
    total_attempts = 0
    total_input_tokens = 0
    total_output_tokens = 0
    all_tests: List[str] = []
    first_success_turn: Optional[int] = None

    for turn_idx, turn_data in enumerate(conversation_history):
        turn_id = turn_data.get("turn_id", turn_idx)
        context = turn_data.get("context", "") or ""
        expected_target = turn_data.get("target_code", "") or ""
        has_injected_error = turn_data.get("has_error", False)
        subproblems_funcs = turn_data.get("subproblems", []) or []
        test_cases = turn_data.get("test_cases", []) or []

        if test_cases:
            all_tests.extend(test_cases)

        turn_result: Dict[str, Any] = {
            "turn_id": turn_id,
            "subproblems": subproblems_funcs,
            "has_injected_error": has_injected_error,
            "solved": False,
            "attempts": [],
        }

        turn_input_tokens = 0
        turn_output_tokens = 0
        turn_attempt_count = 0
        turn_solved = False
        last_trace = ""

        task_desc = f"Implement the following functions: {', '.join(subproblems_funcs)}"
        if context:
            task_desc += f"\n\nYou can use the previously implemented code:\n```python\n{context}\n```"

        current_code = expected_target
        context_seed = accumulated_code if accumulated_code else context
        full_code = context_seed + "\n\n" + current_code if context_seed else current_code

        success, output, trace, anchor_hits = _run_tracebench_tests(
            full_code, f"turn_{turn_id}.py", test_cases, entry
        )

        if success:
            turn_solved = True
            turn_result["solved"] = True
            accumulated_code = full_code
            dialogue_chain.append({
                "turn": turn_id, "role": "user",
                "content": task_desc + "\n\nImplement these functions to pass the tests.",
            })
            dialogue_chain.append({
                "turn": turn_id, "role": "assistant",
                "content": f"```python\n{current_code}\n```",
            })
        else:
            last_trace = trace or output
            anchor_hits = anchor_hits or []
            seed_anchors = _get_anchor_lines(entry) if mode == "error_aware" else []

            for attempt_idx in range(max_attempts_per_turn):
                total_attempts += 1
                turn_attempt_count += 1

                prompt = _build_multi_turn_prompt(
                    entry=entry,
                    turn_id=turn_id,
                    task_desc=task_desc,
                    current_code=full_code,
                    tests=test_cases,
                    last_failure=last_trace,
                    dialogue_history=dialogue_chain,
                    mode=mode,
                    anchor_hits=sorted(set(seed_anchors + anchor_hits)),
                )

                candidate_code = ""
                candidate_spans: List[Dict[str, Any]] = []
                raw_resp = ""
                call_in = 0
                call_out = 0

                if mode == "error_aware":
                    num_samples = 3
                    best_score = -1.0
                    for _ in range(num_samples):
                        sample_temp = min(0.8, temperature + 0.1)
                        resp = generator.generate(prompt, temperature=sample_temp)
                        s_in = int(generator.last_usage.get("input_tokens", 0) or 0)
                        s_out = int(generator.last_usage.get("output_tokens", 0) or 0)
                        total_input_tokens += s_in
                        total_output_tokens += s_out
                        turn_input_tokens += s_in
                        turn_output_tokens += s_out
                        call_in = s_in  # remember last for attempt_log
                        call_out = s_out
                        code = extract_code(resp or "") if resp else ""
                        if not code:
                            continue
                        spans = _compute_patch_spans(full_code, code, f"turn_{turn_id}.py")
                        score = _anchor_alignment_score(spans, anchor_hits)
                        if score > best_score:
                            best_score = score
                            candidate_code = code
                            candidate_spans = spans
                            raw_resp = resp
                    if not candidate_code:
                        raw_resp = generator.generate(prompt, temperature=temperature)
                        call_in = int(generator.last_usage.get("input_tokens", 0) or 0)
                        call_out = int(generator.last_usage.get("output_tokens", 0) or 0)
                        total_input_tokens += call_in
                        total_output_tokens += call_out
                        turn_input_tokens += call_in
                        turn_output_tokens += call_out
                        candidate_code = extract_code(raw_resp or "") if raw_resp else ""
                        candidate_spans = (
                            _compute_patch_spans(full_code, candidate_code, f"turn_{turn_id}.py")
                            if candidate_code else []
                        )
                else:
                    raw_resp = generator.generate(prompt, temperature=temperature)
                    call_in = int(generator.last_usage.get("input_tokens", 0) or 0)
                    call_out = int(generator.last_usage.get("output_tokens", 0) or 0)
                    total_input_tokens += call_in
                    total_output_tokens += call_out
                    turn_input_tokens += call_in
                    turn_output_tokens += call_out
                    candidate_code = extract_code(raw_resp or "") if raw_resp else ""
                    candidate_spans = (
                        _compute_patch_spans(full_code, candidate_code, f"turn_{turn_id}.py")
                        if candidate_code else []
                    )

                edited_lines: List[int] = []
                if candidate_code:
                    try:
                        b_lines = full_code.splitlines()
                        a_lines = candidate_code.splitlines()
                        m = difflib.SequenceMatcher(a=b_lines, b=a_lines)
                        for tag, i1, i2, j1, j2 in m.get_opcodes():
                            if tag == "equal":
                                continue
                            if tag in ("replace", "insert"):
                                edited_lines.extend(range(j1 + 1, j2 + 1))
                            else:
                                edited_lines.append(max(1, j1 + 1))
                        edited_lines = sorted(set(edited_lines))
                    except Exception:
                        pass

                attempt_log: Dict[str, Any] = {
                    "attempt_number": total_attempts,
                    "turn": turn_id,
                    "attempt_in_turn": attempt_idx,
                    "mode": mode,
                    "provider": provider,
                    "model": generator.model,
                    "temperature": temperature,
                    "input_tokens": call_in,
                    "output_tokens": call_out,
                    "blame_spans": candidate_spans,
                    "raw_response": raw_resp,
                    "code_before": full_code,
                    "edited_lines": edited_lines,
                }

                if not candidate_code:
                    attempt_log["success"] = False
                    attempt_log["test_result"] = "LLM returned empty response"
                    turn_result["attempts"].append(attempt_log)
                    last_trace = "LLM returned empty response"
                    continue

                success, output, trace, anchor_hits = _run_tracebench_tests(
                    candidate_code, f"turn_{turn_id}.py", test_cases, entry
                )

                per_test_results: Dict[int, bool] = {}
                try:
                    from src.core.test_runner import run_tests_per_test as _rt
                    _r = _rt(candidate_code, test_cases or [], file_path=f"turn_{turn_id}.py")
                    if not _r.error:
                        per_test_results = dict(_r.per_test)
                except Exception:
                    pass

                attempt_log.update({
                    "success": success,
                    "test_result": output,
                    "generated_code": candidate_code,
                    "patch_spans": candidate_spans,
                    "per_test_results": per_test_results,
                })
                turn_result["attempts"].append(attempt_log)

                if success:
                    turn_solved = True
                    turn_result["solved"] = True
                    accumulated_code = candidate_code
                    dialogue_chain.append({
                        "turn": turn_id, "role": "user",
                        "content": task_desc + f"\n\nTests failed with:\n{last_trace}\n\nPlease fix the code.",
                    })
                    dialogue_chain.append({
                        "turn": turn_id, "role": "assistant",
                        "content": f"```python\n{candidate_code}\n```",
                    })
                    break

                last_trace = trace or output
                anchor_hits = anchor_hits or []
                full_code = candidate_code

        if not turn_solved:
            dialogue_chain.append({
                "turn": turn_id, "role": "user",
                "content": task_desc + f"\n\nTests failed with:\n{last_trace}",
            })
            if full_code:
                accumulated_code = full_code

        subproblems_log.append(turn_result)
        turn_summaries.append({
            "turn": turn_id,
            "attempts": turn_attempt_count,
            "solved": turn_solved,
            "input_tokens": turn_input_tokens,
            "output_tokens": turn_output_tokens,
        })

        if turn_solved and first_success_turn is None:
            first_success_turn = turn_id

    overall_solved = all(t.get("solved", False) for t in subproblems_log)
    if overall_solved and all_tests:
        final_code = accumulated_code or (
            (conversation_history[-1].get("context", "") or "") + "\n\n" +
            (conversation_history[-1].get("target_code", "") or "")
        )
        final_ok, _, _, _ = _run_tracebench_tests(final_code, file_path, all_tests, entry)
        if not final_ok:
            overall_solved = False

    return {
        "problem_id": problem_id,
        "mode": mode,
        "provider": provider,
        "model": generator.model,
        "solved": overall_solved,
        "first_success_turn": first_success_turn,
        "total_turns": len(conversation_history),
        "total_attempts": total_attempts,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "turn_results": turn_summaries,
        "subproblems": subproblems_log,
        "dialogue_chain_length": len(dialogue_chain),
        "file_path": file_path,
    }


if __name__ == "__main__":
    import json

    # 测试示例
    print("Multi-Model Runner Test")
    print("=" * 60)

    sample_path = Path("output/full_run_20251202_131846/tracebench.json")
    if sample_path.exists():
        data = json.loads(sample_path.read_text(encoding="utf-8"))
        if data:
            entry = data[0]

            print("\n测试 Qwen...")
            result_qwen = run_debug_session(entry, mode="baseline", max_turns=2, provider="qwen")
            print(f"Qwen Result: solved={result_qwen['solved']}, turns={result_qwen['total_turns']}")

            if os.getenv("ANTHROPIC_API_KEY"):
                print("\n测试 Claude...")
                result_claude = run_debug_session(entry, mode="baseline", max_turns=2, provider="claude")
                print(f"Claude Result: solved={result_claude['solved']}, turns={result_claude['total_turns']}")
    else:
        print(f"未找到测试数据: {sample_path}")
