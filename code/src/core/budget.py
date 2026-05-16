"""Shared budget guard: wall-clock + USD cap.

Both `00_dry_run_calibration.py` (1-hour cap) and `02_run_evaluation.py`
($BUDGET cap) use this to abort cleanly when limits are hit.

Usage::

    from tracebench.budget import BudgetGuard
    guard = BudgetGuard(max_wall_clock_seconds=3600, max_usd=5.0)
    guard.start()
    ...
    for problem in problems:
        guard.add_cost(input_tokens=ti, output_tokens=to,
                       input_price_per_mt=2.0, output_price_per_mt=12.0)
        if guard.should_stop():
            print(f"BUDGET CUT: {guard.reason()}")
            break

The guard persists itself between runs via a JSON sidecar so a resumed
run picks up where it left off (important for long Gemini runs that may
crash mid-way).
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class BudgetGuard:
    max_wall_clock_seconds: Optional[float] = None
    max_usd: Optional[float] = None
    persist_path: Optional[Path] = None

    # Running totals
    started_at: float = 0.0
    spent_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    _stop_reason: Optional[str] = field(default=None)

    def start(self) -> None:
        # If persistent state exists, resume
        if self.persist_path and self.persist_path.exists():
            try:
                prior = json.loads(self.persist_path.read_text())
                self.spent_usd            = prior.get("spent_usd", 0.0)
                self.total_input_tokens   = prior.get("total_input_tokens", 0)
                self.total_output_tokens  = prior.get("total_output_tokens", 0)
                self.total_calls          = prior.get("total_calls", 0)
            except Exception:
                pass
        self.started_at = time.time()

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0

    def add_cost(self, input_tokens: int, output_tokens: int,
                 input_price_per_mt: float, output_price_per_mt: float) -> None:
        """Record one API call's contribution to the running total."""
        self.total_input_tokens  += int(input_tokens)
        self.total_output_tokens += int(output_tokens)
        self.total_calls         += 1
        cost = (input_tokens  * input_price_per_mt +
                output_tokens * output_price_per_mt) / 1e6
        self.spent_usd += cost
        self._persist()

    def add_call_no_cost(self) -> None:
        """For local-model calls; we still want call counts even though cost=0."""
        self.total_calls += 1
        self._persist()

    def should_stop(self) -> bool:
        if self.max_wall_clock_seconds and self.elapsed_seconds > self.max_wall_clock_seconds:
            self._stop_reason = (f"wall-clock {self.elapsed_seconds:.0f}s > "
                                 f"cap {self.max_wall_clock_seconds:.0f}s")
            return True
        if self.max_usd is not None and self.spent_usd > self.max_usd:
            self._stop_reason = (f"API spend ${self.spent_usd:.2f} > "
                                 f"cap ${self.max_usd:.2f}")
            return True
        return False

    def reason(self) -> str:
        return self._stop_reason or "no stop reason"

    def summary(self) -> dict:
        return {
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "spent_usd": round(self.spent_usd, 4),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_calls": self.total_calls,
            "max_wall_clock_seconds": self.max_wall_clock_seconds,
            "max_usd": self.max_usd,
            "stop_reason": self._stop_reason,
        }

    def _persist(self) -> None:
        if not self.persist_path:
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self.persist_path.write_text(json.dumps(self.summary(), indent=2))
        except Exception:
            pass

    def __str__(self) -> str:
        parts = [
            f"elapsed={self.elapsed_seconds:.0f}s",
            f"calls={self.total_calls}",
            f"spent=${self.spent_usd:.3f}",
        ]
        if self.max_wall_clock_seconds:
            parts.append(f"clock_cap={self.max_wall_clock_seconds:.0f}s")
        if self.max_usd:
            parts.append(f"usd_cap=${self.max_usd:.2f}")
        return "[BudgetGuard " + " ".join(parts) + "]"
