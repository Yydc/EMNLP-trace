"""
TraceBench 数据集生成器 (Enhanced Version)
------------------------------------------
功能：
1. 读取 CodeFlowBench/Codeforces 原始数据
2. 协调 ASTInjector 进行代码注入
3. 验证生成的 TraceBench 样本质量：
   - 原始代码必须通过测试 (original_error_type == "ok")
   - 注入后代码必须无法通过测试，且错误类型是 AssertionError (corrupted_error_type == "assert")
4. 自动重试机制，保证数据集生成的成功率

改进点：
- 优先生成逻辑错误而非运行时错误 (IndexError / ValueError / Timeout)
- 优先使用更贴近真实的逻辑 Bug 策略（boundary_condition_shift 等）
- 增加 Retry Loop 提升 yield rate
- 增强元数据记录（记录 error_type 等）
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

from .ast_injector import ASTInjector, CodeValidator
from .solution_splitter import SolutionSplitter

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TraceBenchGenerator:
    """生成高难度、高真实性的 TraceBench 数据集"""

    def __init__(self):
        self.ast_injector = ASTInjector()
        self.validator = CodeValidator()
        self.splitter = SolutionSplitter()

        # === 策略池定义 ===
        # 与 ASTInjector.strategies 完全对齐
        # 优先级：Tier 1 (逻辑隐蔽) > Tier 2 (边界/操作符/初始化) > Tier 3 (可选扩展)
        self.STRATEGY_TIERS = {
            "tier_1": [
                "boundary_condition_shift",   # 比较条件微调：i < n -> i <= n
                "off_by_one",                 # range 边界偏移
                "wrong_return_variable",      # return ans -> return res
                "missing_update_in_branch",   # if/else 某一支漏更新
                "arg_swap_call",              # 调用时 (l, r) 顺序反了
            ],
            "tier_2": [
                "wrong_operator",             # < -> <=, == -> != 等
                "initialization_error",       # ans = 0 -> ans = 1 (仅限累加器)
                "variable_shadowing",         # 用参数覆盖局部变量
                "loop_entry_condition",       # while 条件微调
                "statement_omission",         # 删掉 += / append / 简单赋值
            ],
            "tier_3": [
                # 预留：如果以后要加更“狠”的策略，可以放这里
            ],
        }

    # =================================================================
    # 主入口
    # =================================================================

    def generate_dataset(
        self,
        input_file: str,
        output_file: str,
        difficulty_mode: str = "single_single",  # single_single, single_multi, multi_multi
        num_problems: Optional[int] = None,
        split: str = "train",
        validate: bool = True,
        seed: Optional[int] = 42,
        max_retries: int = 10,  # 每个题目最大尝试次数
        code_strategies: Optional[List[str]] = None,
        multi_turn: bool = True,  # 是否生成多轮交互格式
        error_injection_frequency: int = 2,  # 每隔几轮注入一次错误
    ) -> str:
        """
        主入口：生成数据集文件
        """
        if seed is not None:
            random.seed(seed)

        start_time = time.time()
        logger.info(f"🚀 开始生成 TraceBench 数据集: mode={difficulty_mode}")
        logger.info(f"📂 输入: {input_file}")

        # 1. 加载数据
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                raw_problems = json.load(f)
        except Exception as e:
            logger.error(f"无法读取输入文件: {e}")
            return ""

        # 2. 预处理：只保留有 Solution 的题目
        problems_with_solution = [p for p in raw_problems if self._get_solution_code(p)]
        if num_problems is not None:
            problems = problems_with_solution[:num_problems]
        else:
            problems = problems_with_solution

        stats = {
            "success": 0,
            "skipped_no_solution": len(raw_problems) - len(problems_with_solution),
            "skipped_validation_failed": 0,
            "strategies_used": {},
        }

        logger.info(
            f"📝 原始题目数: {len(raw_problems)} | "
            f"有 Solution 的题目数: {len(problems_with_solution)} | "
            f"本次处理: {len(problems)}"
        )

        tracebench_data: List[Dict[str, Any]] = []

        # 3. 核心循环
        for idx, problem in enumerate(problems):
            prob_id = problem.get("problem-id", f"idx_{idx}")
            logger.info(f"▶ 处理题目 [{idx}/{len(problems)-1}] problem-id={prob_id}")

            best_entry: Optional[Dict[str, Any]] = None

            # --- 持久化Plan重试机制 ---
            # 策略：为每个问题生成一次plan，所有重试使用相同复杂度（不降级）
            # 配合放宽的验证标准，允许复杂注入有更高成功率
            subproblems = problem.get("subproblems", [])
            if subproblems:
                default_strats = self.STRATEGY_TIERS["tier_1"] + self.STRATEGY_TIERS["tier_2"]
                initial_plan = self._plan_injections(
                    len(subproblems),
                    difficulty_mode,
                    code_strategies or default_strats
                )
            else:
                initial_plan = None

            for attempt in range(max_retries):
                current_strategies = self._pick_strategies_for_attempt(
                    attempt, override=code_strategies
                )

                if multi_turn:
                    entry = self._process_multi_turn_problem(
                        problem=problem,
                        difficulty_mode=difficulty_mode,
                        strategies_pool=current_strategies,
                        split=split,
                        trace_counter=len(tracebench_data),
                        validate=validate,
                        injection_plan=initial_plan,
                    )
                else:
                    entry = self._process_single_problem(
                        problem=problem,
                        difficulty_mode=difficulty_mode,
                        strategies_pool=current_strategies,
                        split=split,
                        trace_counter=len(tracebench_data),
                        validate=validate,
                        injection_plan=initial_plan,
                    )

                if entry:
                    best_entry = entry
                    logger.info(
                        f"  ✅ [P{idx}|{prob_id}] 生成成功 "
                        f"(尝试 {attempt + 1}/{max_retries})"
                    )
                    break  # 本题成功生成一个样本，跳出重试循环

            if best_entry:
                tracebench_data.append(best_entry)
                stats["success"] += 1
                # 统计策略
                for inj in best_entry["injections"]:
                    st = inj["type"]
                    stats["strategies_used"][st] = stats["strategies_used"].get(st, 0) + 1
            else:
                logger.warning(
                    f"  ❌ [P{idx}|{prob_id}] 放弃 "
                    f"(所有 {max_retries} 次注入均未产生有效且失败的用例)"
                )
                stats["skipped_validation_failed"] += 1

            # 进度打印
            if (idx + 1) % 5 == 0:
                print(
                    f"Processing... {idx+1}/{len(problems)} | "
                    f"Success: {stats['success']}"
                )

        # 4. 保存结果
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tracebench_data, f, indent=2, ensure_ascii=False)

        duration = time.time() - start_time
        self._print_summary(stats, duration, str(output_path))

        return str(output_path)

    # =================================================================
    # 单题处理
    # =================================================================

    def _process_multi_turn_problem(
        self,
        problem: Dict[str, Any],
        difficulty_mode: str,
        strategies_pool: List[str],
        split: str,
        trace_counter: int,
        validate: bool,
        injection_plan: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个问题的多轮交互版本。
        将扁平的 solution 拆分为多轮，在指定轮次注入错误。
        """
        subproblems = problem.get("subproblems", [])
        original_code = self._get_solution_code(problem)

        if not original_code or not subproblems:
            return None

        # 建立函数到测试用例的映射，确保每轮都能填充对应的测试
        func_to_tests: Dict[str, List[str]] = {}
        for sp in subproblems:
            name = sp.get("name")
            tests = self._extract_test_cases([sp])
            if name and tests:
                func_to_tests[name] = tests

        # 使用 SolutionSplitter 拆分代码
        try:
            turns = self.splitter.split_solution(original_code, subproblems)
        except Exception as e:
            logger.debug(f"拆分 solution 失败: {e}")
            return None

        if not turns:
            return None

        # 确定在哪些轮次注入错误（按真实场景分布）
        # 50% 注入 1 个，30% 注入 2 个，20% 注入 3+ 个
        available_turns = list(range(1, len(turns)))  # 跳过第一轮（基础函数）

        if not available_turns:
            # 如果只有一轮，无法注入错误
            return None

        # 按分布决定注入数量
        rand_val = random.random()
        if rand_val < 0.5:
            num_injections = 1  # 50%
        elif rand_val < 0.8:
            num_injections = 2  # 30%
        else:
            num_injections = min(3 + random.randint(0, 1), len(available_turns))  # 20%: 3-4 个

        # 限制注入数量不超过可用轮次
        num_injections = min(num_injections, len(available_turns))

        # 随机选择要注入错误的轮次
        error_turns = sorted(random.sample(available_turns, num_injections))

        # 生成多轮交互历史
        conversation_history = []
        accumulated_code = ""

        for turn_idx, turn in enumerate(turns):
            context = turn.get('context', '')
            target = turn.get('target', '')
            base_tests = turn.get('test_cases', [])

            # 显式获取当前轮次涉及函数的测试用例
            current_turn_tests: List[str] = []
            for func_name in turn.get('subproblem_names', []):
                if func_name in func_to_tests:
                    current_turn_tests.extend(func_to_tests[func_name])
            if not current_turn_tests:
                current_turn_tests = base_tests

            # 是否在当前轮注入错误
            should_inject = turn_idx in error_turns

            if should_inject:
                # 注入错误
                injection_records = []
                corrupted_target = target

                # 选择一个子问题注入错误
                target_subproblems = turn.get('subproblem_names', [])
                if target_subproblems:
                    # 尝试所有策略组合，直到成功注入
                    injection_success = False

                    # 优先级策略：某些策略更容易成功
                    priority_strategies = [
                        'boundary_condition_shift',
                        'off_by_one',
                        'operator_swap',
                        'statement_omission',
                    ]
                    # 其他策略
                    other_strategies = [s for s in strategies_pool if s not in priority_strategies]
                    # 组合顺序：优先策略 + 其他策略
                    ordered_strategies = [s for s in priority_strategies if s in strategies_pool] + other_strategies

                    # 对每个函数和每个策略组合尝试
                    for target_func in target_subproblems:
                        if injection_success:
                            break
                        for strategy in ordered_strategies:
                            try:
                                # 在完整代码上注入，然后提取目标部分
                                full_code = context + "\n\n" + target if context else target
                                new_code, anchor_meta = self.ast_injector.inject_bug_and_anchor(
                                    original_code=full_code,
                                    strategy=strategy,
                                    function_name=target_func,
                                )

                                if new_code and anchor_meta:
                                    # 提取注入后的目标函数代码（优先 AST 定位，避免行号偏移导致 def 丢失）
                                    func_slice = self._extract_function_code(new_code, target_func)
                                    if func_slice:
                                        corrupted_target = func_slice
                                    else:
                                        if context:
                                            context_lines = len(context.split('\n'))
                                            new_lines = new_code.split('\n')
                                            corrupted_target = '\n'.join(new_lines[context_lines:]).strip()
                                        else:
                                            corrupted_target = new_code

                                    # 快速验证：确保注入真的改变了代码
                                    if corrupted_target != target:
                                        injection_records.append({
                                            'strategy': strategy,
                                            'anchor': anchor_meta,
                                            'target_func': target_func,
                                            'turn_idx': turn_idx,
                                        })
                                        injection_success = True
                                        break
                            except Exception as e:
                                logger.debug(f"注入失败 ({target_func}, {strategy}): {e}")
                                continue

                    if not injection_success:
                        # 所有策略都失败了，尝试使用保底策略
                        logger.debug(f"Turn {turn_idx}: 常规策略失败，尝试保底策略")
                        for target_func in target_subproblems:
                            try:
                                full_code = context + "\n\n" + target if context else target
                                new_code, anchor_meta = self.ast_injector.inject_bug_and_anchor(
                                    original_code=full_code,
                                    strategy='early_return_fallback',
                                    function_name=target_func,
                                )

                                if new_code and anchor_meta:
                                    func_slice = self._extract_function_code(new_code, target_func)
                                    if func_slice:
                                        corrupted_target = func_slice
                                    else:
                                        if context:
                                            context_lines = len(context.split('\n'))
                                            new_lines = new_code.split('\n')
                                            corrupted_target = '\n'.join(new_lines[context_lines:]).strip()
                                        else:
                                            corrupted_target = new_code

                                    if corrupted_target != target:
                                        injection_records.append({
                                            'strategy': 'early_return_fallback',
                                            'anchor': anchor_meta,
                                            'target_func': target_func,
                                            'turn_idx': turn_idx,
                                        })
                                        injection_success = True
                                        logger.debug(f"Turn {turn_idx}: 保底策略成功")
                                        break
                            except Exception as e:
                                logger.debug(f"保底策略也失败 ({target_func}): {e}")
                                continue

                        if not injection_success:
                            # 连保底策略都失败了，使用原始代码
                            logger.warning(f"Turn {turn_idx}: 所有策略（包括保底）均失败")
                            corrupted_target = target

                turn_data = {
                    'turn_id': turn_idx,
                    'subproblems': turn.get('subproblem_names', []),
                    'depth': turn.get('depth', 0),
                    'context': context,
                    'target_code': corrupted_target,
                    'original_target_code': target,
                    'has_error': should_inject and bool(injection_records),
                    'injections': injection_records if should_inject else [],
                    'test_cases': current_turn_tests,
                }

                accumulated_code = context + "\n\n" + corrupted_target if context else corrupted_target
            else:
                # 正常轮次：不注入错误，但注入 Dummy Anchor 防止信息泄露
                target_funcs = turn.get('subproblem_names', [])
                dummy_injected_code = target

                if target_funcs:
                    func_to_anchor = random.choice(target_funcs)
                    try:
                        full_code = context + "\n\n" + target if context else target
                        new_code, _ = self.ast_injector.inject_bug_and_anchor(
                            original_code=full_code,
                            strategy="anchor_only",
                            function_name=func_to_anchor,
                        )

                        if new_code:
                            func_slice = self._extract_function_code(new_code, func_to_anchor)
                            if func_slice:
                                dummy_injected_code = func_slice
                            else:
                                if context:
                                    context_lines = len(context.split('\n'))
                                    new_lines = new_code.split('\n')
                                    dummy_injected_code = '\n'.join(new_lines[context_lines:]).strip()
                                else:
                                    dummy_injected_code = new_code
                    except Exception:
                        pass

                turn_data = {
                    'turn_id': turn_idx,
                    'subproblems': turn.get('subproblem_names', []),
                    'depth': turn.get('depth', 0),
                    'context': context,
                    'target_code': dummy_injected_code,
                    'original_target_code': target,
                    'has_error': False,
                    'injections': [],
                    'test_cases': current_turn_tests,
                }

                accumulated_code = context + "\n\n" + dummy_injected_code if context else dummy_injected_code

            conversation_history.append(turn_data)

        # 验证最终的累积代码
        if validate:
            final_test_cases = []
            for turn in conversation_history:
                final_test_cases.extend(turn.get('test_cases', []))

            # 只进行基本的语法检查，不要求注入后的代码必须失败
            # 这是因为多轮交互中，某些轮次可能注入失败，但整体依然有价值
            try:
                import ast as ast_module
                ast_module.parse(accumulated_code)
            except SyntaxError:
                return None

            # 如果有注入记录，尝试验证（但不强制要求失败）
            if any(turn.get('has_error') for turn in conversation_history):
                val_result = self.validator.validate_injection(
                    corrupted_code=accumulated_code,
                    test_cases=final_test_cases,
                    original_code=original_code,
                )

                # 原始代码必须通过
                if val_result.get('original_error_type') != 'ok':
                    return None

                # 放宽条件：只要注入后的代码不是完全正确即可
                # 允许 assert / runtime_error / timeout 等多种错误类型
                corrupted_error = val_result.get('corrupted_error_type')
                if corrupted_error == 'ok':
                    # 注入没有生效，但不完全放弃，降低错误标记
                    for turn in conversation_history:
                        if turn.get('has_error'):
                            turn['has_error'] = False
                            turn['injections'] = []

        # 构造 TraceBench entry
        trace_id = f"TB_MT_{split}_{trace_counter:05d}"
        original_id = problem.get("problem-id", "unknown")

        all_injections = []
        for turn in conversation_history:
            for inj in turn.get('injections', []):
                all_injections.append({
                    'injection_id': f"INJ_T{turn['turn_id']:02d}",
                    'type': inj['strategy'],
                    'turn_id': inj['turn_idx'],
                    'description': self._get_strategy_desc(inj['strategy']),
                    'location': {
                        'function': inj['target_func'],
                        'line_approx': inj['anchor'].get('anchor_line'),
                    },
                    'anchor': {
                        'anchor_func_name': inj['anchor'].get('anchor_func_name'),
                        'anchor_line': inj['anchor'].get('anchor_line'),
                        'anchor_value': inj['anchor'].get('anchor_value'),
                    },
                })

        return {
            'trace_id': trace_id,
            'original_source_id': f"CodeFlow_{original_id}",
            'task_description': (
                'Debug the code through multi-turn interaction. '
                'Some turns contain logical errors that need to be fixed.'
            ),
            'multi_turn': True,
            'conversation_history': conversation_history,
            'meta_data': {
                'difficulty_level': self._get_difficulty_level(difficulty_mode),
                'difficulty_desc': difficulty_mode,
                'num_turns': len(conversation_history),
                'error_turns': error_turns,
                'num_injections': len(all_injections),
            },
            'injections': all_injections,
            'original_code': original_code,
        }

    def _process_single_problem(
        self,
        problem: Dict[str, Any],
        difficulty_mode: str,
        strategies_pool: List[str],
        split: str,
        trace_counter: int,
        validate: bool,
        injection_plan: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个问题的一次尝试。
        成功则返回 TraceBench entry，失败返回 None。
        """
        subproblems = problem.get("subproblems", [])
        original_code = self._get_solution_code(problem)

        if not original_code or not subproblems:
            return None

        # 预先提取测试用例（避免重复）
        test_cases = self._extract_test_cases(subproblems)
        if not test_cases:
            # 没有测试用例，无法验证 TraceBench 有效性，跳过
            return None

        # 1. 规划注入方案 (如果没有提供预生成的plan，则生成新的)
        if injection_plan is None:
            plan = self._plan_injections(len(subproblems), difficulty_mode, strategies_pool)
        else:
            # 使用提供的plan骨架，但重新随机选择策略
            plan = {
                "inject_indices": injection_plan["inject_indices"][:],
                "strategies": [random.choice(strategies_pool) for _ in injection_plan["inject_indices"]],
                "root_cause_indices": injection_plan["root_cause_indices"].copy(),
            }
        if not plan["inject_indices"]:
            return None

        # 2. 执行 AST 注入（可能多次，multi_multi / single_multi）
        corrupted_code = original_code
        injection_records = []

        try:
            for idx, strategy in zip(plan["inject_indices"], plan["strategies"]):
                target_func = subproblems[idx].get("name")

                new_code, anchor_meta = self.ast_injector.inject_bug_and_anchor(
                    original_code=corrupted_code,
                    strategy=strategy,
                    function_name=target_func,
                )

                if new_code and anchor_meta:
                    corrupted_code = new_code
                    injection_records.append(
                        {
                            "strategy": strategy,
                            "anchor": anchor_meta,
                            "is_root_cause": idx in plan["root_cause_indices"],
                            "target_func": target_func,
                        }
                    )
        except Exception as e:
            logger.debug(f"注入过程中发生异常，放弃本次尝试: {e}")
            return None

        if not injection_records:
            return None

        # 3. 验证阶段 (Quality Gate)
        eval_block: Dict[str, Any] = {
            "test_cases": test_cases,
            "expected_output": "All tests pass",
            "ground_truth_patch": "The model should fix the logic errors identified by the injections.",
        }

        if validate:
            val_result = self.validator.validate_injection(
                corrupted_code=corrupted_code,
                test_cases=test_cases,
                original_code=original_code,
            )

            # 基本要求：语法 OK
            if not val_result.get("valid", False) or not val_result.get("syntax_ok", False):
                return None

            # 原始代码必须完全正确
            if val_result.get("original_error_type") != "ok":
                return None

            # 我们只保留“逻辑错误导致断言失败”的样本:
            # corrupted_error_type 必须是 "assert"
            if val_result.get("corrupted_error_type") != "assert":
                return None

            eval_block["original_error_type"] = val_result.get("original_error_type")
            eval_block["corrupted_error_type"] = val_result.get("corrupted_error_type")
            eval_block["validator_error_msg"] = val_result.get("error_msg")

        # 4. 构造 TraceBench entry
        trace_id = f"TB_{split}_{trace_counter:05d}"
        original_id = problem.get("problem-id", "unknown")

        return {
            "trace_id": trace_id,
            "original_source_id": f"CodeFlow_{original_id}",
            "task_description": (
                "Debug the following code. It contains logical errors that cause it to fail tests."
            ),
            "code_context": {
                "file_path": f"problem_{original_id}.py",
                "corrupted_code": corrupted_code,
                "entry_point": subproblems[0].get("name", "main") if subproblems else "main",
            },
            "meta_data": {
                "difficulty_level": self._get_difficulty_level(difficulty_mode),
                "difficulty_desc": difficulty_mode,
                "num_injections": len(injection_records),
                "root_causes": [
                    r["strategy"] for r in injection_records if r["is_root_cause"]
                ],
            },
            "injections": [
                {
                    "injection_id": f"INJ_{i+1:02d}",
                    "type": rec["strategy"],
                    "is_root_cause": rec["is_root_cause"],
                    "description": self._get_strategy_desc(rec["strategy"]),
                    "location": {
                        "function": rec["target_func"],
                        "line_approx": rec["anchor"].get("anchor_line"),
                    },
                    "anchor": {
                        "anchor_func_name": rec["anchor"].get("anchor_func_name"),
                        "anchor_line": rec["anchor"].get("anchor_line"),
                        "anchor_value": rec["anchor"].get("anchor_value"),
                    },
                }
                for i, rec in enumerate(injection_records)
            ],
            "evaluation": eval_block,
            "original_code": original_code,
        }

    # =================================================================
    # 策略/计划相关
    # =================================================================

    def _pick_strategies_for_attempt(
        self,
        attempt: int,
        override: Optional[List[str]] = None,
    ) -> List[str]:
        """
        根据尝试次数选择策略池；
        若提供 override 则直接使用该列表作为策略池。
        """
        if override:
            return list(override)

        # 尝试 0-2: 优先使用 Tier 1 + 部分 Tier 2
        if attempt < 3:
            return self.STRATEGY_TIERS["tier_1"] + self.STRATEGY_TIERS["tier_2"]

        # 尝试 3+：混入 Tier 3（目前为空，可以以后扩展）
        return (
            self.STRATEGY_TIERS["tier_1"]
            + self.STRATEGY_TIERS["tier_2"]
            + self.STRATEGY_TIERS["tier_3"]
        )

    def _plan_injections(self, num_subs: int, mode: str, strategies: List[str]) -> Dict[str, Any]:
        """
        规划注入：确定注入位置和策略组合。
        返回：
        {
          "inject_indices": [sub_idx, ...],
          "strategies": [strategy_name, ...],
          "root_cause_indices": set(...)
        }
        """
        plan = {"inject_indices": [], "strategies": [], "root_cause_indices": set()}

        if num_subs <= 0 or not strategies:
            return plan

        indices = list(range(num_subs))
        random.shuffle(indices)

        if mode == "single_single":
            # 1 个注入，1 个 Root Cause
            target_idx = indices[0]
            plan["inject_indices"].append(target_idx)
            plan["strategies"].append(random.choice(strategies))
            plan["root_cause_indices"].add(target_idx)

        elif mode == "single_multi":
            # 多个注入，全是同一个策略，只有 1 个是 Root Cause (噪音注入场景)
            count = min(len(indices), max(2, int(len(indices) * 0.5)))
            selected = indices[:count]
            strat = random.choice(strategies)

            plan["inject_indices"] = selected
            plan["strategies"] = [strat] * count
            plan["root_cause_indices"].add(selected[0])  # 假设第一个是主要原因

        elif mode == "multi_multi":
            # 多个注入，多种策略，多个 Root Cause (困难模式)
            count = min(len(indices), max(2, int(len(indices) * 0.8)))
            selected = indices[:count]

            plan["inject_indices"] = selected
            plan["strategies"] = [random.choice(strategies) for _ in selected]

            # 随机选 1 到 count 个作为 Root Cause（这里只是"计划上的" Root Cause）
            num_roots = random.randint(1, count)
            for i in range(num_roots):
                plan["root_cause_indices"].add(selected[i])

        elif mode == "mixed":
            # 混合模式：补偿性分布 + 放宽验证
            # 目标最终分布: 50% 单，35% 双，15% 三+ (更现实)
            # 假设成功率: 单95%, 双40%, 三20% (放宽验证后提升)
            # 规划分布: 24% 单，41% 双，35% 三+ (补偿失败率)
            rand = random.random()
            if rand < 0.24:
                # 单错误 (24%)
                target_idx = indices[0]
                plan["inject_indices"].append(target_idx)
                plan["strategies"].append(random.choice(strategies))
                plan["root_cause_indices"].add(target_idx)
            elif rand < 0.65:  # 0.24 + 0.41
                # 双错误 (41%)
                count = min(2, len(indices))
                selected = indices[:count]
                plan["inject_indices"] = selected
                plan["strategies"] = [random.choice(strategies) for _ in selected]
                # 随机选 1-2 个作为 root cause
                num_roots = random.randint(1, count)
                for i in range(num_roots):
                    plan["root_cause_indices"].add(selected[i])
            else:
                # 三+ 错误 (35%)，符合真实调试场景
                count = min(len(indices), max(3, int(len(indices) * 0.6)))
                selected = indices[:count]
                plan["inject_indices"] = selected
                plan["strategies"] = [random.choice(strategies) for _ in selected]
                # 多个 root cause
                num_roots = random.randint(2, count)
                for i in range(num_roots):
                    plan["root_cause_indices"].add(selected[i])

        return plan

    # =================================================================
    # 工具函数
    # =================================================================

    def _get_solution_code(self, problem: Dict[str, Any]) -> Optional[str]:
        """从 problem 中提取 AC 代码"""
        return problem.get("solution") or problem.get("reference_code")

    def _extract_function_code(self, full_code: str, func_name: str) -> Optional[str]:
        """
        从完整代码中提取指定函数的源码，避免依赖行号切片导致 def 头丢失。
        """
        try:
            import ast

            tree = ast.parse(full_code)
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == func_name:
                    return ast.unparse(node).strip()
        except Exception:
            return None
        return None

    def _extract_test_cases(self, subproblems: List[Dict[str, Any]]) -> List[str]:
        """
        提取测试用例，并修复参数调用格式问题。
        关键点：
        - 使用 *inp 进行参数解包，兼容 (args) 和 ['arg'] 格式。
        - 对 input 中的换行做 unicode_escape + literal_eval + repr，保证 Python 语法合法。
        - 使用 str(...).rstrip() 比较，兼容 int/str 与尾部换行差异。
        """
        cases: List[str] = []
        for sp in subproblems:
            name = sp.get("name")
            tests = sp.get("test_code", [])

            if not name or not isinstance(tests, list):
                continue

            # 限制每个 subproblem 的测试数量，防止运行太慢
            for t in tests[:3]:
                inp = t.get("input", "")
                out = t.get("output", "")

                if not inp or out is None:
                    continue

                # 对 inp 做安全的 parse + repr
                # 示例：
                #   "(5, [1, 2])"   -> func(*(5, [1, 2]))
                #   "['3\\n5']"     -> func(*['3\\n5'])
                try:
                    import ast as ast_module
                    import codecs

                    # 把真实换行编码为 \n 文本
                    inp_escaped_str = codecs.encode(inp, "unicode_escape").decode("ascii")
                    # 用 literal_eval 转成 Python 对象
                    inp_obj = ast_module.literal_eval(inp_escaped_str)
                    # 再用 repr 序列化为合法 Python 表达式
                    inp_escaped = repr(inp_obj)
                except Exception:
                    # 解析失败就退化使用原始字符串（有风险，但比直接挂好）
                    inp_escaped = inp

                # 使用 str() + rstrip() 做宽松比较
                assertion = (
                    f"assert str({name}(*{inp_escaped})).rstrip() == "
                    f"str({repr(out)}).rstrip()"
                )
                cases.append(assertion)

        return cases

    def _get_difficulty_level(self, mode: str) -> int:
        mapping = {"single_single": 1, "single_multi": 2, "multi_multi": 3, "mixed": 2}
        return mapping.get(mode, 1)

    def _get_strategy_desc(self, strategy: str) -> str:
        descs = {
            "boundary_condition_shift": (
                "Slightly shifts boundary conditions (e.g., i < n → i <= n)."
            ),
            "off_by_one": "Loop or index boundary error around range/indices.",
            "wrong_return_variable": (
                "Returns a wrong but similar-looking variable (e.g., ans vs res)."
            ),
            "missing_update_in_branch": (
                "Missing a state update in one branch of an if/else."
            ),
            "arg_swap_call": (
                "Swaps paired arguments in a function call (e.g., l,r or x,y)."
            ),
            "wrong_operator": "Incorrect comparison or arithmetic operator.",
            "initialization_error": (
                "Incorrect initialization of accumulator variables (0 ↔ 1)."
            ),
            "variable_shadowing": (
                "Overrides a local variable using a function argument value."
            ),
            "loop_entry_condition": "Alters while-loop entry logic slightly.",
            "statement_omission": "Removes a critical logic statement (e.g., += or append).",
        }
        return descs.get(strategy, "Unknown Logic Error")

    def _print_summary(self, stats: Dict[str, Any], duration: float, output_file: str):
        print("\n" + "=" * 50)
        print(f"🏁 TraceBench 生成完成 (耗时: {duration:.2f}s)")
        print(f"📄 输出文件: {output_file}")
        print("-" * 30)
        print(f"✅ 成功生成: {stats['success']}")
        print(f"⏭️  跳过 (无Solution): {stats['skipped_no_solution']}")
        print(f"❌ 跳过 (无法生成Fail用例): {stats['skipped_validation_failed']}")
        print("-" * 30)
        print("📊 策略分布:")
        for k, v in stats["strategies_used"].items():
            print(f"   - {k}: {v}")
        print("=" * 50 + "\n")
