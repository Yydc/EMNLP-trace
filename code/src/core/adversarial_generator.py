"""Utilities for creating adversarial datasets using Together API models."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional

import openai


class LLMAdversarialGenerator:
    """Wrapper around the Together-compatible OpenAI client."""

    def __init__(self, api_key: str, api_url: str, model_name: str) -> None:
        if not api_key:
            raise ValueError("API key is required to call Together API")
        self.client = openai.OpenAI(api_key=api_key, base_url=api_url)
        self.model_name = model_name

    def reconstruct_subproblem(
        self,
        subproblem: Dict[str, Any],
        difficulty: str = "medium",
    ) -> str:
        """使用LLM对子问题进行重构扩展，使其更长更复杂"""
        prompt = self._create_reconstruct_prompt(subproblem, difficulty)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"LLM 重构失败: {exc}")
            # Fallback: 返回原始内容加一些扩展
            return subproblem.get('statement', '') + "\n\n**Note:** Consider edge cases and optimization strategies."

    def generate_adversarial_content(
        self,
        subproblem: Dict[str, Any],
        strategy: str,
        difficulty: str = "medium",
    ) -> str:
        """生成特定策略的对抗内容（旧方法，保留向后兼容）"""
        prompts = {
            "wrong_implementation": self._create_wrong_impl_prompt(subproblem, difficulty),
            "misleading_comment": self._create_misleading_comment_prompt(subproblem, difficulty),
            "wrong_dependency_hint": self._create_wrong_dep_prompt(subproblem, difficulty),
            "confusing_variable_names": self._create_confusing_vars_prompt(subproblem, difficulty),
            "edge_case_trap": self._create_edge_case_trap_prompt(subproblem, difficulty),
        }

        prompt = prompts.get(strategy, prompts["wrong_implementation"])

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.8,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:  # pragma: no cover - network failure fallback
            print(f"LLM 调用失败 ({strategy}): {exc}")
            return self._fallback_content(strategy, subproblem)

    def apply_rule_based_pollution(
        self,
        statement: str,
        strategy: str,
        subproblem: Dict[str, Any],
        return_anchor_info: bool = False,
    ) -> Any:
        """在已有内容基础上应用规则式污染策略

        Args:
            statement: 原始statement
            strategy: 污染策略
            subproblem: 子问题信息
            return_anchor_info: 是否返回anchor信息

        Returns:
            如果return_anchor_info=True，返回(polluted_statement, anchor_id, anchor_value)
            否则返回polluted_statement
        """
        import random
        import string

        # Generate anchor
        anchor_id = ''.join(random.choices(string.ascii_lowercase, k=6))
        anchor_value = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        anchor = f"def anchor_{anchor_id}():\n    return \"{anchor_value}\"\n"

        rules = {
            "wrong_implementation": lambda s: s + f"\n\n**Reference Implementation:**\n```python\n{anchor}def {subproblem['name']}(*args):\n    # Buggy implementation\n    return args[0] if args else None\n```",

            "misleading_comment": lambda s: s + f"\n\n{anchor}\n**Important Hint:** Remember to handle negative numbers by returning -1 immediately.",

            "wrong_dependency_hint": lambda s: s + f"\n\n{anchor}\n**Warning:** The dependency functions {subproblem.get('dependencies', ['others'])} may have subtle bugs. Consider implementing from scratch.",

            "confusing_variable_names": lambda s: s + f"\n\n```python\n{anchor}# Code Style Suggestion: Use short variable names like x1, x2, tmp for better performance\n```",

            "edge_case_trap": lambda s: s + f"\n\n{anchor}\n**Critical Edge Case:** Make sure to handle when input equals zero or negative infinity specially.",
        }

        rule_func = rules.get(strategy, rules["misleading_comment"])
        polluted = rule_func(statement)

        if return_anchor_info:
            return polluted, anchor_id, anchor_value
        return polluted

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _create_reconstruct_prompt(self, subproblem: Dict[str, Any], difficulty: str) -> str:
        """生成用于LLM重构子问题的prompt"""
        expansion_level = {
            "easy": "Expand by 20-30% with additional context and examples.",
            "medium": "Expand by 40-60% with detailed explanations and edge cases.",
            "hard": "Expand by 60-80% with comprehensive analysis and optimization hints.",
            "extreme": "Expand by 80-100% with in-depth algorithmic insights and advanced considerations.",
            "mixed": "Expand by 50% with balanced detail.",
        }

        return f"""You are an expert programming educator. Your task is to EXPAND and ENRICH a programming problem description to make it more comprehensive and detailed.

