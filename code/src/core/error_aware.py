from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .risk_analyzer import Span, RiskVector


@dataclass
class ControlPlan:
    """
    控制本轮解码的“计划”：给调用 LLM 的外层逻辑用。
    """
    # 允许修改的代码区域（硬约束）
    allowed_edit_regions: List[Span]

    # 解码超参数（可以直接塞给你现有的 generate 调用）
    temperature: float
    top_k: int
    num_candidates: int

    # prompt / 策略开关
    structured_prompt: bool = True   # 是否用“先分析再patch”的结构化提示
    enable_rollback: bool = True     # 是否允许本轮引入微回滚策略


class ErrorAwareController:
    """
    把 RiskVector 映射到 ControlPlan：
    - high risk → 低温、多候选、强编辑约束
    - low risk  → 正常温度、少候选、稍松编辑约束
    """

    def __init__(
        self,
        window_lines: int = 5,
        t_min: float = 0.1,
        t_max: float = 0.5,
        k_min: int = 8,
        k_max: int = 64,
        base_candidates: int = 2,
        max_candidates: int = 5,
    ) -> None:
        self.window_lines = window_lines
        self.t_min = t_min
        self.t_max = t_max
        self.k_min = k_min
        self.k_max = k_max
        self.base_candidates = base_candidates
        self.max_candidates = max_candidates

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def make_control_plan(self, risk: RiskVector) -> ControlPlan:
        """
        核心策略：
        1. 使用 suspicious_spans 构造 allowed_edit_regions（再扩一点窗口）
        2. 用 global_risk 线性插值 temperature / top_k / num_candidates
        """
        allowed_regions = self._expand_regions(risk.suspicious_spans)

        temperature = self._interp(
            high_is_safe=False,  # 风险越高，温度越低
            risk=risk.global_risk,
            lo=self.t_min,
            hi=self.t_max,
        )
        top_k = int(
            self._interp(
                high_is_safe=True,   # 风险越高，多给点候选
                risk=risk.global_risk,
                lo=self.k_min,
                hi=self.k_max,
            )
        )
        num_candidates = int(
            self._interp(
                high_is_safe=True,
                risk=risk.global_risk,
                lo=self.base_candidates,
                hi=self.max_candidates,
            )
        )

        # 风险很低时可以关闭 rollback / structured prompt（当baseline）
        structured = True
        enable_rollback = True
        if risk.global_risk < 0.2 and risk.failure_streak == 0:
            structured = False
            enable_rollback = False

        return ControlPlan(
            allowed_edit_regions=allowed_regions,
            temperature=temperature,
            top_k=top_k,
            num_candidates=num_candidates,
            structured_prompt=structured,
            enable_rollback=enable_rollback,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _expand_regions(self, spans: List[Span]) -> List[Span]:
        """
        在 RiskAnalyzer 给出的 suspicious spans 基础上再稍微扩一圈，
        确保 patch 不会太“卡边界”。
        """
        expanded: List[Span] = []
        for s in spans:
            start = max(1, s.start_line - self.window_lines)
            end = max(start, s.end_line + self.window_lines)
            expanded.append(Span(file_path=s.file_path, start_line=start, end_line=end, score=s.score))
        return expanded

    @staticmethod
    def _interp(high_is_safe: bool, risk: float, lo: float, hi: float) -> float:
        """
        简单线性插值：
        - high_is_safe=True：风险越高 → 参数越接近 hi
        - high_is_safe=False：风险越高 → 参数越接近 lo
        """
        r = max(0.0, min(1.0, risk))
        if high_is_safe:
            return lo + (hi - lo) * r
        else:
            return hi - (hi - lo) * r