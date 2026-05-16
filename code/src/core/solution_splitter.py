"""
Solution Splitter - 将扁平的 solution 拆分成多轮交互格式
根据 subproblems 的依赖关系，按深度顺序拆分函数
"""

import ast
from typing import Dict, List, Any, Optional, Tuple


class SolutionSplitter:
    """拆分扁平的 Python solution 代码为多轮对话历史"""

    def __init__(self):
        pass

    def split_solution(
        self,
        solution_code: str,
        subproblems: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        将扁平的 solution 拆分为多轮对话历史

        Args:
            solution_code: 完整的 Python 代码字符串
            subproblems: 子问题列表，包含 name, depth, dependencies 等

        Returns:
            多轮对话历史，每轮包含：
            - turn_id: 轮次编号
            - context: 当前轮之前的所有代码
            - target: 当前轮要实现的代码
            - subproblem_names: 当前轮涉及的子问题名称
            - depth: 当前轮的深度
            - test_cases: 当前轮的测试用例
        """
        # 解析代码为 AST
        try:
            tree = ast.parse(solution_code)
        except SyntaxError as e:
            raise ValueError(f"无法解析 solution 代码: {e}")

        # 提取所有函数定义和全局变量
        global_vars = []
        functions = {}

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                func_code = ast.get_source_segment(solution_code, node)
                functions[node.name] = {
                    'name': node.name,
                    'code': func_code,
                    'lineno': node.lineno,
                }
            elif isinstance(node, ast.Assign):
                # 全局变量赋值
                var_code = ast.get_source_segment(solution_code, node)
                global_vars.append(var_code)

        # 按深度排序 subproblems（深度越大越基础，越先实现）
        sorted_subproblems = sorted(
            subproblems,
            key=lambda sp: sp.get('depth', 0),
            reverse=True
        )

        # 按深度分组
        depth_groups = {}
        for sp in sorted_subproblems:
            depth = sp.get('depth', 0)
            if depth not in depth_groups:
                depth_groups[depth] = []
            depth_groups[depth].append(sp)

        # 生成多轮对话历史
        turns = []
        context_code = "\n".join(global_vars) if global_vars else ""
        if context_code:
            context_code += "\n\n"

        turn_id = 0
        for depth in sorted(depth_groups.keys(), reverse=True):
            group = depth_groups[depth]

            # 当前轮要实现的函数
            target_funcs = []
            target_names = []
            test_cases = []

            for sp in group:
                func_name = sp.get('name')
                if func_name and func_name in functions:
                    target_funcs.append(functions[func_name]['code'])
                    target_names.append(func_name)
                    # 收集测试用例
                    sp_tests = sp.get('test_code', [])
                    test_cases.extend(self._format_test_cases(func_name, sp_tests))

            if not target_funcs:
                continue

            target_code = "\n\n".join(target_funcs)

            turns.append({
                'turn_id': turn_id,
                'context': context_code.strip(),
                'target': target_code.strip(),
                'subproblem_names': target_names,
                'depth': depth,
                'test_cases': test_cases,
                'dependencies': [sp.get('dependencies', []) for sp in group],
            })

            # 更新 context 为下一轮准备
            context_code += target_code + "\n\n"
            turn_id += 1

        return turns

    def _format_test_cases(
        self,
        func_name: str,
        test_code: List[Dict[str, Any]]
    ) -> List[str]:
        """格式化测试用例为可执行的断言"""
        cases = []
        for t in test_code[:5]:  # 限制测试用例数量
            inp = t.get('input', '')
            out = t.get('output', '')

            if not inp or out is None:
                continue

            try:
                import codecs
                inp_escaped_str = codecs.encode(str(inp), 'unicode_escape').decode('ascii')
                inp_obj = ast.literal_eval(inp_escaped_str)
                inp_escaped = repr(inp_obj)
            except Exception:
                inp_escaped = inp

            assertion = (
                f"assert str({func_name}(*{inp_escaped})).rstrip() == "
                f"str({repr(out)}).rstrip()"
            )
            cases.append(assertion)

        return cases

    def reconstruct_full_code(self, turns: List[Dict[str, Any]]) -> str:
        """从多轮对话历史重建完整代码"""
        if not turns:
            return ""

        # 取最后一轮的 context + target
        last_turn = turns[-1]
        context = last_turn.get('context', '')
        target = last_turn.get('target', '')

        full_code = context
        if context and target:
            full_code += "\n\n" + target
        elif target:
            full_code = target

        return full_code.strip()