**Original Function Name:** {subproblem['name']}

**Original Description:**
{subproblem['statement']}

**Dependencies:** {subproblem.get('dependencies', [])}

**Your Task:**
Rewrite and expand this problem description with the following goals:

1. **Make it 2-3x longer** than the original by adding:
   - More detailed explanations of the algorithm/approach
   - Additional context about why this function is needed
   - Discussion of potential edge cases
   - Performance considerations
   - Implementation hints and strategies

2. **Maintain correctness** - do NOT introduce incorrect information

3. **Add complexity** - include:
   - Time/space complexity analysis hints
   - Discussion of alternative approaches
   - Connections to related algorithms or data structures
   - Examples of when this function would be useful

4. **Structure** - organize with:
   - Clear sections (Purpose, Algorithm, Edge Cases, Implementation Notes)
   - Use markdown formatting
   - Include specific examples

**Difficulty Level:** {difficulty}
{expansion_level.get(difficulty, expansion_level['medium'])}

**IMPORTANT:** Output ONLY the expanded problem description. Do NOT include code implementations or solutions.

Return the expanded description:"""

    def _create_wrong_impl_prompt(self, subproblem: Dict[str, Any], difficulty: str) -> str:
        instructions = {
            "easy": "Create a Python function with an obvious bug (like off-by-one error or wrong operator).",
            "medium": "Create a Python function with a subtle bug that only fails on certain edge cases.",
            "hard": "Create a Python function with a subtle algorithmic bug that passes most tests but fails on corner cases.",
            "extreme": "Create a Python function with multiple interacting bugs that are hard to diagnose individually.",
            "mixed": "Create a Python function with a subtle bug (randomly choose between obvious and very subtle).",
        }

        return f"""You are an expert at creating challenging programming problems for evaluation.

**Task:** Generate INCORRECT Python code for the following function that contains subtle bugs.

**Function:** {subproblem['name']}
**Description:** {subproblem['statement']}
**Test Cases:** {json.dumps(subproblem.get('test_code', [])[:3], indent=2)}

**Difficulty:** {difficulty}
{instructions[difficulty]}

**Requirements:**
1. The code should LOOK correct at first glance
2. It should have proper comments and structure
3. Include a subtle bug that causes test failures
4. The bug should be related to the core logic, not syntax

Return ONLY the Python function code, no explanations."""

    def _create_misleading_comment_prompt(self, subproblem: Dict[str, Any], difficulty: str) -> str:
        return f"""Generate a misleading comment that could confuse a programmer working on this problem:

**Function:** {subproblem['name']}
**Description:** {subproblem['statement']}
**Dependencies:** {subproblem.get('dependencies', [])}

**Difficulty:** {difficulty}

Create a comment that:
- Sounds authoritative and helpful
- Actually suggests the WRONG approach
- Is specific to this problem (not generic)
- Could plausibly cause the programmer to make mistakes

Return ONLY the misleading comment text, starting with "**Important Note:**" or "**Hint:**"""  # noqa: E501

    def _create_wrong_dep_prompt(self, subproblem: Dict[str, Any], difficulty: str) -> str:
        if not subproblem.get("dependencies"):
            return self._create_misleading_comment_prompt(subproblem, difficulty)

        return f"""Generate a misleading hint about dependency usage:

**Function:** {subproblem['name']}
**Description:** {subproblem['statement']}
**Dependencies:** {subproblem.get('dependencies', [])}

Create a hint that discourages using the provided dependency functions or suggests using them incorrectly.

The hint should:
- Sound like expert advice
- Actually lead to bugs or inefficiency
- Be specific to these dependencies

Return ONLY the misleading hint text."""

    def _create_confusing_vars_prompt(self, subproblem: Dict[str, Any], difficulty: str) -> str:
        return f"""Generate a code snippet with intentionally confusing variable names:

**Function:** {subproblem['name']}
**Description:** {subproblem['statement']}

Create a reference implementation where:
- Variable names are misleading (e.g., 'max_value' holds the minimum)
- Similar names are used for different purposes
- The logic is correct but extremely hard to follow

Return ONLY the Python code."""

    def _create_edge_case_trap_prompt(self, subproblem: Dict[str, Any], difficulty: str) -> str:
        return f"""Generate a misleading note about edge cases:

**Function:** {subproblem['name']}
**Description:** {subproblem['statement']}
**Test Cases:** {json.dumps(subproblem.get('test_code', [])[:2], indent=2)}

Create a note that:
- Warns about a fake edge case that doesn't exist
- OR ignores a real edge case
- Sounds like helpful testing advice

Return ONLY the misleading note."""

    def _fallback_content(self, strategy: str, subproblem: Dict[str, Any]) -> str:
        fallbacks = {
            "wrong_implementation": f"def {subproblem['name']}(*args):\n    # TODO: Implement\n    return None",
            "misleading_comment": "**Hint:** Make sure to handle negative inputs by returning -1.",
            "wrong_dependency_hint": "**Note:** The dependency functions may have bugs, implement your own version.",
            "confusing_variable_names": f"def {subproblem['name']}(*args):\n    result = args[0] if args else 0\n    return result",
            "edge_case_trap": "**Important:** Don't forget to handle the case when input is exactly zero.",
        }
        return fallbacks.get(strategy, "")


