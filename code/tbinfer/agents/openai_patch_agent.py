from __future__ import annotations
import os, json, sys
from pathlib import Path
from typing import Dict, Any
from tbgen.providers.openai_client import OpenAIClient, OpenAIConfig

class OpenAIPatchAgent:
    def __init__(self):
        self.client = OpenAIClient(OpenAIConfig(
            model=os.getenv("AGENT_MODEL", "gpt-4o"),
            temperature=0.2,
            max_tokens=4000,
            mock=bool(os.environ.get("TBGEN_MOCK"))
        ))

    def run_one_turn(self) -> Dict[str, Any]:
        turn_input_path = os.getenv("TRACEBENCH_TURN_INPUT")
        if not turn_input_path or not Path(turn_input_path).exists():
            return self._empty_output()

        with open(turn_input_path, 'r') as f:
            turn_input = json.load(f)

        feedback = turn_input.get("feedback", {})

        if os.environ.get("TBGEN_MOCK"):
            return self._mock_output()

        patch_diff = self._generate_patch(feedback)

        return {
            "diagnosis": self._diagnose(feedback),
            "evidence_map": self._extract_evidence(feedback),
            "picked_rationale_id": "R_llm_fix",
            "plan": "Generated patch to fix failing tests",
            "patch": {
                "format": "unified_diff",
                "diff": patch_diff
            },
            "tests_to_rerun": []
        }

    def _diagnose(self, feedback: Dict) -> str:
        unit = feedback.get("unit", {})
        if not unit:
            return "NO_FEEDBACK"

        content = unit.get("content", {})
        failed = content.get("failed", 0)

        if failed > 0:
            return "TEST_FAILURE"
        elif content.get("coverage", 1.0) < 0.85:
            return "LOW_COVERAGE"
        return "OTHER"

    def _extract_evidence(self, feedback: Dict) -> list:
        evidence = []
        for fb_type in ["compile", "unit", "verbal"]:
            if fb_type in feedback and feedback[fb_type]:
                evidence.append({
                    "feedback_id": feedback[fb_type].get("feedback_id"),
                    "relevance": 0.9
                })
        return evidence

    def _generate_patch(self, feedback: Dict) -> str:
        unit = feedback.get("unit", {})
        if not unit:
            return ""

        content = unit.get("content", {})
        failed_cases = content.get("failed_cases", [])

        if not failed_cases:
            return ""

        system = """You are an expert code debugger. Given test failures, generate a minimal unified diff patch to fix them.
Output ONLY the patch in unified diff format, nothing else."""

        user_prompt = f"""Test failures:
{json.dumps(failed_cases, indent=2)}

Generate a minimal patch to fix these failures. Output format:
--- a/solution.py
+++ b/solution.py
@@ -X,Y +X,Z @@
 context
-removed line
+added line
 context
"""

        response = self.client.chat(system=system, user=user_prompt)
        return self._extract_diff(response)

    def _extract_diff(self, response: str) -> str:
        lines = response.split('\n')
        diff_lines = []
        in_diff = False

        for line in lines:
            if line.startswith('---') or line.startswith('+++'):
                in_diff = True
            if in_diff:
                diff_lines.append(line)

        return '\n'.join(diff_lines) if diff_lines else response

    def _mock_output(self) -> Dict[str, Any]:
        return {
            "diagnosis": "TEST_FAILURE",
            "evidence_map": [],
            "picked_rationale_id": "R_mock",
            "plan": "Mock patch",
            "patch": {
                "format": "unified_diff",
                "diff": "--- a/solution.py\n+++ b/solution.py\n@@ -1,3 +1,3 @@\n def parse(data):\n-    pass\n+    return data\n"
            },
            "tests_to_rerun": []
        }

    def _empty_output(self) -> Dict[str, Any]:
        return {
            "diagnosis": "OTHER",
            "evidence_map": [],
            "picked_rationale_id": "R_empty",
            "plan": "",
            "patch": {"format": "unified_diff", "diff": ""},
            "tests_to_rerun": []
        }

if __name__ == "__main__":
    agent = OpenAIPatchAgent()
    output = agent.run_one_turn()

    output_path = os.getenv("TRACEBENCH_TURN_OUTPUT")
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
    else:
        print(json.dumps(output, indent=2))
