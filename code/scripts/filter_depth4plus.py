#!/usr/bin/env python3
"""
Clean and down-sample the depth4plus dataset to remove redundant tests.

Default behavior:
- Deduplicate identical (input, output) test pairs (order preserved).
- Cap extremely repetitive void functions (output None) to a small sample.
- Limit how many cases we keep per output value and per subproblem overall.
- Drop problems whose subproblems do not meet a minimal test coverage bar.

Outputs the cleaned dataset to data/depth4.json by default.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def normalize(value: Any) -> str:
    """Stable string key for deduplication/bucketing."""
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return repr(value)


def deduplicate_tests(tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop duplicate (input, output) pairs while keeping original order."""
    seen = set()
    unique: List[Dict[str, Any]] = []
    for t in tests:
        key = (normalize(t.get("input")), normalize(t.get("output")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique


def trim_tests(
    tests: List[Dict[str, Any]],
    max_tests_per_output: int,
    max_tests_per_subproblem: int,
    max_void_tests: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Down-sample a subproblem's tests to remove redundant coverage.

    Returns trimmed tests and a dict describing how many were dropped per reason.
    """
    dropped = {"void_cap": 0, "per_output_cap": 0, "per_subproblem_cap": 0}
    if not tests:
        return tests, dropped

    outputs = [t.get("output") for t in tests]
    none_ratio = sum(1 for o in outputs if o is None or str(o) == "None") / len(outputs)

    # If it's basically a void function with tons of examples, keep only a slice.
    if none_ratio >= 0.8 and len(tests) > max_void_tests:
        dropped["void_cap"] = len(tests) - max_void_tests
        return tests[:max_void_tests], dropped

    buckets: Dict[str, int] = defaultdict(int)
    trimmed: List[Dict[str, Any]] = []

    for idx, t in enumerate(tests):
        if len(trimmed) >= max_tests_per_subproblem:
            dropped["per_subproblem_cap"] += len(tests) - idx
            break

        out_key = normalize(t.get("output"))
        if buckets[out_key] >= max_tests_per_output:
            dropped["per_output_cap"] += 1
            continue

        buckets[out_key] += 1
        trimmed.append(t)

    return trimmed, dropped


def clean_problem(
    problem: Dict[str, Any],
    max_tests_per_output: int,
    max_tests_per_subproblem: int,
    max_void_tests: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Clean a single problem; returns the cleaned problem and per-subproblem trim logs.
    """
    cleaned = dict(problem)
    cleaned["problem_id"] = cleaned.get("problem_id") or cleaned.get("problem-id") or cleaned.get(
        "original_source_id", "UNKNOWN"
    )

    trim_logs: List[Dict[str, Any]] = []
    new_subs: List[Dict[str, Any]] = []

    for sp in cleaned.get("subproblems", []):
        before_tests = sp.get("test_code", []) or []
        deduped = deduplicate_tests(before_tests)
        trimmed, drop_reasons = trim_tests(
            deduped,
            max_tests_per_output=max_tests_per_output,
            max_tests_per_subproblem=max_tests_per_subproblem,
            max_void_tests=max_void_tests,
        )

        newsp = dict(sp)
        newsp["test_code"] = trimmed
        new_subs.append(newsp)

        removed = len(before_tests) - len(trimmed)
        if removed > 0:
            outputs = [t.get("output") for t in deduped] or [None]
            none_ratio = sum(1 for o in outputs if o is None or str(o) == "None") / len(outputs)
            trim_logs.append(
                {
                    "problem": cleaned.get("problem-id") or cleaned.get("problem_id"),
                    "subproblem": sp.get("name", "unknown"),
                    "before": len(before_tests),
                    "after": len(trimmed),
                    "removed": removed,
                    "none_ratio": round(none_ratio, 3),
                    "reasons": drop_reasons,
                }
            )

    cleaned["subproblems"] = new_subs
    return cleaned, trim_logs


def filter_problems(
    problems: List[Dict[str, Any]],
    min_coverage: float,
    min_tests_per_subproblem: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Keep problems where enough subproblems still have tests after cleaning.
    """
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []

    for prob in problems:
        subs = prob.get("subproblems", [])
        if not subs:
            dropped.append({**prob, "_drop_reason": "no_subproblems"})
            continue

        good = sum(1 for sp in subs if len(sp.get("test_code", [])) >= min_tests_per_subproblem)
        coverage = good / len(subs)
        if good > 0 and coverage >= min_coverage:
            kept.append(prob)
        else:
            dropped.append({**prob, "_drop_reason": f"low_coverage:{coverage:.2f}"})

    return kept, dropped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean depth4plus dataset and trim redundant tests.")
    parser.add_argument("--input", default="depth4plus.json", help="Path to raw depth4plus JSON.")
    parser.add_argument("--output", default="data/depth4.json", help="Path to save the cleaned dataset.")
    parser.add_argument("--max-tests-per-subproblem", type=int, default=40, help="Cap per subproblem.")
    parser.add_argument("--max-tests-per-output", type=int, default=5, help="Cap per distinct output value.")
    parser.add_argument("--max-void-tests", type=int, default=10, help="Cap when outputs are mostly None/void.")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.3,
        help="Min fraction of subproblems with enough tests required to keep a problem.",
    )
    parser.add_argument(
        "--min-tests-per-subproblem",
        type=int,
        default=3,
        help="Subproblem needs at least this many tests to count toward coverage.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"✗ 输入文件不存在: {input_path}")

    with input_path.open("r", encoding="utf-8") as fin:
        data = json.load(fin)

    total_tests_before = sum(len(sp.get("test_code", [])) for p in data for sp in p.get("subproblems", []))
    max_tests_before = max((len(sp.get("test_code", [])) for p in data for sp in p.get("subproblems", [])), default=0)

    cleaned_problems: List[Dict[str, Any]] = []
    trim_logs: List[Dict[str, Any]] = []

    for prob in data:
        cleaned, logs = clean_problem(
            prob,
            max_tests_per_output=args.max_tests_per_output,
            max_tests_per_subproblem=args.max_tests_per_subproblem,
            max_void_tests=args.max_void_tests,
        )
        cleaned_problems.append(cleaned)
        trim_logs.extend(logs)

    kept, dropped = filter_problems(
        cleaned_problems,
        min_coverage=args.min_coverage,
        min_tests_per_subproblem=args.min_tests_per_subproblem,
    )

    total_tests_after = sum(len(sp.get("test_code", [])) for p in kept for sp in p.get("subproblems", []))
    max_tests_after = max((len(sp.get("test_code", [])) for p in kept for sp in p.get("subproblems", [])), default=0)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fout:
        json.dump(kept, fout, ensure_ascii=False, indent=2)

    # Summary
    print("=" * 60)
    print("深度4数据清洗完成")
    print("=" * 60)
    print(f"输入问题数: {len(data)}")
    print(f"输出问题数: {len(kept)} (移除 {len(dropped)})")
    print(f"测试用例总数: {total_tests_before} -> {total_tests_after}")
    print(f"单个子任务最大测试数: {max_tests_before} -> {max_tests_after}")
    print("\n修剪最多的前 5 个子任务:")
    for entry in sorted(trim_logs, key=lambda x: x["removed"], reverse=True)[:5]:
        reasons = {k: v for k, v in entry["reasons"].items() if v}
        print(
            f"  - {entry['problem']} / {entry['subproblem']}: "
            f"{entry['before']} -> {entry['after']} (删除 {entry['removed']}), "
            f"none_ratio={entry['none_ratio']}, reasons={reasons}"
        )
    print(f"\n已保存到: {output_path}")


if __name__ == "__main__":
    main()