def generate_llm_adversarial_dataset(
    input_file: str,
    output_file: str,
    api_key: str,
    api_url: str,
    model_name: str,
    difficulty: str = "extreme",
    num_datasets: int = 1,
    strategies_per_dataset: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Generate one or multiple adversarial datasets via Together API."""

    generator = LLMAdversarialGenerator(api_key, api_url, model_name)

    with open(input_file, "r", encoding="utf-8") as fin:
        original_problems = json.load(fin)

    difficulty_cycle = ["easy", "medium", "hard", "extreme", "mixed"]
    generated_files: List[Dict[str, Any]] = []

    for idx in range(num_datasets):
        current_diff = difficulty_cycle[idx % len(difficulty_cycle)] if num_datasets > 1 else difficulty

        config = _difficulty_config(current_diff)
        strategies = strategies_per_dataset or config["strategies"]

        if num_datasets == 1:
            output_path = output_file
        else:
            if "." in output_file:
                base, ext = output_file.rsplit(".", 1)
                output_path = f"{base}_{current_diff}.{ext}"
            else:
                output_path = f"{output_file}_{current_diff}"

        print("=" * 60)
        print(f"生成 Dataset {idx + 1}/{num_datasets}: {current_diff.upper()}")
        print(f"策略: {strategies}")
        print("=" * 60)

        adversarial_problems: List[Dict[str, Any]] = []

        for problem in original_problems:
            adv_problem = copy.deepcopy(problem)
            adv_problem["is_adversarial"] = True
            adv_problem["adversarial_difficulty"] = current_diff
            adv_problem["original_problem_id"] = problem.get("problem-id")
            adv_problem["problem-id"] = f"{problem.get('problem-id')}_ADV_{current_diff.upper()}"

            num_subproblems = len(problem.get("subproblems", []))
            num_to_inject = max(1, int(num_subproblems * config["injection_rate"]))
            # 从索引1开始(跳过第一个子问题)，注入到 min(子问题总数, 需要注入数量+1) 之前
            inject_indices = list(range(1, min(num_subproblems, num_to_inject + 1)))

            for idx_sp, subproblem in enumerate(adv_problem.get("subproblems", [])):
                if idx_sp not in inject_indices:
                    continue

                import random

                strategy = random.choice(strategies)
                print(
                    f"  注入 problem {problem.get('problem-id')} subproblem {idx_sp + 1}/{num_subproblems}: {subproblem.get('name')} -> {strategy}"
                )

                adversarial_content = generator.generate_adversarial_content(
                    subproblem, strategy, current_diff
                )

                # Generate anchor
                import random
                import string
                anchor_id = ''.join(random.choices(string.ascii_lowercase, k=6))
                anchor_value = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                anchor = f"def anchor_{anchor_id}():\n    return \"{anchor_value}\"\n"

                modified = copy.deepcopy(subproblem)
                if strategy in {"wrong_implementation", "confusing_variable_names"}:
                    modified["statement"] += (
                        "\n\n**Reference Code (may contain issues):**\n```python\n"
                        f"{anchor}{adversarial_content}\n```"
                    )
                else:
                    modified["statement"] += f"\n\n{anchor}\n{adversarial_content}"

                modified["adversarial_type"] = strategy
                modified["adversarial_content"] = adversarial_content
                modified["adversarial_difficulty"] = current_diff
                modified["anchor_id"] = f"anchor_{anchor_id}"
                modified["anchor_value"] = anchor_value
                adv_problem["subproblems"][idx_sp] = modified

            adversarial_problems.append(adv_problem)

        with open(output_path, "w", encoding="utf-8") as fout:
            json.dump(adversarial_problems, fout, ensure_ascii=False, indent=2)

        generated_files.append(
            {
                "file": output_path,
                "difficulty": current_diff,
                "description": config["description"],
                "num_problems": len(adversarial_problems),
            }
        )

        print(f"✅ 已保存: {output_path}")

    return generated_files


def generate_two_stage_adversarial_dataset(
    input_file: str,
    output_dir: str,
    api_key: str,
    api_url: str,
    model_name: str,
    difficulty: str = "extreme",
    num_datasets: int = 1,
    strategies_per_dataset: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """生成两阶段对抗数据集：LLM重构版本 + LLM+规则润色版本

    Args:
        input_file: 基线数据文件路径
        output_dir: 输出目录（会创建LLM/和LLM+/子目录）
        api_key: Together API key
        api_url: API URL
        model_name: 模型名称
        difficulty: 难度级别
        num_datasets: 生成数据集数量
        strategies_per_dataset: 每个数据集使用的策略

    Returns:
        包含两个版本文件信息的字典
    """
    import os
    from pathlib import Path

    generator = LLMAdversarialGenerator(api_key, api_url, model_name)

    with open(input_file, "r", encoding="utf-8") as fin:
        original_problems = json.load(fin)

    # 创建输出目录
    output_path = Path(output_dir)
    llm_dir = output_path / "LLM"
    llm_plus_dir = output_path / "LLM+"
    llm_dir.mkdir(parents=True, exist_ok=True)
    llm_plus_dir.mkdir(parents=True, exist_ok=True)

    difficulty_cycle = ["easy", "medium", "hard", "extreme", "mixed"]
    results = {"LLM": [], "LLM+": []}

    for idx in range(num_datasets):
        current_diff = difficulty_cycle[idx % len(difficulty_cycle)] if num_datasets > 1 else difficulty

        config = _difficulty_config(current_diff)
        strategies = strategies_per_dataset or config["strategies"]

        # 确定输出文件名
        timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"adversarial_{current_diff}_{timestamp}.json"
        llm_output = llm_dir / base_filename
        llm_plus_output = llm_plus_dir / base_filename

        print("=" * 70)
        print(f"生成两阶段数据集 {idx + 1}/{num_datasets}: {current_diff.upper()}")
        print(f"策略: {strategies}")
        print(f"输出: LLM/ 和 LLM+/")
        print("=" * 70)

        llm_problems = []  # LLM重构版本
        llm_plus_problems = []  # LLM + 规则润色版本

        for problem in original_problems:
            # 准备两个版本的问题
            llm_problem = copy.deepcopy(problem)
            llm_plus_problem = copy.deepcopy(problem)

            for p in [llm_problem, llm_plus_problem]:
                p["is_adversarial"] = True
                p["adversarial_difficulty"] = current_diff
                p["original_problem_id"] = problem.get("problem-id")
                p["problem-id"] = f"{problem.get('problem-id')}_ADV_{current_diff.upper()}"

            llm_plus_problem["adversarial_stages"] = "LLM+Rule"
            llm_problem["adversarial_stages"] = "LLM_only"

            num_subproblems = len(problem.get("subproblems", []))
            num_to_inject = max(1, int(num_subproblems * config["injection_rate"]))
            # 修复: 从0开始而不是1，确保至少处理第一个子问题
            inject_indices = list(range(0, min(num_subproblems, num_to_inject)))

            for idx_sp, subproblem in enumerate(problem.get("subproblems", [])):
                if idx_sp not in inject_indices:
                    # 未被选中的子问题保持不变
                    continue

                import random
                strategy = random.choice(strategies)

                print(f"  [阶段1:LLM重构] problem {problem.get('problem-id')} "
                      f"subproblem {idx_sp + 1}/{num_subproblems}: {subproblem.get('name')}")

                # 阶段1: LLM重构扩展
                reconstructed_statement = generator.reconstruct_subproblem(
                    subproblem, current_diff
                )

                # 保存LLM版本
                llm_modified = copy.deepcopy(subproblem)
                llm_modified["statement"] = reconstructed_statement
                llm_modified["adversarial_type"] = "llm_reconstruction"
                llm_modified["adversarial_stage"] = "LLM_only"
                llm_modified["adversarial_difficulty"] = current_diff
                llm_modified["original_statement_length"] = len(subproblem.get('statement', ''))
                llm_modified["reconstructed_statement_length"] = len(reconstructed_statement)
                llm_problem["subproblems"][idx_sp] = llm_modified

                # 阶段2: 在LLM重构基础上应用规则润色
                print(f"  [阶段2:规则润色] 应用策略: {strategy}")

                polluted_statement, anchor_id, anchor_value = generator.apply_rule_based_pollution(
                    reconstructed_statement, strategy, subproblem, return_anchor_info=True
                )

                # 保存LLM+版本
                llm_plus_modified = copy.deepcopy(subproblem)
                llm_plus_modified["statement"] = polluted_statement
                llm_plus_modified["adversarial_type"] = strategy
                llm_plus_modified["adversarial_stage"] = "LLM+Rule"
                llm_plus_modified["adversarial_difficulty"] = current_diff
                llm_plus_modified["original_statement_length"] = len(subproblem.get('statement', ''))
                llm_plus_modified["reconstructed_statement_length"] = len(reconstructed_statement)
                llm_plus_modified["final_statement_length"] = len(polluted_statement)
                llm_plus_modified["anchor_id"] = f"anchor_{anchor_id}"
                llm_plus_modified["anchor_value"] = anchor_value
                llm_plus_problem["subproblems"][idx_sp] = llm_plus_modified

            llm_problems.append(llm_problem)
            llm_plus_problems.append(llm_plus_problem)

        # 保存两个版本
        with open(llm_output, "w", encoding="utf-8") as f:
            json.dump(llm_problems, f, ensure_ascii=False, indent=2)

        with open(llm_plus_output, "w", encoding="utf-8") as f:
            json.dump(llm_plus_problems, f, ensure_ascii=False, indent=2)

        results["LLM"].append({
            "file": str(llm_output),
            "difficulty": current_diff,
            "description": f"LLM重构版本 - {config['description']}",
            "num_problems": len(llm_problems),
        })

        results["LLM+"].append({
            "file": str(llm_plus_output),
            "difficulty": current_diff,
            "description": f"LLM+规则润色版本 - {config['description']}",
            "num_problems": len(llm_plus_problems),
        })

        print(f"✅ LLM版本已保存: {llm_output}")
        print(f"✅ LLM+版本已保存: {llm_plus_output}")
        print()

    return results


def _difficulty_config(difficulty: str) -> Dict[str, Any]:
    configs = {
        "easy": {
            "strategies": ["wrong_implementation", "misleading_comment"],
            "injection_rate": 0.3,
            "description": "Simple bugs and obvious misleading hints",
        },
        "medium": {
            "strategies": [
                "wrong_implementation",
                "misleading_comment",
                "wrong_dependency_hint",
            ],
            "injection_rate": 0.5,
            "description": "Subtle bugs and plausible misleading advice",
        },
        "hard": {
            "strategies": [
                "wrong_implementation",
                "misleading_comment",
                "wrong_dependency_hint",
                "confusing_variable_names",
            ],
            "injection_rate": 0.6,
            "description": "Very subtle bugs plus confusing code",
        },
        "extreme": {
            "strategies": [
                "wrong_implementation",
                "misleading_comment",
                "wrong_dependency_hint",
                "confusing_variable_names",
                "edge_case_trap",
            ],
            "injection_rate": 0.8,
            "description": "Multiple interacting bugs and misleading hints",
        },
        "mixed": {
            "strategies": [
                "wrong_implementation",
                "misleading_comment",
                "wrong_dependency_hint",
            ],
            "injection_rate": 0.5,
            "description": "Random mix of adversarial strategies",
        },
    }
    return configs[difficulty]


def generate_difficulty_based_dataset(
    input_file: str,
    output_dir: str,
    difficulty_mode: str = "single_single",
    num_problems: int = 100,
) -> str:
    """生成基于难度模式的adversarial dataset

    Args:
        input_file: 输入文件路径
        output_dir: 输出目录
        difficulty_mode: 难度模式
            - "single_single": 单一root cause单一inject (每个问题1个错误)
            - "single_multi": 单一root cause多次inject (同一错误注入多个subproblem)
            - "multi_multi": 多个root cause多次inject (多种错误注入多个subproblem)
        num_problems: 生成问题数量

    Returns:
        输出文件路径
    """
    import random
    from pathlib import Path

    with open(input_file, "r", encoding="utf-8") as f:
        problems = json.load(f)

    # 只取前num_problems个问题
    problems = problems[:num_problems]

    generator = LLMAdversarialGenerator.__new__(LLMAdversarialGenerator)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_path / f"adversarial_{difficulty_mode}_{timestamp}.json"

    print("=" * 80)
    print(f"生成 {difficulty_mode.upper()} 难度数据集")
    print(f"问题数量: {len(problems)}")
    print("=" * 80)

    adversarial_problems = []
    strategies = ["wrong_implementation", "misleading_comment", "wrong_dependency_hint",
                  "confusing_variable_names", "edge_case_trap"]

    for prob_idx, problem in enumerate(problems):
        adv_problem = copy.deepcopy(problem)
        adv_problem["adversarial_mode"] = difficulty_mode
        adv_problem["problem-id"] = f"{problem.get('problem-id')}_{difficulty_mode.upper()}"

        num_subproblems = len(problem.get("subproblems", []))

        if difficulty_mode == "single_single":
            # 每个问题只注入1个错误到1个subproblem
            if num_subproblems > 0:
                inject_idx = random.randint(0, num_subproblems - 1)
                strategy = random.choice(strategies)

                subproblem = adv_problem["subproblems"][inject_idx]
                result, anchor_id, anchor_value = generator.apply_rule_based_pollution(
                    subproblem['statement'], strategy, subproblem, return_anchor_info=True
                )

                adv_problem["subproblems"][inject_idx].update({
                    "statement": result,
                    "adversarial_type": strategy,
                    "adversarial_difficulty": difficulty_mode,
                    "anchor_id": f"anchor_{anchor_id}",
                    "anchor_value": anchor_value,
                    "is_injected": True,
                })

                print(f"  [{prob_idx+1}/{len(problems)}] {problem.get('problem-id')}: "
                      f"inject 1 error at subproblem {inject_idx+1}/{num_subproblems}")

        elif difficulty_mode == "single_multi":
            # 单一root cause，注入到多个subproblem（至少50%）
            if num_subproblems > 0:
                num_inject = max(1, int(num_subproblems * 0.5))
                inject_indices = random.sample(range(num_subproblems), num_inject)
                strategy = random.choice(strategies)  # 同一个策略

                for idx in inject_indices:
                    subproblem = adv_problem["subproblems"][idx]
                    result, anchor_id, anchor_value = generator.apply_rule_based_pollution(
                        subproblem['statement'], strategy, subproblem, return_anchor_info=True
                    )

                    adv_problem["subproblems"][idx].update({
                        "statement": result,
                        "adversarial_type": strategy,
                        "adversarial_difficulty": difficulty_mode,
                        "anchor_id": f"anchor_{anchor_id}",
                        "anchor_value": anchor_value,
                        "is_injected": True,
                    })

                print(f"  [{prob_idx+1}/{len(problems)}] {problem.get('problem-id')}: "
                      f"inject {num_inject} x {strategy} at {num_inject}/{num_subproblems} subproblems")

        elif difficulty_mode == "multi_multi":
            # 多个root cause，注入到多个subproblem（至少80%）
            if num_subproblems > 0:
                num_inject = max(1, int(num_subproblems * 0.8))
                inject_indices = random.sample(range(num_subproblems), num_inject)

                injected_strategies = []
                for idx in inject_indices:
                    subproblem = adv_problem["subproblems"][idx]
                    strategy = random.choice(strategies)  # 每次随机选择策略
                    injected_strategies.append(strategy)

                    result, anchor_id, anchor_value = generator.apply_rule_based_pollution(
                        subproblem['statement'], strategy, subproblem, return_anchor_info=True
                    )

                    adv_problem["subproblems"][idx].update({
                        "statement": result,
                        "adversarial_type": strategy,
                        "adversarial_difficulty": difficulty_mode,
                        "anchor_id": f"anchor_{anchor_id}",
                        "anchor_value": anchor_value,
                        "is_injected": True,
                    })

                print(f"  [{prob_idx+1}/{len(problems)}] {problem.get('problem-id')}: "
                      f"inject {num_inject} errors ({len(set(injected_strategies))} unique) "
                      f"at {num_inject}/{num_subproblems} subproblems")

        adversarial_problems.append(adv_problem)

    # 保存
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(adversarial_problems, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已保存: {output_file}")
    print(f"   总问题数: {len(adversarial_problems)}")

    # 统计
    total_injected = sum(
        sum(1 for sp in p.get("subproblems", []) if sp.get("is_injected"))
        for p in adversarial_problems
    )
    print(f"   总注入数: {total_injected}")

    return str(output_file)


__all__ = [
    "generate_llm_adversarial_dataset",
    "generate_two_stage_adversarial_dataset",
    "generate_difficulty_based_dataset",
    "LLMAdversarialGenerator",
]


