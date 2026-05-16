from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass
from tbgen.providers.openai_client import OpenAIClient, OpenAIConfig

@dataclass
class ExtensionConfig:
    """Configuration for extending CodeFlowBench tasks."""
    target_turns: int = 8
    add_noisy_rationales: int = 3
    add_rollback_points: int = 2
    add_shift_tags: bool = True
    add_fuzz_triggers: bool = True
    model: str = "gpt-4o"
    provider: str = "openai"
    api_key: str = None

class TraceBenchBuilder:
    """
    Builds extended TraceBench tasks from CodeFlowBench.
    """
    def __init__(self, config: ExtensionConfig):
        self.config = config
        self.client = OpenAIClient(OpenAIConfig(
            model=config.model,
            temperature=0.7,
            max_tokens=6000,
            provider=config.provider,
            api_key=config.api_key
        ))

    def extend_task(self, codeflow_task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extend a CodeFlowBench task to a longer TraceBench task.
        """
        base_spec = codeflow_task.get("spec_md", "")
        starter_code = codeflow_task.get("starter_code", "")
        difficulty = codeflow_task.get("difficulty", "medium")

        print(f"Extending task: {codeflow_task.get('id', 'unknown')}")

        extended_rationales = self._generate_extended_rationales(
            base_spec, starter_code, codeflow_task.get("rationales", {})
        )

        extended_scenario = self._generate_extended_scenario(
            base_spec, starter_code, extended_rationales
        )

        shift_tags = self._generate_shift_tags(
            codeflow_task, extended_scenario
        )

        fuzz_config = self._generate_fuzz_config(
            base_spec, difficulty
        )

        return {
            "task_id": f"tracebench:{codeflow_task.get('id', 'unknown')}",
            "track": codeflow_task.get("track", "function"),
            "difficulty": difficulty,
            "title": codeflow_task.get("id", "").replace("_", " ").title(),
            "spec_md": base_spec,
            "starter_files": {
                "solution.py": starter_code
            },
            "tests": codeflow_task.get("tests", {}),
            "rationales": extended_rationales,
            "scenarios": {
                "extended_multi_rollback": extended_scenario
            },
            "shift_tags": shift_tags,
            "fuzz_config": fuzz_config,
            "source": "CodeFlowBench+GPT-extended",
            "oracle_turns": codeflow_task.get("tests", {}).get("oracle_turns", 1)
        }

    def _generate_extended_rationales(
        self,
        spec: str,
        starter_code: str,
        base_rationales: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate extended rationales using GPT.
        """
        system = """You are an expert in software debugging pedagogy. Given a coding task and existing rationales, generate additional noisy/misleading rationales that would lead to longer debugging sessions.

Output JSON format:
{
  "clean": {"rid": "R1", "content": "..."},
  "noisy": [
    {"rid": "R2", "noise_type": "partially_correct", "content": "..."},
    {"rid": "R3", "noise_type": "off_task", "content": "..."},
    {"rid": "R4", "noise_type": "incorrect_api", "content": "..."}
  ]
}"""

        user = f"""Task specification:
{spec}

Starter code:
```python
{starter_code}
```

Existing rationales:
{json.dumps(base_rationales, indent=2)}

Generate {self.config.add_noisy_rationales} additional noisy rationales that:
1. Sound plausible but lead to wrong solutions
2. Mix correct and incorrect advice
3. Suggest irrelevant optimizations
4. Use wrong APIs or patterns

Keep the clean rationale but enhance noisy ones."""

        response = self.client.chat(system=system, user=user)

        try:
            extended = json.loads(response)
            if not extended.get("clean"):
                extended["clean"] = base_rationales.get("clean", {
                    "rid": "R1",
                    "content": "Follow the specification exactly"
                })
            return extended
        except:
            return base_rationales

    def _generate_extended_scenario(
        self,
        spec: str,
        starter_code: str,
        rationales: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate a long multi-turn scenario with rollbacks.
        """
        system = f"""You are designing a debugging scenario with {self.config.target_turns} turns and {self.config.add_rollback_points} rollbacks.

Output JSON format:
{{
  "turns": [
    {{
      "turn": 1,
      "picked_rationale_id": "R2",
      "expected_outcome": "partial_progress",
      "tests_passed": 2,
      "tests_total": 6,
      "description": "..."
    }},
    {{
      "turn": 2,
      "picked_rationale_id": "R3",
      "expected_outcome": "regression",
      "tests_passed": 1,
      "tests_total": 6,
      "description": "..."
    }},
    {{
      "turn": 3,
      "rollback": true,
      "rollback_to_turn": 1,
      "reason": "...",
      "expected_outcome": "recovery"
    }},
    ...
  ],
  "expected_final_success": true,
  "expected_rollback_count": {self.config.add_rollback_points},
  "narrative": "Overall scenario description"
}}

Rules:
1. Include failure streaks before rollbacks
2. Show recovery after rollback
3. Eventually reach success with clean rationale
4. Make it realistic debugging flow"""

        rationale_list = [rationales.get("clean", {})] + rationales.get("noisy", [])
        rationale_ids = [r.get("rid", f"R{i+1}") for i, r in enumerate(rationale_list)]

        user = f"""Task: {spec}

Starter code:
```python
{starter_code}
```

Available rationales: {', '.join(rationale_ids)}

Design a {self.config.target_turns}-turn scenario with:
- At least {self.config.add_rollback_points} rollback points
- Realistic failure patterns
- Progressive difficulty
- Final success"""

        response = self.client.chat(system=system, user=user)

        try:
            return json.loads(response)
        except:
            return self._fallback_scenario()

    def _generate_shift_tags(
        self,
        codeflow_task: Dict[str, Any],
        scenario: Dict[str, Any]
    ) -> List[str]:
        """
        Generate comprehensive shift_tags.
        """
        tags = []

        difficulty = codeflow_task.get("difficulty", "medium")
        tags.append(f"difficulty:{difficulty}")

        track = codeflow_task.get("track", "function")
        tags.append(f"track:{track}")

        expected_turns = len(scenario.get("turns", []))
        if expected_turns <= 3:
            tags.append("structure:turns=short")
        elif expected_turns <= 6:
            tags.append("structure:turns=medium")
        else:
            tags.append("structure:turns=long")

        rollback_count = scenario.get("expected_rollback_count", 0)
        if rollback_count > 0:
            tags.append(f"strategy:rollback_count={rollback_count}")

        spec = codeflow_task.get("spec_md", "").lower()

        if any(kw in spec for kw in ["error", "exception", "raise", "try"]):
            tags.append("boundary:error_handling")

        if any(kw in spec for kw in ["edge case", "boundary", "corner"]):
            tags.append("boundary:high")

        if any(kw in spec for kw in ["parse", "validate", "transform"]):
            tags.append("domain:data_processing")

        if any(kw in spec for kw in ["sort", "search", "filter"]):
            tags.append("domain:algorithms")

        tags.append("temporal:2025")

        return tags

    def _generate_fuzz_config(
        self,
        spec: str,
        difficulty: str
    ) -> Dict[str, Any]:
        """
        Generate fuzzing/property-based testing config.
        """
        return {
            "enabled": self.config.add_fuzz_triggers,
            "trigger_conditions": {
                "all_tests_pass": True,
                "coverage_below": 0.85
            },
            "tools": ["hypothesis", "atheris"],
            "hypothesis": {
                "strategies": self._infer_hypothesis_strategies(spec),
                "max_examples": 100
            },
            "atheris": {
                "enabled": "C extension" in spec or "performance" in spec.lower(),
                "timeout_seconds": 60
            },
            "crosshair": {
                "enabled": difficulty in ["medium", "hard"],
                "timeout_seconds": 30
            }
        }

    def _infer_hypothesis_strategies(self, spec: str) -> List[str]:
        """Infer appropriate Hypothesis strategies from spec."""
        strategies = []
        spec_lower = spec.lower()

        if "int" in spec_lower or "number" in spec_lower:
            strategies.append("integers()")
        if "string" in spec_lower or "text" in spec_lower:
            strategies.append("text()")
        if "list" in spec_lower or "array" in spec_lower:
            strategies.append("lists(integers())")
        if "dict" in spec_lower or "map" in spec_lower:
            strategies.append("dictionaries(text(), integers())")

        return strategies or ["integers()", "text()"]

    def _fallback_scenario(self) -> Dict[str, Any]:
        """Fallback scenario if GPT generation fails."""
        return {
            "turns": [
                {
                    "turn": 1,
                    "picked_rationale_id": "R2",
                    "expected_outcome": "partial_progress",
                    "tests_passed": 2,
                    "tests_total": 5
                },
                {
                    "turn": 2,
                    "picked_rationale_id": "R3",
                    "expected_outcome": "regression",
                    "tests_passed": 1,
                    "tests_total": 5
                },
                {
                    "turn": 3,
                    "rollback": True,
                    "rollback_to_turn": 1
                },
                {
                    "turn": 4,
                    "picked_rationale_id": "R1",
                    "expected_outcome": "success",
                    "tests_passed": 5,
                    "tests_total": 5
                }
            ],
            "expected_final_success": True,
            "expected_rollback_count": 1
        }

def build_tracebench_from_codeflow(
    codeflow_dataset_path: str,
    output_dir: str,
    config: ExtensionConfig,
    limit: int = None
) -> int:
    """
    Main pipeline: CodeFlowBench → TraceBench.
    """
    builder = TraceBenchBuilder(config)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    codeflow_data = load_codeflow_dataset(codeflow_dataset_path)

    tasks_created = 0
    for i, codeflow_task in enumerate(codeflow_data):
        if limit and i >= limit:
            break

        try:
            extended_task = builder.extend_task(codeflow_task)

            task_dir = output_path / extended_task["task_id"].replace(":", "__")
            task_dir.mkdir(parents=True, exist_ok=True)

            task_file = task_dir / "task.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(extended_task, f, indent=2, ensure_ascii=False)

            for fname, content in extended_task.get("starter_files", {}).items():
                (task_dir / fname).write_text(content, encoding='utf-8')

            tasks_created += 1
            print(f"✓ Created: {extended_task['task_id']}")

        except Exception as e:
            print(f"✗ Failed to extend task {i}: {e}")
            continue

    print(f"\n=== Built {tasks_created} TraceBench tasks ===")
    return tasks_created

def load_codeflow_dataset(path: str) -> List[Dict[str, Any]]:
    """
    Load CodeFlowBench dataset from HuggingFace or local file.
    """
    try:
        from datasets import load_dataset
        dataset = load_dataset("WaterWang-001/CodeFlowBench-2505")
        return list(dataset["train"]) if "train" in dataset else list(dataset)
    except:
        path_obj = Path(path)
        if path_obj.exists():
            with open(path_obj, 'r', encoding='utf-8') as f:
                return json.load(f)

        return generate_mock_codeflow_samples()

def generate_mock_codeflow_samples() -> List[Dict[str, Any]]:
    """Generate mock CodeFlowBench samples for testing."""
    return [
        {
            "id": "simple:chunk_list",
            "difficulty": "simple",
            "track": "function",
            "spec_md": "Implement chunk(arr, k) that splits array into chunks of size k. Raise ValueError if k<=0. Preserve order.",
            "starter_code": """def chunk(arr, k):
    if k == 0:
        return [arr]
    arr.sort()
    out = []
    i = 0
    while i < len(arr):
        out.append(arr[i:i+k])
        i += k
    return out
""",
            "tests": {
                "unit": ["test_chunk_basic", "test_preserve_order", "test_invalid_k"],
                "oracle_turns": 1
            },
            "rationales": {
                "clean": {
                    "rid": "R1",
                    "content": "If k<=0 raise ValueError. Do not sort. Use slicing."
                },
                "noisy": [
                    {
                        "rid": "R2",
                        "noise_type": "partially_correct",
                        "content": "If k<0 use |k|, if 0 use 1."
                    }
                ]
            }
        }
    ]
