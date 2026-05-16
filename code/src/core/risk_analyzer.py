from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """一个代码片段，用行号区间表示。"""
    file_path: str
    start_line: int
    end_line: int
    score: float = 1.0  # 归因置信度，越大越可疑


@dataclass
class RiskVector:
    """
    解码前用来指导策略的“风险向量”。

    必要字段：
    - suspicious_spans: Top-K 高风险代码片段
    - global_risk: [0,1]，越大表示“现在非常危险，应该谨慎动手”
    """
    suspicious_spans: List[Span]
    global_risk: float
    failure_streak: int = 0
    depth: Optional[int] = None   # 当前子问题的深度（可选）


class RiskAnalyzer:
    """
    根据当前的 problem state（代码、最近一次失败信息、anchor hit、失败串长度等）
    生成 RiskVector。

    ⚠️ 强依赖于你 evaluation loop 填的 state 字段，下面注释里会写清楚预期字段。
    """

    def __init__(self, window_lines: int = 5, max_spans: int = 3):
        # 怀疑行的上下扩一个小窗口，变成 span
        self.window_lines = window_lines
        self.max_spans = max_spans

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_risk_vector(self, state: Dict[str, Any]) -> RiskVector:
        """
        输入：
            state: {
              "file_path": 当前主代码文件路径 (str),
              "last_test_output": 最近一轮测试输出/trace (str),
              "anchor_hits": [int 行号 ...] 或 []，可选
              "failure_streak": 连续失败次数 (int),
              "depth": 当前子问题深度 (int, optional)
            }
        输出：
            RiskVector
        """
        file_path = state.get("file_path", "main.py")
        test_output = state.get("last_test_output") or ""
        anchor_hits: List[int] = state.get("anchor_hits") or []
        failure_streak: int = int(state.get("failure_streak", 0))
        depth: Optional[int] = state.get("depth")

        # 1) 从 traceback 里抽取最近的报错行号
        failing_lines = self._extract_error_lines_from_trace(test_output, file_path)

        # 2) 把 failing_lines + anchor_hits 合并成若干 suspicious spans
        spans = self._build_suspicious_spans(
            file_path=file_path,
            failing_lines=failing_lines,
            anchor_hits=anchor_hits,
        )

        # 3) 计算一个简单的 global_risk
        global_risk = self._compute_global_risk(
            failure_streak=failure_streak,
            num_suspicious=len(spans),
            depth=depth,
        )

        return RiskVector(
            suspicious_spans=spans,
            global_risk=global_risk,
            failure_streak=failure_streak,
            depth=depth,
        )

    # ------------------------------------------------------------------
    # Heuristics
    # ------------------------------------------------------------------

    def _extract_error_lines_from_trace(self, trace: str, file_path: str) -> List[int]:
        """
        从 Python traceback 里抓出当前文件相关的行号。

        典型格式：
            File "problem_1926F.py", line 42, in is_valid
        """
        if not trace:
            return []

        pattern = r'File "([^"]+)", line (\d+)'
        lines: List[int] = []
        for match in re.finditer(pattern, trace):
            fname, line_str = match.groups()
            if fname.endswith(file_path) or file_path.endswith(fname):
                try:
                    lines.append(int(line_str))
                except ValueError:
                    continue
        # 最近的 frame 通常是最接近 bug 的
        return lines[-self.max_spans :] if lines else []

    def _build_suspicious_spans(
        self,
        file_path: str,
        failing_lines: List[int],
        anchor_hits: List[int],
    ) -> List[Span]:
        """
        把 failing_lines 和 anchor_hits 各自扩成一个小窗口，合并成 span 列表。
        failing_lines 的 score 略高于 anchor。
        """
        spans: List[Span] = []

        def add_span(center: int, base_score: float):
            start = max(1, center - self.window_lines)
            end = max(start, center + self.window_lines)
            spans.append(Span(file_path=file_path, start_line=start, end_line=end, score=base_score))

        for ln in failing_lines:
            add_span(ln, base_score=1.0)

        for ln in anchor_hits:
            add_span(ln, base_score=0.7)

        # 简单按照 score 排序 + 去重（overlap 合并这里先不做，留给后处理）
        spans.sort(key=lambda s: s.score, reverse=True)

        # 去除重复/高度重叠的 span（粗略版）
        deduped: List[Span] = []
        for s in spans:
            if len(deduped) >= self.max_spans:
                break
            if not any(self._overlap_ratio(s, t) > 0.7 for t in deduped):
                deduped.append(s)

        return deduped

    def _compute_global_risk(
        self,
        failure_streak: int,
        num_suspicious: int,
        depth: Optional[int],
    ) -> float:
        """
        一个非常粗糙但好用的 risk 定义：
        - 失败串越长，风险越大；
        - 已经激活了多个 suspicious spans，说明问题复杂；
        - 深度越大（离入口远），倾向于给更高风险。
        """
        base = min(1.0, failure_streak / 3.0)          # 连续失败 3 次视为高风险
        span_factor = min(1.0, num_suspicious / 3.0)   # span 越多越复杂
        depth_factor = 0.0
        if depth is not None and depth >= 2:
            depth_factor = min(1.0, (depth - 1) / 3.0)  # 深度 >=2 逐步加权

        # 简单加权平均
        global_risk = 0.6 * base + 0.3 * span_factor + 0.1 * depth_factor
        return max(0.0, min(1.0, global_risk))

    @staticmethod
    def _overlap_ratio(a: Span, b: Span) -> float:
        if a.file_path != b.file_path:
            return 0.0
        inter_start = max(a.start_line, b.start_line)
        inter_end = min(a.end_line, b.end_line)
        if inter_end < inter_start:
            return 0.0
        inter = inter_end - inter_start + 1
        union = (a.end_line - a.start_line + 1) + (b.end_line - b.start_line + 1) - inter
        return inter / union if union > 0 else 0.0