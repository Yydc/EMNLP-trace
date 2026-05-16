import ast
import random
import string
import sys
import signal
from contextlib import contextmanager
from typing import Dict, Any, Optional, Tuple, List, Set


class ASTInjector:
    """
    AST 注入器：负责将逻辑错误和 Trace 锚点注入到源代码中。

    设计目标：
    - 更贴近真实世界中人类会犯的逻辑错误（尤其是边界、计数、状态维护相关）。
    - 尽量避免 TypeError / IndexError 这类硬崩，而是让测试通过/失败来体现差异。
    - 让 bug 分散在多处逻辑链条里，不是一眼就能看出的 “if 写反了”。
    """

    def __init__(self):
        # Tier 1: 更真实、更隐蔽的逻辑错误
        self.strategies = {
            "boundary_condition_shift": self._inject_boundary_condition_shift,
            "off_by_one": self._inject_off_by_one,
            "wrong_return_variable": self._inject_wrong_return_variable,
            "missing_update_in_branch": self._inject_missing_update_in_branch,
            "arg_swap_call": self._inject_arg_swap_call,

            # Tier 2: 稍显眼但依然常见的逻辑错误 / 兼容旧策略
            "wrong_operator": self._inject_wrong_operator,
            "initialization_error": self._inject_initialization_error,
            "variable_shadowing": self._inject_variable_shadowing,
            "loop_entry_condition": self._inject_loop_entry_condition,
            "statement_omission": self._inject_statement_omission,

            # Fallback: 保底策略，几乎总是能成功
            "early_return_fallback": self._inject_early_return_fallback,

            # Anchor-only: 仅插入 anchor，保持逻辑不变
            "anchor_only": self._inject_anchor_only,
        }

    # =================================================================
    # Public API
    # =================================================================

    def inject_bug_and_anchor(
        self,
        original_code: str,
        strategy: str,
        function_name: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        对 original_code 进行单点注入，返回 (corrupted_code, metadata)。

        metadata 中包含：
        - anchor_id / anchor_value / anchor_func_name
        - anchor_line（在最终代码中的行号）
        - target_function
        - strategy
        """
        try:
            tree = ast.parse(original_code)
        except SyntaxError:
            return None, None

        # 为所有节点添加 parent 指针，便于精准插入 Anchor
        self._add_parent_pointers(tree)

        # 1. 生成 Anchor 数据
        anchor_id = ''.join(random.choices(string.ascii_lowercase, k=6))
        anchor_val = f"TRACER_{random.randint(1000, 9999)}"

        # 2. 定位目标函数
        target_func = self._find_target_function(tree, function_name)
        if not target_func:
            return None, None

        # 3. 准备 Anchor 节点
        anchor_def, anchor_call = self._create_anchor_nodes(anchor_id, anchor_val)

        # 4. 执行注入
        injector = self.strategies.get(strategy)
        if not injector:
            return None, None

        success, bug_lineno = injector(target_func, anchor_def, anchor_call)
        if not success:
            return None, None

        # 5. 将 Anchor 定义插入到目标函数内部（docstring 之后）
        self._insert_node_after_docstring(target_func, anchor_def)

        # 6. 生成代码并重新解析，获取 Anchor 的真实行号
        try:
            ast.fix_missing_locations(tree)
            corrupted_code = ast.unparse(tree)
        except Exception:
            return None, None

        anchor_line = bug_lineno
        try:
            new_tree = ast.parse(corrupted_code)
            self._add_parent_pointers(new_tree)
            lineno = self._find_anchor_call_lineno(new_tree, anchor_def.name)
            if lineno:
                anchor_line = lineno
        except SyntaxError:
            pass

        metadata = {
            "anchor_id": anchor_id,
            "anchor_value": anchor_val,
            "anchor_func_name": anchor_def.name,
            "anchor_line": anchor_line,
            "target_function": target_func.name,
            "strategy": strategy,
        }

        return corrupted_code, metadata

    # =================================================================
    # Helper Methods
    # =================================================================

    def _add_parent_pointers(self, tree: ast.AST):
        """遍历 AST，给每个节点添加 parent 属性。"""
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                child.parent = node

    def _create_anchor_nodes(self, a_id: str, a_val: str) -> Tuple[ast.FunctionDef, ast.Expr]:
        func_name = f"anchor_{a_id}"
        anchor_def = ast.FunctionDef(
            name=func_name,
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=[
                ast.Return(value=ast.Constant(value=a_val)),
            ],
            decorator_list=[],
        )
        anchor_call = ast.Expr(
            value=ast.Call(func=ast.Name(id=func_name, ctx=ast.Load()), args=[], keywords=[])
        )
        return anchor_def, anchor_call

    def _insert_node_after_docstring(self, func_node: ast.FunctionDef, new_node: ast.AST):
        """将 new_node 插入到函数体的 docstring 之后（如果存在），否则插在最前面。"""
        if (
            func_node.body
            and isinstance(func_node.body[0], ast.Expr)
            and isinstance(func_node.body[0].value, ast.Constant)
            and isinstance(func_node.body[0].value.value, str)
        ):
            func_node.body.insert(1, new_node)
        else:
            func_node.body.insert(0, new_node)

    def _find_target_function(self, tree: ast.AST, name: Optional[str]) -> Optional[ast.FunctionDef]:
        """优先选择 solve / main，其次选择 body 最大的函数。"""
        funcs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("anchor_")
        ]
        if not funcs:
            return None

        if name:
            for f in funcs:
                if f.name == name:
                    return f

        preferred = ["solve", "main", "solution"]
        for pref in preferred:
            for f in funcs:
                if f.name == pref:
                    return f

        # 退化：选择语句数量最多的函数
        return max(funcs, key=lambda f: len(f.body))

    def _find_anchor_call_lineno(self, tree: ast.AST, anchor_name: str) -> int:
        """在最终代码的 AST 中找到 anchor 调用的行号。"""
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == anchor_name
            ):
                return getattr(node, "lineno", 0)
        return 0

    def _get_enclosing_stmt_list(self, node: ast.AST) -> Tuple[Optional[List[ast.stmt]], Optional[int]]:
        """
        向上查找，直到找到包含该节点的语句列表 (body)。
        用于在表达式前插入语句。
        """
        curr = node
        while hasattr(curr, "parent"):
            parent = curr.parent
            for _field, value in ast.iter_fields(parent):
                if isinstance(value, list) and curr in value:
                    # 仅当该列表元素都是语句时，才认为它是语句容器
                    if all(isinstance(item, ast.stmt) for item in value):
                        return value, value.index(curr)
            curr = parent
        return None, None

    def _find_stmt_and_container(self, node: ast.AST) -> Tuple[Optional[List[ast.stmt]], Optional[int]]:
        """
        寻找最近的语句及其容器，用于表达式场景（如 BoolOp.values）。
        """
        curr = node
        while hasattr(curr, "parent"):
            parent = curr.parent
            if isinstance(curr, ast.stmt):
                for _field, value in ast.iter_fields(parent):
                    if (
                        isinstance(value, list)
                        and curr in value
                        and all(isinstance(item, ast.stmt) for item in value)
                    ):
                        return value, value.index(curr)
            curr = parent
        return None, None

    def _inject_anchor_near_node(
        self, func_root: ast.FunctionDef, target_node: ast.AST, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """使用 parent 指针精准插入 Anchor（插在 target_node 之前）。"""
        stmt_list, idx = self._get_enclosing_stmt_list(target_node)
        if stmt_list is None:
            # 如果目标位于表达式列表（如 BoolOp.values），尝试找到最近的语句容器
            stmt_list, idx = self._find_stmt_and_container(target_node)
        if stmt_list is not None and idx is not None:
            stmt_list.insert(idx, anchor_call)
            return True, getattr(target_node, "lineno", 0)

        # Fallback：插在函数开头
        self._insert_node_after_docstring(func_root, anchor_call)
        return True, getattr(target_node, "lineno", 0)

    # 一些通用的启发式

    def _is_index_like(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            name = node.id.lower()
            return any(k in name for k in ["i", "j", "k", "idx", "id", "pos", "ptr"])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len":
            return True
        return False

    def _is_size_like(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            name = node.id.lower()
            return any(k in name for k in ["n", "m", "size", "len", "cnt", "count", "limit"])
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return True
        return False

    def _is_accumulator_name(self, name: str) -> bool:
        name = name.lower()
        return any(k in name for k in ["ans", "res", "sum", "total", "cnt", "count"])

    def _similar_name(self, a: str, b: str) -> bool:
        """用于 wrong_return_variable：找看起来相近的局部变量名。"""
        if a == b:
            return False
        a_low, b_low = a.lower(), b.lower()
        if a_low[0] == b_low[0]:
            return True
        if a_low in b_low or b_low in a_low:
            return True
        if abs(len(a_low) - len(b_low)) <= 1 and a_low[0] == b_low[0]:
            return True
        return False

    def _is_pair_name(self, a: str, b: str) -> bool:
        """用于 arg_swap_call：判断是否像 (l,r)/(x,y)/(i,j) 这样的配对参数。"""
        a, b = a.lower(), b.lower()
        pair = {a, b}
        return pair in ({"l", "r"}, {"x", "y"}, {"i", "j"})

    # =================================================================
    # Tier 1 Strategies：更贴近真实 bug
    # =================================================================

    def _inject_boundary_condition_shift(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        边界条件轻微偏移：
        - i < n  ↔ i <= n
        - i > 0  ↔ i >= 0
        - len(s) == 0 → len(s) <= 0 / >= 0

        只对 index-like vs size-like 的比较生效，模拟 off-by-one / 包含性错误。
        """
        candidates: List[ast.Compare] = []
        for node in ast.walk(func):
            if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                continue
            left = node.left
            right = node.comparators[0]
            op = node.ops[0]

            if not isinstance(
                op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq)
            ):
                continue

            # index-like < size-like
            if self._is_index_like(left) and self._is_size_like(right):
                candidates.append(node)
            # size-like > index-like
            elif self._is_size_like(left) and self._is_index_like(right):
                candidates.append(node)

        if not candidates:
            return False, 0

        target = random.choice(candidates)
        op = target.ops[0]

        if isinstance(op, ast.Lt):
            target.ops[0] = ast.LtE()
        elif isinstance(op, ast.LtE):
            target.ops[0] = ast.Lt()
        elif isinstance(op, ast.Gt):
            target.ops[0] = ast.GtE()
        elif isinstance(op, ast.GtE):
            target.ops[0] = ast.Gt()
        elif isinstance(op, ast.Eq):
            # 这个等号的情况稍微重一点，随机成 <= 或 >=
            target.ops[0] = ast.LtE() if random.random() < 0.5 else ast.GtE()

        return self._inject_anchor_near_node(func, target, anchor_call)

    def _inject_off_by_one(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        对 range 的边界进行轻微偏移：
        - range(n) → range(n-1) / range(n+1)
        - range(l, r) → range(l, r-1) / range(l, r+1)

        主要产生“漏掉最后一个元素”这类错误，偶尔产生“多做一次”的错误。
        """
        candidates: List[ast.Call] = []
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "range"
                and 1 <= len(node.args) <= 2
            ):
                candidates.append(node)

        if not candidates:
            return False, 0

        target = random.choice(candidates)

        if len(target.args) == 1:
            end = target.args[0]
            # 大部分情况：缩小范围（range(n-1)）
            if random.random() < 0.7:
                target.args[0] = ast.BinOp(left=end, op=ast.Sub(), right=ast.Constant(value=1))
            else:
                target.args[0] = ast.BinOp(left=end, op=ast.Add(), right=ast.Constant(value=1))
        else:
            start, end = target.args
            # 只改右边界，模拟 [l, r) vs [l, r] 的混淆
            if random.random() < 0.7:
                target.args[1] = ast.BinOp(left=end, op=ast.Sub(), right=ast.Constant(value=1))
            else:
                target.args[1] = ast.BinOp(left=end, op=ast.Add(), right=ast.Constant(value=1))

        return self._inject_anchor_near_node(func, target, anchor_call)

    def _inject_wrong_return_variable(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        返回了“相似名字”的错误变量：
        - return ans → return res
        - return total → return cnt

        这种错误在统计/DP 里非常常见，而且阅读时很容易忽略。
        """
        returns: List[ast.Return] = [
            n for n in ast.walk(func) if isinstance(n, ast.Return) and isinstance(n.value, ast.Name)
        ]
        if not returns:
            return False, 0

        # 收集局部变量名
        local_names: Set[str] = set()
        for n in ast.walk(func):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        local_names.add(t.id)
            elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                local_names.add(n.target.id)

        candidates: List[Tuple[ast.Return, List[str]]] = []
        for ret in returns:
            orig_name = ret.value.id
            if orig_name not in local_names:
                continue
            other_names = [nm for nm in local_names if self._similar_name(orig_name, nm)]
            if not other_names:
                continue
            candidates.append((ret, other_names))

        if not candidates:
            return False, 0

        target_ret, other_names = random.choice(candidates)
        new_name = random.choice(other_names)
        target_ret.value.id = new_name

        return self._inject_anchor_near_node(func, target_ret, anchor_call)

    def _inject_missing_update_in_branch(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        在 if/else 的某一支中漏掉对某个变量的更新：
        if cond:
            cnt += 1
            sum += x
        else:
            sum += x      # cnt += 1 被“删掉”

        实现：在一个分支中删除一次写操作（Assign/AugAssign），用 anchor 替代该语句。
        """
        if_nodes: List[ast.If] = [
            n for n in ast.walk(func) if isinstance(n, ast.If) and n.orelse
        ]
        if not if_nodes:
            return False, 0

        random.shuffle(if_nodes)

        def collect_writes(stmts: List[ast.stmt]) -> Dict[str, List[ast.stmt]]:
            writes: Dict[str, List[ast.stmt]] = {}
            for s in stmts:
                if isinstance(s, ast.AugAssign) and isinstance(s.target, ast.Name):
                    writes.setdefault(s.target.id, []).append(s)
                elif isinstance(s, ast.Assign):
                    for t in s.targets:
                        if isinstance(t, ast.Name):
                            writes.setdefault(t.id, []).append(s)
            return writes

        for if_node in if_nodes:
            body_writes = collect_writes(if_node.body)
            else_writes = collect_writes(if_node.orelse)
            common_vars = set(body_writes.keys()) & set(else_writes.keys())
            if not common_vars:
                continue

            var = random.choice(list(common_vars))
            branch_is_body = random.random() < 0.5
            branch_stmts = if_node.body if branch_is_body else if_node.orelse
            writes_map = body_writes if branch_is_body else else_writes

            stmts_for_var = writes_map.get(var)
            if not stmts_for_var:
                continue

            target_stmt = random.choice(stmts_for_var)
            try:
                idx = branch_stmts.index(target_stmt)
            except ValueError:
                continue

            bug_lineno = getattr(target_stmt, "lineno", 0)
            # 用 anchor_call 替换掉这条更新语句
            branch_stmts[idx] = anchor_call
            return True, bug_lineno

        return False, 0

    def _inject_arg_swap_call(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        调用时参数顺序反了：
        - update(l, r) → update(r, l)
        - add_edge(u, v) → add_edge(v, u)

        只处理前两个参数，且名字看起来是配对（l/r, x/y, i/j）。
        """
        calls: List[ast.Call] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and len(node.args) >= 2:
                a1, a2 = node.args[0], node.args[1]
                if isinstance(a1, ast.Name) and isinstance(a2, ast.Name):
                    if self._is_pair_name(a1.id, a2.id):
                        calls.append(node)

        if not calls:
            return False, 0

        target = random.choice(calls)
        target.args[0], target.args[1] = target.args[1], target.args[0]

        return self._inject_anchor_near_node(func, target, anchor_call)

    # =================================================================
    # Tier 2 Strategies：兼容旧逻辑，但做了安全性收紧
    # =================================================================

    def _inject_wrong_operator(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        更安全的运算符替换：
        - 优先改比较运算符（<, <=, >, >=, ==, !=）；
        - 对算术运算符，只在“看起来是计数/长度逻辑”的地方改，避免 list + int 崩溃。
        """
        # 先试比较运算符
        compares: List[ast.Compare] = [
            n for n in ast.walk(func) if isinstance(n, ast.Compare) and len(n.ops) == 1
        ]
        random.shuffle(compares)
        for target in compares:
            op = target.ops[0]
            op_map = {
                ast.Lt: ast.LtE,
                ast.LtE: ast.Lt,
                ast.Gt: ast.GtE,
                ast.GtE: ast.Gt,
                ast.Eq: ast.NotEq,
                ast.NotEq: ast.Eq,
            }
            if type(op) in op_map:
                target.ops[0] = op_map[type(op)]()
                return self._inject_anchor_near_node(func, target, anchor_call)

        # 再尝试算术运算符
        binops: List[ast.BinOp] = []
        for node in ast.walk(func):
            if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
            ):
                parent = getattr(node, "parent", None)
                safe = False

                # 1) 参与比较：if i + 1 < n
                if isinstance(parent, ast.Compare):
                    safe = True

                # 2) 赋值给累加器变量：cnt = i + 1
                if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
                    t = parent.targets[0]
                    if isinstance(t, ast.Name) and self._is_accumulator_name(t.id):
                        safe = True

                # 3) 两边都是数字字面量
                if isinstance(node.left, ast.Constant) and isinstance(
                    node.left.value, (int, float)
                ):
                    if isinstance(node.right, ast.Constant) and isinstance(
                        node.right.value, (int, float)
                    ):
                        safe = True

                if safe:
                    binops.append(node)

        if not binops:
            return False, 0

        target = random.choice(binops)
        if isinstance(target.op, ast.Add):
            target.op = ast.Sub()
        elif isinstance(target.op, ast.Sub):
            target.op = ast.Add()
        elif isinstance(target.op, ast.Mult):
            target.op = ast.Add()
        elif isinstance(target.op, ast.Div):
            target.op = ast.Mult()

        return self._inject_anchor_near_node(func, target, anchor_call)

    def _inject_initialization_error(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        初始值错误（温和版）：
        - 只修改名字看起来像累加器的变量（ans/res/sum/cnt/...）
        - 且只在值为 0/1 时进行 0 ↔ 1 切换。
        """
        candidates: List[ast.Assign] = []
        for n in ast.walk(func):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(
                n.value.value, int
            ):
                for t in n.targets:
                    if isinstance(t, ast.Name) and self._is_accumulator_name(t.id):
                        candidates.append(n)
                        break

        if not candidates:
            return False, 0

        target = random.choice(candidates)
        val = target.value.value
        if val == 0:
            target.value.value = 1
        elif val == 1:
            target.value.value = 0
        else:
            return False, 0

        return self._inject_anchor_near_node(func, target, anchor_call)

    def _inject_variable_shadowing(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        更贴切的诠释：用某个参数错误地覆盖了局部变量的值。
        例如：
            ok = False      -> ok = valid_val
        典型于“用配置/参数去初始化中间状态”，导致逻辑永远偏向某种情况。
        """
        safe_vars = [arg.arg for arg in func.args.args]
        if not safe_vars:
            return False, 0

        targets: List[ast.Assign] = []
        for n in ast.walk(func):
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                t = n.targets[0]
                if isinstance(t, ast.Name) and self._is_accumulator_name(t.id):
                    targets.append(n)

        # 没有明显累加器时，退而求其次，任意选择一个赋值
        if not targets:
            targets = [n for n in ast.walk(func) if isinstance(n, ast.Assign)]
        if not targets:
            return False, 0

        target_node = random.choice(targets)
        chosen_var = random.choice(safe_vars)
        target_node.value = ast.Name(id=chosen_var, ctx=ast.Load())

        return self._inject_anchor_near_node(func, target_node, anchor_call)

    def _inject_loop_entry_condition(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        while 循环入口条件的轻微改动，例如：
        - while x > 0 → while x >= 0
        这类错误也比较常见，但相对其它策略显得更直接一些。
        """
        loops = [n for n in ast.walk(func) if isinstance(n, ast.While)]
        if not loops:
            return False, 0

        target = random.choice(loops)
        if isinstance(target.test, ast.Compare) and len(target.test.ops) == 1:
            op = target.test.ops[0]
            if isinstance(op, ast.Gt):
                target.test.ops[0] = ast.GtE()
            elif isinstance(op, ast.GtE):
                target.test.ops[0] = ast.Gt()
            elif isinstance(op, ast.Lt):
                target.test.ops[0] = ast.LtE()
            elif isinstance(op, ast.LtE):
                target.test.ops[0] = ast.Lt()

        # 在循环体开头插入 anchor
        target.body.insert(0, anchor_call)
        return True, target.lineno

    def _inject_statement_omission(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        语句省略：
        - 优先删除 AugAssign (+=) 和简单的函数调用（如 append）
        - 仅在必要时删除简单的 Assign（右值为常量），避免删掉关键定义导致未定义异常。
        """
        aug_assigns: List[ast.AST] = []
        calls: List[ast.AST] = []
        assigns: List[ast.AST] = []

        for node in ast.walk(func):
            body_list, idx = self._get_enclosing_stmt_list(node)
            if body_list is None:
                continue

            if isinstance(node, ast.AugAssign):
                aug_assigns.append(node)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                calls.append(node)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                assigns.append(node)

        candidates: List[ast.AST] = aug_assigns + calls
        if not candidates and assigns:
            candidates = assigns

        if not candidates:
            return False, 0

        target = random.choice(candidates)
        body_list, idx = self._get_enclosing_stmt_list(target)
        if body_list is None or idx is None:
            return False, 0

        bug_lineno = getattr(target, "lineno", 0)
        body_list[idx] = anchor_call  # 用 Anchor 替换该语句
        return True, bug_lineno

    def _inject_early_return_fallback(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        保底策略：在函数中间位置插入提前返回。
        这个策略几乎总是能成功，用于确保高注入成功率。

        策略：
        1. 找到函数体的中间位置
        2. 插入 anchor 调用后立即返回一个默认值
        3. 根据函数的返回类型推断默认值（None, 0, False, [], {}等）
        """
        if not func.body or len(func.body) < 2:
            return False, 0

        # 找到合适的插入位置（跳过 docstring 和初始化语句）
        insert_idx = len(func.body) // 2  # 中间位置
        insert_idx = max(1, insert_idx)  # 至少在第二个语句之后

        # 推断返回值类型
        # 查找现有的 return 语句来推断类型
        return_value = ast.Constant(value=None)  # 默认返回 None

        for node in ast.walk(func):
            if isinstance(node, ast.Return) and node.value:
                # 根据已有的返回语句推断类型
                if isinstance(node.value, ast.Constant):
                    val = node.value.value
                    if isinstance(val, bool):
                        return_value = ast.Constant(value=False)
                    elif isinstance(val, int):
                        return_value = ast.Constant(value=0)
                    elif isinstance(val, str):
                        return_value = ast.Constant(value="")
                    break
                elif isinstance(node.value, ast.List):
                    return_value = ast.List(elts=[], ctx=ast.Load())
                    break
                elif isinstance(node.value, ast.Dict):
                    return_value = ast.Dict(keys=[], values=[])
                    break
                elif isinstance(node.value, ast.Tuple):
                    return_value = ast.Tuple(elts=[], ctx=ast.Load())
                    break

        # 创建早返回语句
        early_return = ast.Return(value=return_value)

        # 在选定位置插入 anchor 调用和早返回
        func.body.insert(insert_idx, anchor_call)
        func.body.insert(insert_idx + 1, early_return)

        return True, func.body[insert_idx].lineno if hasattr(func.body[insert_idx], 'lineno') else func.lineno

    def _inject_anchor_only(
        self, func: ast.FunctionDef, _anchor_def: ast.FunctionDef, anchor_call: ast.Expr
    ) -> Tuple[bool, int]:
        """
        无害注入：只插入 anchor，不改动任何逻辑。
        Anchor 定义仍由 inject_bug_and_anchor 统一插入。
        """
        self._insert_node_after_docstring(func, anchor_call)
        lineno = getattr(anchor_call, "lineno", getattr(func, "lineno", 0))
        return True, lineno


class CodeValidator:
    """
    验证器：带超时保护的代码执行器。

    - 先确认 original_code 能通过所有测试（否则直接认为数据有问题）；
    - 再跑 corrupted_code，记录其错误类型：
        * ok      : 所有断言通过
        * assert  : 断言失败（理想的“逻辑错误”样本）
        * runtime : 其他异常（IndexError / ValueError 等）
        * timeout : 执行超时
    """

    def validate_injection(self, corrupted_code: str, test_cases: List[str], original_code: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "valid": False,
            "syntax_ok": False,
            "all_passed": False,
            "error_msg": None,
            "original_error_type": None,
            "corrupted_error_type": None,
        }

        # 先检查语法
        try:
            compile(corrupted_code, "<string>", "exec")
            result["syntax_ok"] = True
        except SyntaxError as e:
            result["error_msg"] = str(e)
            return result

        # 确保原始代码是"通过所有测试"的正确实现
        orig = self._run_safely(original_code, test_cases)
        result["original_error_type"] = orig["error_type"]
        if not orig["passed"]:
            result["error_msg"] = f"Original code failed tests: {orig['error_type']} {orig['error_msg']}"
            return result

        # 运行注入后的代码
        corr = self._run_safely(corrupted_code, test_cases)
        result["corrupted_error_type"] = corr["error_type"]
        result["all_passed"] = corr["passed"]
        result["error_msg"] = corr["error_msg"]

        # 原版严格验证：必须所有测试都失败，且错误类型是 assert
        if not corr["passed"] and corr["error_type"] == "assert":
            result["valid"] = True

        return result

    def _run_safely(self, code: str, tests: List[str]) -> Dict[str, Any]:
        """
        在受限环境中执行 code + tests，返回：
        {
            "passed": bool,
            "error_type": "ok" | "assert" | "runtime" | "timeout",
            "error_msg": str
        }
        """
        full_script = code + "\n\n" + "\n".join(tests)

        # 跨平台超时处理
        if sys.platform != "win32":

            @contextmanager
            def time_limit(seconds: int):
                def signal_handler(signum, frame):
                    raise TimeoutError("Timed out!")

                old_handler = signal.signal(signal.SIGALRM, signal_handler)
                signal.alarm(seconds)
                try:
                    yield
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)

        else:

            @contextmanager
            def time_limit(seconds: int):
                # Windows 下不做真实超时，作为简单透传
                yield

        try:
            with time_limit(2):
                exec_globals: Dict[str, Any] = {"__name__": "__main__"}
                exec(full_script, exec_globals)
            return {"passed": True, "error_type": "ok", "error_msg": ""}
        except TimeoutError as e:
            return {"passed": False, "error_type": "timeout", "error_msg": str(e)}
        except AssertionError as e:
            return {"passed": False, "error_type": "assert", "error_msg": repr(e)}
        except Exception as e:
            return {"passed": False, "error_type": "runtime", "error_msg": repr(e)}


__all__ = ["ASTInjector", "CodeValidator"]
