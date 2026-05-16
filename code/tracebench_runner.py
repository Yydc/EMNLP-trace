#!/usr/bin/env python3
"""TraceBench runner that calls Together-compatible LLMs to get real metrics."""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.agent.generation import CodeGenerator
from src.agent.prompts import extract_code
from src.core.error_aware import ControlPlan, ErrorAwareController
from src.core.risk_analyzer import RiskAnalyzer, Span

DEFAULT_MODEL = (
    os.getenv("TRACEBENCH_MODEL")
    or os.getenv("TOGETHER_MODEL")
    or os.getenv("CODEFLOW_INFERENCE_MODEL")
    or "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"
)
DEFAULT_TEMP = float(os.getenv("TRACEBENCH_TEMPERATURE", "0.35"))
TEST_TIMEOUT = int(os.getenv("TRACEBENCH_TEST_TIMEOUT", "120"))


def _with_line_numbers(code: str) -> str:
    lines = code.splitlines()
    return "\n".join(f"{idx+1:4d}: {line}" for idx, line in enumerate(lines))


def _get_anchor_lines(entry: Dict[str, Any]) -> List[int]:
    anchors: List[int] = []
    for inj in entry.get("injections", []) or []:
        anchor = inj.get("anchor") or {}
        loc = anchor.get("anchor_line") or inj.get("location", {}).get("line_approx")
        try:
            if loc is not None:
                anchors.append(int(loc))
        except (TypeError, ValueError):
            continue
    return anchors


def _build_anchor_notes(entry: Dict[str, Any]) -> str:
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
    mode: str,
    last_failure: str,
    suspicious_spans: List[Span],
) -> str:
    """
    统一的 prompt 构造逻辑：
    - 不再在文案中提 allowed_edit_regions / 约束
    - 不在提示中暴露 anchor / suspicious spans，保持盲测
    """
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")

    test_preview = (
        "\n".join(f"- {t}" for t in tests[:5])
        if tests
        else "Tests embedded in the provided assertions."
    )

    failure_section = (
        last_failure.strip()
        if last_failure
        else "No test executed yet. Propose a fix and make sure all assertions pass."
    )

    guidance = (
        "Analyze the failing behavior and fix the root cause. "
        "Make minimal, targeted changes that make all tests pass."
    )

    prompt = f"""You are debugging the Python file `{file_path}`.
Mode: {mode}. Your goal is to produce a minimal patch that makes all tests pass.

{guidance}

Tests to satisfy:
{test_preview}

Last failing trace/output:
{failure_section}

Current code (with line numbers):
{_with_line_numbers(current_code)}

Return the full corrected file. Use a single ```python``` block. Do not include explanations."""
    return prompt


def _build_multi_turn_prompt(
    entry: Dict[str, Any],
    turn_id: int,
    task_desc: str,
    current_code: str,
    tests: List[str],
    last_failure: str,
    dialogue_history: List[Dict[str, Any]],
    mode: str,
    anchor_hits: List[int],
) -> str:
    """
    构建多轮交互的 prompt，包含完整的对话历史链。

    Args:
        entry: TraceBench 数据条目
        turn_id: 当前轮次ID
        task_desc: 当前轮的任务描述
        current_code: 当前的代码
        tests: 测试用例
        last_failure: 上次失败的错误信息
        dialogue_history: 对话历史链
        mode: baseline 或 error_aware
        analyzer: RiskAnalyzer 实例
        controller: ErrorAwareController 实例
        failure_streak: 连续失败次数
    """
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")

    # 构建对话历史部分
    history_text = ""
    if dialogue_history:
        history_text = "\n\n## Previous Conversation:\n"
        for msg in dialogue_history[-5:]:  # 只显示最近5轮对话
            role = msg['role'].capitalize()
            content = msg['content']
            history_text += f"\n**{role}:**\n{content}\n"

    test_preview = "\n".join(f"- {t}" for t in tests[:5]) if tests else "No tests for this turn."

    # 软提示：始终展示运行时轨迹作为日志，不作为“定责”提示
    trace_hint = ""
    if anchor_hits:
        hits = sorted(set(anchor_hits))
        lines = "\n".join(f"[TRACE] Checkpoint at Line {ln} executed." for ln in hits)
        trace_hint = (
            "\n## System Standard Output (Truncated):\n"
            "... (previous logs) ...\n"
            f"{lines}\n"
            "... (program crashed here) ..."
        )

    prompt = f"""You are solving a multi-turn programming task. This is Turn {turn_id}.

IMPORTANT OUTPUT RULES:
- Return ONLY the corrected Python code in a single ```python``` fenced block.
- Do NOT include analysis, planning, step-by-step reasoning, or commentary before or after the code.
- If you must explain, keep it under 50 words AFTER the code block.
- The code block must be the COMPLETE corrected file/function, not a diff or snippet.

{history_text}

## Current Task:
{task_desc}

## Tests to Pass:
{test_preview}

## Last Failure:
{last_failure}
{trace_hint}

## Current Code:
{_with_line_numbers(current_code)}

Return the complete corrected code in a single ```python``` block. The code should pass all tests."""

    return prompt


