from __future__ import annotations
import json, os, pathlib, sys
from .base_agent import BaseAgent

class RulePatchAgent(BaseAgent):
    """
    规则型补丁代理（用于无网络演示）：
    - 若 verbal/unit 提示中含 TypeError/类型关键词，尝试对 add() 加类型检查。
    TODO:
    - 加入更多可配置的“常见修复策略库”（边界检查/排序稳定性/除零/空值等）。
    """
    def run_one_turn(self) -> dict:
        data = self._read_turn_input()
        diff = """--- a/starter_files/solution.py
+++ b/starter_files/solution.py
@@ -1,3 +1,9 @@
 def add(a, b):
-    # BUGGY stub: passes compilation but fails tests (type checking absent)
-    return a + b
+    if not isinstance(a, int) or not isinstance(b, int):
+        raise TypeError("add only accepts integers")
+    return a + b
"""
        unit = data.get("feedback", {}).get("unit", [])
        evidence = [{"src": "unit", "id": unit[0]["id"]}] if unit else []
        out = {
            "diagnosis": "BOUNDARY_TYPE",
            "evidence_map": evidence,
            "picked_rationale_id": "R_rule",
            "plan": "为 add 添加类型检查。",
            "patch": {"format": "unified_diff", "diff": diff},
            "tests_to_rerun": [x["test"] for x in unit]
        }
        return out

if __name__ == "__main__":
    agent = RulePatchAgent()
    agent._write_stdout(agent.run_one_turn())