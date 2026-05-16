from __future__ import annotations
import os, json, sys
from pathlib import Path
from typing import Dict, Any, List
from tbgen.providers.openai_client import OpenAIClient, OpenAIConfig

class RationaleAgent:
    """
    Agent that can select from multiple rationales (clean + noisy).
    Supports CodeFlowBench-style reasoning.
    """
    def __init__(self):
        self.client = OpenAIClient(OpenAIConfig(
            model=os.getenv("AGENT_MODEL", "gpt-4o"),
            temperature=0.3,
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
        rationales = turn_input.get("rationales", {})

        if os.environ.get("TBGEN_MOCK"):
            return self._mock_output_with_rationale(feedback, rationales)

        picked_rationale, patch_diff = self._generate_patch_with_rationale(
            feedback, rationales
        )

        return {
            "diagnosis": self._diagnose(feedback),
            "evidence_map": self._extract_evidence(feedback),
            "picked_rationale_id": picked_rationale,
            "plan": "Generated patch based on selected rationale",
            "patch": {
                "format": "unified_diff",
                "diff": patch_diff
            },
            "tests_to_rerun": self._identify_tests_to_rerun(feedback)
        }

    def _diagnose(self, feedback: Dict) -> str:
        """Diagnose the issue type."""
        compile_fb = feedback.get("compile", {})
        unit_fb = feedback.get("unit", {})

        if compile_fb:
            content = compile_fb.get("content", {})
            if content.get("status") != "success":
                return "COMPILE_ERROR"

        if unit_fb:
            content = unit_fb.get("content", {})
            failed = content.get("failed", 0)
            coverage = content.get("coverage", 1.0)

            if failed > 0:
                return "TEST_FAILURE"
            elif coverage < 0.85:
                return "LOW_COVERAGE"

        return "OTHER"

    def _extract_evidence(self, feedback: Dict) -> List[Dict]:
        """Extract evidence from feedback."""
        evidence = []

        unit_fb = feedback.get("unit", {})
        if unit_fb:
            content = unit_fb.get("content", {})
            failed_cases = content.get("failed_cases", [])

            for i, case in enumerate(failed_cases[:3]):
                evidence.append({
                    "src": "unit",
                    "id": case.get("test", f"test_{i}"),
                    "feedback_id": unit_fb.get("feedback_id"),
                    "relevance": 0.9
                })

        return evidence

    def _identify_tests_to_rerun(self, feedback: Dict) -> List[str]:
        """Identify which tests should be rerun."""
        unit_fb = feedback.get("unit", {})
        if not unit_fb:
            return []

        content = unit_fb.get("content", {})
        failed_cases = content.get("failed_cases", [])

        return [case.get("test", "") for case in failed_cases[:5]]

    def _select_rationale(
        self,
        feedback: Dict,
        rationales: Dict[str, Any]
    ) -> str:
        """
        Select the best rationale based on feedback.
        In mock mode, randomly pick. In real mode, use LLM.
        """
        if os.environ.get("TBGEN_MOCK"):
            clean = rationales.get("clean", {})
            return clean.get("rid", "R1")

        all_rationales = []
        clean = rationales.get("clean", {})
        if clean:
            all_rationales.append(clean)

        noisy = rationales.get("noisy", [])
        all_rationales.extend(noisy)

        if not all_rationales:
            return "R_unknown"

        system = """You are a debugging expert. Given test failures and multiple rationales, select the most relevant one.
Output only the rationale ID (e.g., "R1", "R2")."""

        rationale_text = "\n".join([
            f"{r.get('rid', '')}: {r.get('content', '')}"
            for r in all_rationales
        ])

        user = f"""Feedback:
{json.dumps(feedback, indent=2)}

Available rationales:
{rationale_text}

Which rationale is most relevant? Output only the ID."""

        response = self.client.chat(system=system, user=user)

        for r in all_rationales:
            rid = r.get("rid", "")
            if rid in response:
                return rid

        return all_rationales[0].get("rid", "R1")

    def _generate_patch_with_rationale(
        self,
        feedback: Dict,
        rationales: Dict[str, Any]
    ) -> tuple:
        """Generate patch based on selected rationale."""
        picked_rationale_id = self._select_rationale(feedback, rationales)

        rationale_content = ""
        all_rats = []
        if rationales.get("clean"):
            all_rats.append(rationales["clean"])
        all_rats.extend(rationales.get("noisy", []))

        for r in all_rats:
            if r.get("rid") == picked_rationale_id:
                rationale_content = r.get("content", "")
                break

        unit_fb = feedback.get("unit", {})
        failed_cases = unit_fb.get("content", {}).get("failed_cases", []) if unit_fb else []

        if not failed_cases:
            return picked_rationale_id, ""

        system = f"""You are an expert code debugger. Use this guidance: {rationale_content}

Generate a minimal unified diff patch to fix the test failures.
Output ONLY the patch in unified diff format."""

        user = f"""Test failures:
{json.dumps(failed_cases, indent=2)}

Generate patch following the guidance. Format:
--- a/solution.py
+++ b/solution.py
@@ -X,Y +X,Z @@
 context
-removed
+added
"""

        response = self.client.chat(system=system, user=user)
        patch = self._extract_diff(response)

        return picked_rationale_id, patch

    def _extract_diff(self, response: str) -> str:
        """Extract unified diff from response."""
        lines = response.split('\n')
        diff_lines = []
        in_diff = False

        for line in lines:
            if line.startswith('---') or line.startswith('+++'):
                in_diff = True
            if in_diff:
                diff_lines.append(line)

        return '\n'.join(diff_lines) if diff_lines else response

    def _mock_output_with_rationale(
        self,
        feedback: Dict,
        rationales: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mock output that picks clean rationale."""
        clean = rationales.get("clean", {})
        picked_rid = clean.get("rid", "R1")

        return {
            "diagnosis": "TEST_FAILURE",
            "evidence_map": self._extract_evidence(feedback),
            "picked_rationale_id": picked_rid,
            "plan": f"Using rationale {picked_rid}",
            "patch": {
                "format": "unified_diff",
                "diff": self._generate_mock_patch()
            },
            "tests_to_rerun": []
        }

    def _generate_mock_patch(self) -> str:
        """Generate a simple mock patch."""
        return """--- a/solution.py
+++ b/solution.py
@@ -1,3 +1,5 @@
 def chunk(arr, k):
-    if k == 0:
-        return [arr]
+    if k <= 0:
+        raise ValueError("k must be > 0")
+    out = []
"""

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
    agent = RationaleAgent()
    output = agent.run_one_turn()

    output_path = os.getenv("TRACEBENCH_TURN_OUTPUT")
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
    else:
        print(json.dumps(output, indent=2))