def _compute_patch_spans(old_code: str, new_code: str, file_path: str) -> List[Dict[str, Any]]:
    """Approximate patch spans by diffing old/new code line ranges."""
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
            start = i1 + 1  # convert to 1-based
            end = max(start, i2)
        spans.append({"file_path": file_path, "start_line": start, "end_line": end})
    if not spans:
        spans.append({"file_path": file_path, "start_line": 1, "end_line": 1})
    return spans


def _anchor_alignment_score(spans: List[Dict[str, Any]], anchor_hits: List[int]) -> float:
    """
    Evidence-based scoring：patch 靠近运行时 anchor 越近，得分越高。
    - 无 anchor 时返回 1.0（退化为等价采样）
    - 使用 1/(1 + 0.1 * min_dist) 作为平滑衰减
    """
    if not anchor_hits:
        return 1.0
    if not spans:
        return 0.0
    min_dist = float("inf")
    for span in spans:
        start = span.get("start_line", 0) or 0
        end = span.get("end_line", 0) or start
        for anchor in anchor_hits:
            if anchor < start:
                dist = start - anchor
            elif anchor > end:
                dist = anchor - end
            else:
                dist = 0
            min_dist = min(min_dist, dist)
    return 1.0 / (1.0 + 0.1 * min_dist)


def _spans_to_json(spans: List[Span]) -> List[Dict[str, Any]]:
    return [asdict(s) for s in spans]


def _extract_anchor_hits(stdout: str, entry: Dict[str, Any]) -> List[int]:
    """Detect runtime anchor prints and map them to line numbers."""
    hits: List[int] = []
    if "ANCHOR_HIT" not in stdout:
        return hits

    anchor_lines = _get_anchor_lines(entry)
    if anchor_lines:
        hits.extend(anchor_lines)
    return hits


def _tune_decoding(plan: ControlPlan, failure_streak: int) -> Tuple[float, int]:
    """
    极简调参策略：仅在极端连续失败时轻微升温，避免过度干预。
    同一策略适用于 baseline / error_aware。
    """
    base_temp = getattr(plan, "temperature", None) or DEFAULT_TEMP
    temperature = max(0.05, float(base_temp))

    # 仅在失败 >= 3 次时轻微升温
    if failure_streak >= 3:
        temperature = min(0.5, temperature + 0.1)

    num_candidates = getattr(plan, "num_candidates", 1) or 1
    return temperature, max(1, int(num_candidates))


def _run_tracebench_tests(
    code: str, file_path: str, tests: List[str], entry: Dict[str, Any]
) -> Tuple[bool, str, str, List[int]]:
    """Execute provided TraceBench assertions against candidate code."""
    if not tests:
        return True, "No tests provided", "", []

    try:
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
                timeout=TEST_TIMEOUT,
            )

        combined_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        anchor_hits = _extract_anchor_hits(proc.stdout or "", entry)
        return proc.returncode == 0, combined_output.strip(), proc.stderr or "", anchor_hits
    except subprocess.TimeoutExpired:
        error_msg = f"Test execution timed out after {TEST_TIMEOUT} seconds"
        print(f"  [!!] {error_msg}", file=sys.stderr)
        return False, "", error_msg, []
    except Exception as e:
        error_msg = f"Test execution error: {e}"
        print(f"  [!!] {error_msg}", file=sys.stderr)
        return False, "", error_msg, []


