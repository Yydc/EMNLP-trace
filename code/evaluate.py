#!/usr/bin/env python3
"""Run TraceBench evaluation on two datasets and compare results."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.tracebench_eval import run_tracebench_eval


def _import_runner(spec: str) -> Callable[..., Dict[str, Any]]:
    """
    Load run_debug_session callable from a spec like "module.sub:func" or "module.sub.func".
    """
    module_path: str
    func_name: str
    if ":" in spec:
        module_path, func_name = spec.split(":", 1)
    elif "." in spec:
        module_path, func_name = spec.rsplit(".", 1)
    else:
        raise ValueError("Runner spec must look like 'module.sub:run_debug_session'.")

    module = importlib.import_module(module_path)
    runner = getattr(module, func_name, None)
    if runner is None or not callable(runner):
        raise AttributeError(f"Callable {func_name} not found in module {module_path}.")
    return runner


def _diff_numeric(a: Any, b: Any) -> Any:
    """Return a - b when both are numeric, else None."""
    try:
        if a is None or b is None:
            return None
        return float(a) - float(b)
    except (TypeError, ValueError):
        return None


def _diff_mode(current: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    """Compute metric deltas for one mode (baseline / error_aware)."""
    pass_at_turn_cur = current.get("pass_at_turn", {}) or {}
    pass_at_turn_base = baseline.get("pass_at_turn", {}) or {}
    blame_cur = current.get("blame_at_k", {}) or {}
    blame_base = baseline.get("blame_at_k", {}) or {}
    patch_cur = current.get("patch_locality", {}) or {}
    patch_base = baseline.get("patch_locality", {}) or {}

    def _diff_seq(cur: Any, base: Any) -> Any:
        if not isinstance(cur, list) or not isinstance(base, list):
            return None
        if len(cur) != len(base):
            return None
        return [_diff_numeric(c, b) for c, b in zip(cur, base)]

    pass_at_turn = {
        k: _diff_numeric(pass_at_turn_cur.get(k), pass_at_turn_base.get(k))
        for k in set(pass_at_turn_cur) | set(pass_at_turn_base)
    }
    blame_at_k = {
        k: _diff_numeric(blame_cur.get(k), blame_base.get(k))
        for k in set(blame_cur) | set(blame_base)
    }
    patch_locality = {
        key: _diff_numeric(patch_cur.get(key), patch_base.get(key))
        for key in {"min_distance_mean", "mean_distance", "mean_iou", "line_count_mean"}
    }

    return {
        "success_rate": _diff_numeric(current.get("success_rate"), baseline.get("success_rate")),
        "pass_at_turn": pass_at_turn,
        "blame_at_k": blame_at_k,
        "patch_locality": patch_locality,
        "anchor_hit_rate": _diff_numeric(current.get("anchor_hit_rate"), baseline.get("anchor_hit_rate")),
        "precision_at_1": _diff_numeric(current.get("precision_at_1"), baseline.get("precision_at_1")),
        "cf_valid_at_1": _diff_numeric(current.get("cf_valid_at_1"), baseline.get("cf_valid_at_1")),
        "pass_slope": _diff_numeric(current.get("pass_slope"), baseline.get("pass_slope")),
        "pass_r2": _diff_numeric(current.get("pass_r2"), baseline.get("pass_r2")),
        "pass_rate_by_turn": _diff_seq(current.get("pass_rate_by_turn"), baseline.get("pass_rate_by_turn")),
    }


def _compute_delta(current: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    """Compute deltas between two evaluation results keyed by mode."""
    return {
        mode: _diff_mode(current.get(mode, {}), baseline.get(mode, {}))
        for mode in {"baseline", "error_aware"}
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate TraceBench datasets (baseline vs error_aware) and compare two JSON files."
    )
    parser.add_argument(
        "--tracebench",
        type=str,
        default=str(ROOT / "output" / "tracebench_multi_anchor.json"),
        help="Path to tracebench.json (after injection).",
    )
    parser.add_argument(
        "--tracebench-raw",
        type=str,
        default=str(ROOT / "output" / "tracebench_raw.json"),
        help="Path to tracebench_raw.json (before injection).",
    )
    parser.add_argument(
        "--skip-raw",
        action="store_true",
        help="Only evaluate the injected TraceBench (skip running the raw dataset).",
    )
    parser.add_argument(
        "--runner",
        required=True,
        help="Callable to run a debug session, e.g., mypkg.module:run_debug_session.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name for Together-compatible OpenAI API (optional; falls back to env).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Together API key (optional; falls back to TOGETHER_API_KEY env).",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Together API base URL (optional; falls back to TOGETHER_API_BASE env).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature forwarded to runner via TRACEBENCH_TEMPERATURE env.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=5,
        help="Max turns per problem for the debugging loop.",
    )
    parser.add_argument(
        "--blame-k",
        type=int,
        nargs="*",
        default=None,
        help="k values for blame@k (default: 1 3 5).",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Optional JSONL checkpoint file to resume TraceBench runs (stores per-problem logs).",
    )
    parser.add_argument(
        "--force-llm-on-raw",
        action="store_true",
        help="Force LLM to run on the raw dataset (ignore any pre-existing corrupted_code).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Propagate API/model settings to runners through standard env vars.
    if args.api_key:
        os.environ["TOGETHER_API_KEY"] = args.api_key
    if args.api_url:
        os.environ["TOGETHER_API_BASE"] = args.api_url
    if args.model:
        os.environ["TRACEBENCH_MODEL"] = args.model
        os.environ.setdefault("TOGETHER_MODEL", args.model)
    if args.temperature is not None:
        os.environ["TRACEBENCH_TEMPERATURE"] = str(args.temperature)

    runner = _import_runner(args.runner)

    ckpt_main = args.checkpoint
    ckpt_raw = f"{args.checkpoint}.raw" if args.checkpoint else None

    detailed_output_dir = None
    if args.checkpoint:
        ckpt_path = Path(args.checkpoint)
        detailed_output_dir = str(ckpt_path.parent / "detailed_results")

    tb_results = run_tracebench_eval(
        tracebench_path=args.tracebench,
        run_debug_session=runner,
        max_turns=args.max_turns,
        blame_k=args.blame_k,
        checkpoint_path=ckpt_main,
        detailed_output_dir=detailed_output_dir,
    )
    output = {Path(args.tracebench).name: tb_results}

    if not args.skip_raw:
        raw_results = run_tracebench_eval(
            tracebench_path=args.tracebench_raw,
            run_debug_session=runner,
            max_turns=args.max_turns,
            blame_k=args.blame_k,
            checkpoint_path=ckpt_raw,
            detailed_output_dir=f"{detailed_output_dir}_raw" if detailed_output_dir else None,
            force_llm_on_raw=args.force_llm_on_raw,
        )
        output[Path(args.tracebench_raw).name] = raw_results
        output["delta(tracebench - tracebench_raw)"] = _compute_delta(tb_results, raw_results)

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
