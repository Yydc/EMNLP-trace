from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pathlib, json, os, time

from tbgen.providers.openai_client import OpenAIClient, OpenAIConfig
from tbgen.tools.spec_utils import ensure_task_shape, write_task
from tbgen.tools.test_builder import materialize_layered_tests

@dataclass
class FlowGenConfig:
    model: str = "gpt-4o"
    temperature: float = 0.2

class FlowGenerator:
    def __init__(self, cfg: FlowGenConfig):
        self.cfg = cfg
        self.client = OpenAIClient(OpenAIConfig(
            model=cfg.model,
            temperature=cfg.temperature,
            mock=bool(os.environ.get("TBGEN_MOCK"))
        ))

    def generate_one(self, out_dir: pathlib.Path) -> pathlib.Path:
        if os.environ.get("TBGEN_MOCK"):
            task = self._generate_mock_task()
        else:
            task = self._generate_llm_task()

        tdir = out_dir / task["task_id"].replace(":", "__")
        write_task(tdir, task)
        materialize_layered_tests(tdir, task)
        return tdir

    def _generate_mock_task(self) -> Dict[str, Any]:
        return {
            "task_id": f"flow:mock_{int(time.time())}",
            "track": "function_flow",
            "title": "Data Processing Pipeline",
            "spec_md": "Implement a 3-layer data processing pipeline: parse -> validate -> transform",
            "starter_files": {
                "solution.py": "def parse(data): pass\ndef validate(data): pass\ndef transform(data): pass"
            },
            "dependency_topology": {
                "dependencies": {
                    "validate": ["parse"],
                    "transform": ["validate"]
                },
                "layers": [
                    {"level": 1, "functions": ["parse"]},
                    {"level": 2, "functions": ["validate"]},
                    {"level": 3, "functions": ["transform"]}
                ]
            },
            "tests": {"unit": {"paths": ["tests/test_1_parse.py", "tests/test_2_validate.py", "tests/test_3_transform.py"]}},
            "shift_tags": ["structure:depth=3", "structure:turns=3"],
            "source": "tbgen:mock:flow"
        }

    def _generate_llm_task(self) -> Dict[str, Any]:
        system = """You are a code challenge designer. Generate a TraceBench function_flow task with:
- 3-4 functions with clear dependencies
- Each function builds on previous ones
- Output must be valid JSON matching this schema:
{
  "task_id": "flow:...",
  "track": "function_flow",
  "title": "...",
  "spec_md": "...",
  "starter_files": {"solution.py": "..."},
  "dependency_topology": {
    "dependencies": {"func2": ["func1"], "func3": ["func2"]},
    "layers": [{"level": 1, "functions": ["func1"]}, ...]
  },
  "tests": {"unit": {"paths": ["tests/test_1_func1.py", ...]}},
  "shift_tags": ["structure:depth=N", "structure:turns=N"]
}"""

        user = "Generate a data processing or algorithm pipeline task with 3 layers of dependencies."

        response = self.client.chat(system=system, user=user)
        task = json.loads(response)
        return ensure_task_shape(task)

    def generate_n(self, out_dir: str, n: int = 1):
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        return [self.generate_one(out) for _ in range(n)]