def run_multi_turn_debug_session(
    entry: Dict[str, Any],
    mode: str = "baseline",
    enable_adaptive_decoding: bool = False,
    max_attempts_per_turn: int = 3,
    max_turns: int = 5,
) -> Dict[str, Any]:
    """
    运行真正的多轮交互式 TraceBench 评测会话（对话链模式）。

    每一轮都是一个独立的 prompt，形成完整的对话历史链：
    - Turn 0: 实现基础函数
    - Turn 1: 基于 Turn 0 的结果（成功/失败），继续实现下一批函数
    - Turn N: 累积所有历史，Agent 可以回溯和修正

    Args:
        entry: 多轮 TraceBench 数据条目
        mode: "baseline" 或 "error_aware"
        enable_adaptive_decoding: 是否启用动态调参
        max_attempts_per_turn: 每轮最大尝试次数（修复轮次）
    """
    model = DEFAULT_MODEL
    temperature = DEFAULT_TEMP

    api_key = os.getenv("TOGETHER_API_KEY")
    api_url = os.getenv("TOGETHER_API_BASE", "https://api.together.xyz/v1")
    if "claude" in model.lower() and os.getenv("ANTHROPIC_API_KEY"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        api_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    if not api_key:
        raise RuntimeError(
            "API key is required (set ANTHROPIC_API_KEY for Claude, or TOGETHER_API_KEY otherwise)."
        )

    generator = CodeGenerator(api_key, api_url)
    analyzer = RiskAnalyzer()
    controller = ErrorAwareController()

    problem_id = entry.get('trace_id') or entry.get('problem_id', 'unknown')
    file_path = entry.get('code_context', {}).get('file_path', 'solution.py')
    conversation_history = entry.get('conversation_history', [])[:max_turns]

    if not conversation_history:
        return {
            'problem_id': problem_id,
            'mode': mode,
            'solved': False,
            'error': 'No conversation history in multi-turn entry',
        }

    # 对话链：存储每一轮的 prompt 和 response
    dialogue_chain: List[Dict[str, Any]] = []
    accumulated_code = entry.get("code_context", {}).get("corrupted_code", "") or ""
    turn_results: List[Dict[str, Any]] = []
    total_attempts = 0
    all_solved = True
    overall_solved = False
    all_tests: List[str] = []

    for turn_idx, turn_data in enumerate(conversation_history):
        turn_id = turn_data.get('turn_id', turn_idx)
        context = turn_data.get('context', '')
        expected_target = turn_data.get('target_code', '')
        has_injected_error = turn_data.get('has_error', False)
        subproblems = turn_data.get('subproblems', [])
        test_cases = turn_data.get('test_cases', [])
        original_target = turn_data.get('original_target_code', expected_target)

        # 记录全局测试集，用于最终整体验证
        if test_cases:
            all_tests.extend(test_cases)

        turn_result = {
            'turn_id': turn_id,
            'subproblems': subproblems,
            'has_injected_error': has_injected_error,
            'solved': False,
            'attempts': [],
        }

        # 构建当前轮的任务描述
        task_desc = f"Implement the following functions: {', '.join(subproblems)}"
        if context:
            task_desc += f"\n\nYou can use the previously implemented code:\n```python\n{context}\n```"

        # 第一轮：让 Agent 实现目标函数
        current_code = expected_target  # 从注入了错误的代码开始（如果有错误）
        turn_solved = False

        # 使用最新的累计代码作为上下文，确保跨轮修改能被传递
        context_seed = accumulated_code if accumulated_code else context
        full_code = context_seed + "\n\n" + current_code if context_seed else current_code
        success, output, trace, anchor_hits = _run_tracebench_tests(
            full_code, f"turn_{turn_id}.py", test_cases, entry
        )

        if success:
            # 当前轮直接通过（没有注入错误，或者注入失败了）
            turn_solved = True
            turn_result['solved'] = True
            accumulated_code = full_code

            # 记录到对话链
            dialogue_chain.append({
                'turn': turn_id,
                'role': 'user',
                'content': task_desc + "\n\nImplement these functions to pass the tests.",
            })
            dialogue_chain.append({
                'turn': turn_id,
                'role': 'assistant',
                'content': f"```python\n{current_code}\n```",
            })
        else:
            # 当前轮有错误，需要修复
            last_trace = trace or output
            failure_streak = 0
            anchor_hits = anchor_hits or []

            # 修复循环
            for attempt_idx in range(max_attempts_per_turn):
                total_attempts += 1
                suspicious_spans: List[Span] = []

                # 构建修复 prompt（包含完整的对话历史 + 运行时轨迹）
                prompt = _build_multi_turn_prompt(
                    entry=entry,
                    turn_id=turn_id,
                    task_desc=task_desc,
                    current_code=full_code,
                    tests=test_cases,
                    last_failure=last_trace,
                    dialogue_history=dialogue_chain,
                    mode=mode,
                    anchor_hits=anchor_hits,
                )

                # 调参
                if enable_adaptive_decoding:
                    tuned_temp = min(0.5, temperature + 0.1 * failure_streak)
                else:
                    tuned_temp = temperature

                # 生成修复代码（Baseline 单样本；Error-aware 多样本择优）
                candidate_code = ""
                candidate_spans: List[Dict[str, Any]] = []
                raw_resp = ""

                if mode == "error_aware":
                    num_samples = 3
                    best_score = -1.0
                    for _ in range(num_samples):
                        sample_temp = min(0.8, tuned_temp + 0.1)
                        resp = generator.generate(model, prompt, temperature=sample_temp)
                        code = extract_code(resp or "") if resp else ""
                        if not code:
                            continue
                        spans = _compute_patch_spans(full_code, code, file_path)
                        score = _anchor_alignment_score(spans, anchor_hits)
                        if score > best_score:
                            best_score = score
                            candidate_code = code
                            candidate_spans = spans
                            raw_resp = resp

                    if not candidate_code:
                        raw_resp = generator.generate(model, prompt, temperature=tuned_temp)
                        candidate_code = extract_code(raw_resp or "") if raw_resp else ""
                        candidate_spans = _compute_patch_spans(full_code, candidate_code, file_path) if candidate_code else []
                else:
                    raw_resp = generator.generate(model, prompt, temperature=tuned_temp)
                    candidate_code = extract_code(raw_resp or "") if raw_resp else ""
                    candidate_spans = _compute_patch_spans(full_code, candidate_code, file_path) if candidate_code else []

                # Compute paper-required per-attempt fields:
                #   - code_before : the code that was tested at this attempt
                #     (for RegressionRate diff)
                #   - edited_lines: actual line numbers changed in candidate
                #     vs code_before (for Outside-G)
                edited_lines: List[int] = []
                if candidate_code:
                    try:
                        import difflib as _dl
                        b_lines = full_code.splitlines()
                        a_lines = candidate_code.splitlines()
                        m = _dl.SequenceMatcher(a=b_lines, b=a_lines)
                        for tag, i1, i2, j1, j2 in m.get_opcodes():
                            if tag == "equal":
                                continue
                            if tag in ("replace", "insert"):
                                edited_lines.extend(range(j1 + 1, j2 + 1))
                            else:  # delete
                                edited_lines.append(max(1, j1 + 1))
                        edited_lines = sorted(set(edited_lines))
                    except Exception:
                        pass

                attempt_log = {
                    'attempt_number': total_attempts,
                    'turn': turn_id,
                    'attempt_in_turn': attempt_idx,
                    'mode': mode,
                    'temperature': tuned_temp,
                    # 将 blame_spans 的 file_path 规范化为主文件，便于与 GT 注入对齐
                    'blame_spans': candidate_spans,  # 直接用补丁跨度作为归因位置
                    'raw_response': raw_resp,
                    # New paper-required fields for Outside-G / RegressionRate
                    'code_before': full_code,
                    'edited_lines': edited_lines,
                }

                if not candidate_code:
                    attempt_log['success'] = False
                    attempt_log['test_result'] = 'LLM returned empty response'
                    turn_result['attempts'].append(attempt_log)
                    failure_streak += 1
                    last_trace = 'LLM returned empty response'
                    continue

                # 测试修复后的代码
                success, output, trace, anchor_hits = _run_tracebench_tests(
                    candidate_code, f"turn_{turn_id}.py", test_cases, entry
                )

                # Per-test pass/fail (for RegressionRate). We call the
                # per-test runner separately so we don't disturb the existing
                # all-or-nothing harness path.
                per_test_results: Dict[int, bool] = {}
                try:
                    from src.core.test_runner import run_tests_per_test as _rt
                    _r = _rt(candidate_code, test_cases or [], file_path=f"turn_{turn_id}.py")
                    if not _r.error:
                        per_test_results = dict(_r.per_test)
                except Exception:
                    pass

                attempt_log.update({
                    'success': success,
                    'test_result': output,
                    'generated_code': candidate_code,
                    'patch_spans': candidate_spans,
                    'per_test_results': per_test_results,
                })
                turn_result['attempts'].append(attempt_log)

                if success:
                    turn_solved = True
                    turn_result['solved'] = True
                    accumulated_code = candidate_code

                    # 成功后，将对话加入历史链
                    dialogue_chain.append({
                        'turn': turn_id,
                        'role': 'user',
                        'content': task_desc + f"\n\nTests failed with:\n{last_trace}\n\nPlease fix the code.",
                    })
                    dialogue_chain.append({
                        'turn': turn_id,
                        'role': 'assistant',
                        'content': f"```python\n{candidate_code}\n```",
                    })
                    break

                failure_streak += 1
                last_trace = trace or output
                anchor_hits = anchor_hits or []
                full_code = candidate_code

        if not turn_solved:
            all_solved = False
            # 即使失败，也记录到对话链，让后续轮次知道前面的失败
            dialogue_chain.append({
                'turn': turn_id,
                'role': 'user',
                'content': task_desc + f"\n\nTests failed with:\n{last_trace}",
            })
            if full_code:
                accumulated_code = full_code

        turn_results.append(turn_result)

    # 检查整体是否成功：所有轮次都要通过
    overall_solved = all([t.get('solved', False) for t in turn_results])

    # 如果全部轮次标记通过，再用汇总测试集做一次全量校验，避免局部通过但全局失效
    if overall_solved and all_tests:
        final_code = accumulated_code or (conversation_history[-1].get('context', '') + "\n\n" + conversation_history[-1].get('target_code', ''))
        final_ok, _, _, _ = _run_tracebench_tests(final_code, file_path, all_tests, entry)
        if not final_ok:
            overall_solved = False

    # 计算 first_success_turn（如果所有轮次都成功）
    first_success_turn = None
    if overall_solved:
        first_success_turn = len(turn_results)
        if total_attempts == 0:
            total_attempts = len(turn_results)

    return {
        'problem_id': problem_id,
        'mode': mode,
        'enable_adaptive_decoding': enable_adaptive_decoding,
        'solved': overall_solved,
        'first_success_turn': first_success_turn,
        'total_turns': len(conversation_history),
        'total_attempts': total_attempts,
        'turn_results': turn_results,
        'dialogue_chain_length': len(dialogue_chain),
    }


def run_debug_session(
    entry: Dict[str, Any],
    mode: str = "baseline",
    enable_adaptive_decoding: bool = False,
    max_turns: int = 5
) -> Dict[str, Any]:
    """
    Run a single-turn TraceBench session (legacy format).

    Args:
        entry: TraceBench 数据条目
        mode: "baseline" 或 "error_aware"（是否提供 suspicious_spans/anchors）
        enable_adaptive_decoding: True=启用动态调参策略, False=固定参数(Vanilla)
        max_turns: 最大轮次

    注意：如果 entry 包含 multi_turn=True，应该使用 run_multi_turn_debug_session
    """
    # 检测是否为多轮格式
    if entry.get('multi_turn', False):
        return run_multi_turn_debug_session(
            entry=entry,
            mode=mode,
            enable_adaptive_decoding=enable_adaptive_decoding,
            max_attempts_per_turn=max_turns,
            max_turns=max_turns,
        )

    # 原有的单轮逻辑
    model = DEFAULT_MODEL
    temperature = DEFAULT_TEMP

    # Resolve API creds: prefer Anthropic when running Claude; otherwise Together/OpenAI-compatible.
    api_key = os.getenv("TOGETHER_API_KEY")
    api_url = os.getenv("TOGETHER_API_BASE", "https://api.together.xyz/v1")
    if "claude" in model.lower() and os.getenv("ANTHROPIC_API_KEY"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        api_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    if not api_key:
        raise RuntimeError(
            "API key is required (set ANTHROPIC_API_KEY for Claude, or TOGETHER_API_KEY otherwise)."
        )

    generator = CodeGenerator(api_key, api_url)
    analyzer = RiskAnalyzer()
    controller = ErrorAwareController()

    problem_id = entry.get("trace_id") or entry.get("problem_id", "unknown")
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")
    tests = entry.get("evaluation", {}).get("test_cases") or []

    # 使用 corrupted_code（对于 raw 数据集，这就是原始代码；对于 injected 数据集，这是注入错误的代码）
    baseline_code = entry.get("code_context", {}).get("corrupted_code", "")

    # Seed anchors only for error-aware decoding.
    anchor_lines = _get_anchor_lines(entry) if mode == "error_aware" else []

    current_code = baseline_code
    previous_code = baseline_code
    failure_streak = 0
    last_trace = ""
    first_success_turn = None
    solved = False

    # Run a quick check on the corrupted code to harvest a real traceback/anchors.
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
            "solved": True,
            "first_success_turn": 0,
            "total_turns": 0,
            "subproblems": [sub_log],
            "file_path": file_path,
        }

    attempt_counter = 0

    for turn in range(1, max_turns + 1):
        state = {
            "file_path": Path(file_path).name,
            "last_test_output": last_trace,
            "anchor_hits": anchor_lines if mode == "error_aware" else [],
            "failure_streak": failure_streak,
        }
        risk_vector = analyzer.build_risk_vector(state)

        total_lines = max(1, len(current_code.splitlines()))

        if mode == "error_aware":
            # 使用 controller / risk_vector 只为了拿 suspicious_spans，不再作为硬约束。
            plan = controller.make_control_plan(risk_vector)
            suspicious_spans = risk_vector.suspicious_spans
            if not suspicious_spans and anchor_lines:
                suspicious_spans = [
                    Span(
                        file_path=file_path,
                        start_line=ln,
                        end_line=ln,
                        score=0.9,
                    )
                    for ln in anchor_lines
                ]
        else:
            # baseline：构造一个简单的 plan，方便后面统一调参 / 记录
            plan = ControlPlan(
                allowed_edit_regions=[],
                temperature=max(temperature, 0.2),
                top_k=32,
                num_candidates=1,
                structured_prompt=True,
                enable_rollback=False,
            )
            suspicious_spans = []

        # 统一：全局编辑自由，不在提示中强调任何区域限制
        plan.allowed_edit_regions = [
            Span(
                file_path=file_path,
                start_line=1,
                end_line=total_lines,
                score=0.1,
            )
        ]

        prompt = _build_prompt(
            entry=entry,
            current_code=current_code,
            tests=tests,
            mode=mode,
            last_failure=last_trace,
            suspicious_spans=suspicious_spans,
        )

        # 根据 enable_adaptive_decoding 决定是否使用动态调参
        if enable_adaptive_decoding:
            tuned_temp, tuned_candidates = _tune_decoding(plan, failure_streak)
        else:
            # Vanilla: 固定参数，不动态调整
            tuned_temp = getattr(plan, "temperature", None) or DEFAULT_TEMP
            tuned_candidates = getattr(plan, "num_candidates", None) or 1

        for _ in range(tuned_candidates):
            attempt_counter += 1
            raw_resp = generator.generate(model, prompt, temperature=tuned_temp)
            candidate_code = extract_code(raw_resp or "") if raw_resp else ""

            attempt_log: Dict[str, Any] = {
                "attempt_number": attempt_counter,
                "turn": turn,
                "mode": mode,
                "temperature": tuned_temp,
                "decoding_candidates": tuned_candidates,
                "prompt_tokens": len(prompt.split()),
                "blame_spans": _spans_to_json(suspicious_spans),
                "prompt": prompt,
                "raw_response": raw_resp,
            }

            if not candidate_code:
                attempt_log["success"] = False
                attempt_log["test_result"] = "LLM returned empty response"
                sub_log["attempts"].append(attempt_log)
                failure_streak += 1
                last_trace = "LLM returned empty response"
                continue

            success, output, trace, anchor_hits = _run_tracebench_tests(
                candidate_code, file_path, tests, entry
            )

            attempt_log.update(
                {
                    "success": success,
                    "test_result": output,
                    "generated_code": candidate_code,
                    "patch_spans": _compute_patch_spans(
                        previous_code, candidate_code, file_path
                    ),
                }
            )

            sub_log["attempts"].append(attempt_log)

            current_code = candidate_code
            previous_code = candidate_code

            if success:
                solved = True
                sub_log["solved"] = True
                if first_success_turn is None:
                    first_success_turn = turn
                break

            failure_streak += 1
            last_trace = trace or output
            if mode == "error_aware":
                anchor_lines = sorted(set(anchor_lines + anchor_hits))

        if solved:
            break

    problem_log = {
        "problem_id": problem_id,
        "mode": mode,
        "enable_adaptive_decoding": enable_adaptive_decoding,
        "solved": solved,
        "first_success_turn": first_success_turn,
        "total_turns": turn,
        "subproblems": [sub_log],
        "file_path": file_path,
    }
    return problem_log


if __name__ == "__main__":
    # Quick manual smoke test (requires TOGETHER_API_KEY and small dataset entry).
    import json

    sample_path = Path("output/tracebench_multi_anchor.json")
    if sample_path.exists():
        entry = json.loads(sample_path.read_text(encoding="utf-8"))[0]
        print(run_debug_session(entry, mode="baseline", max_turns=2))
    else:
        print("No data/tracebench.json available for a smoke test.")
