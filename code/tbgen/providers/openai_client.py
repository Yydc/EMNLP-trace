from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import os, json, time, random

@dataclass
class OpenAIConfig:
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 4000
    mock: bool = False
    api_key: Optional[str] = None
    provider: str = "openai"  # "openai" or "together"

@dataclass
class CostTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_calls: int = 0

    def add_usage(self, prompt: int, completion: int):
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_calls += 1

    def estimate_cost(self, model: str) -> float:
        pricing = {
            "gpt-4o": {"prompt": 2.5, "completion": 10.0},
            "gpt-4o-mini": {"prompt": 0.15, "completion": 0.6},
            "gpt-4-turbo": {"prompt": 10.0, "completion": 30.0}
        }
        rates = pricing.get(model, pricing["gpt-4o"])
        cost = (self.prompt_tokens * rates["prompt"] +
                self.completion_tokens * rates["completion"]) / 1_000_000
        return cost

class OpenAIClient:
    def __init__(self, cfg: OpenAIConfig):
        self.cfg = cfg
        self.cost_tracker = CostTracker()

        if not self.cfg.mock and not os.environ.get("TBGEN_MOCK"):
            if self.cfg.provider == "together":
                try:
                    from together import Together
                    self.client = Together(api_key=cfg.api_key or os.getenv("TOGETHER_API_KEY"))
                except ImportError:
                    raise ImportError("together package not installed. Run: pip install together")
            else:
                try:
                    import openai
                    self.client = openai.OpenAI(api_key=cfg.api_key or os.getenv("OPENAI_API_KEY"))
                except ImportError:
                    raise ImportError("openai package not installed. Run: pip install openai")

    def chat(self, system: str, user: str, response_format: Optional[Dict] = None) -> str:
        if self.cfg.mock or os.environ.get("TBGEN_MOCK"):
            return self._mock_response()

        for attempt in range(3):
            try:
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]

                kwargs = {
                    "model": self.cfg.model,
                    "messages": messages,
                    "temperature": self.cfg.temperature,
                    "max_tokens": self.cfg.max_tokens
                }

                if response_format:
                    kwargs["response_format"] = response_format

                response = self.client.chat.completions.create(**kwargs)

                if response.usage:
                    self.cost_tracker.add_usage(
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens
                    )

                return response.choices[0].message.content

            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("OpenAI API call failed after retries")

    def _mock_response(self) -> str:
        template = {
            "task_id": f"func:mock_{int(time.time())}_{random.randint(1000,9999)}",
            "track": "function",
            "title": "Implement safe addition",
            "spec_md": "Implement add(a,b) that only accepts int, raises TypeError otherwise.",
            "starter_files": None,
            "tests": {"unit": {"paths": ["tests/test_basic.py"]}},
            "env": {"python": "3.11", "deps": ["pytest==8.*", "coverage"]},
            "feedback_profiles": ["compile+unit_highcov+expert_noise:light"],
            "shift_tags": ["structure:depth=1", "structure:turns=2", "boundary:high"],
            "source": "tbgen:mock"
        }
        return json.dumps(template, ensure_ascii=False)