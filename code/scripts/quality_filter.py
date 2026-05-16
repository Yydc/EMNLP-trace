#!/usr/bin/env python3
"""
Dataset quality filter (no API required).

Filters out low-quality subproblems based on:
  - too few tests
  - low unique ratio
  - too many None outputs
Optionally drops problems whose remaining subproblems fail a minimum coverage bar.

Example:
  python scripts/quality_filter.py \
    -i data/data_improved.json \
    -o data/data_high.json \
    --min-tests 3 \
    --min-unique 0.5 \
    --max-none 0.5 \
    --min-coverage 0.6 \
    --max-tests-per-output 4 \
    --max-tests-per-subproblem 35
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def normalize(val: Any) -> str:
    """Stable key for (input, output) pairs."""
    try:
        return json.dumps(val, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return repr(val)


def dedup_tests(tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate (input, output) pairs while preserving order."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for t in tests:
        key = (normalize(t.get("input")), normalize(t.get("output")))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def trim_tests(
    tests: List[Dict[str, Any]],
    max_per_output: int,
    max_per_sub: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Cap highly repetitive outputs and overall subproblem length."""
    buckets: Dict[str, int] = defaultdict(int)
    trimmed: List[Dict[str, Any]] = []
    dropped = {"per_output_cap": 0, "per_sub_cap": 0}

    for idx, t in enumerate(tests):
        if len(trimmed) >= max_per_sub:
            dropped["per_sub_cap"] += len(tests) - idx
            break
        out_key = normalize(t.get("output"))
        if buckets[out_key] >= max_per_output:
            dropped["per_output_cap"] += 1
            continue
        buckets[out_key] += 1
        trimmed.append(t)
    return trimmed, dropped


def subproblem_quality(
    tests: List[Dict[str, Any]],
    min_tests: int,
    min_unique: float,
    max_none: float,
    max_per_output: int,
    max_per_sub: int,
) -> Tuple[bool, List[Dict[str, Any]], Dict[str, Any]]:
    """Return (keep_flag, cleaned_tests, stats)."""
    stats: Dict[str, Any] = {}
    if not tests:
        stats.update({"total": 0, "unique_ratio": 0, "none_ratio": 0})
        return False, [], stats

    deduped = dedup_tests(tests)
    total = len(deduped)
    none_ratio = sum(
        1 for t in deduped if t.get("output") is None or str(t.get("output")) == "None"
    ) / total

    unique_ratio = len(deduped) / len(tests) if tests else 0

    trimmed, drop_reasons = trim_tests(deduped, max_per_output, max_per_sub)
    stats.update(
        {
            "total": len(tests),
            "after_dedup": total,
            "after_trim": len(trimmed),
            "unique_ratio": unique_ratio,
            "none_ratio": none_ratio,
            "drop_reasons": drop_reasons,
        }
    )

    keep = (
        len(trimmed) >= min_tests
        and unique_ratio >= min_unique
        and none_ratio < max_none
    )
    return keep, trimmed if keep else [], stats


def filter_dataset(
    data: List[Dict[str, Any]],
    min_tests: int,
    min_unique: float,
    max_none: float,
    min_coverage: float,
    max_per_output: int,
    max_per_sub: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    stats = {
        "problems_input": len(data),
        "problems_kept": 0,
        "problems_dropped": 0,
        "subproblems_input": 0,
        "subproblems_kept": 0,
        "subproblems_dropped": 0,
    }

    for prob in data:
        subproblems = prob.get("subproblems", [])
        stats["subproblems_input"] += len(subproblems)

        cleaned_subs = []
        for sp in subproblems:
            keep, cleaned_tests, _ = subproblem_quality(
                sp.get("test_code", []),
                min_tests=min_tests,
                min_unique=min_unique,
                max_none=max_none,
                max_per_output=max_per_output,
                max_per_sub=max_per_sub,
            )
            if keep:
                new_sp = dict(sp)
                new_sp["test_code"] = cleaned_tests
                cleaned_subs.append(new_sp)
            else:
                stats["subproblems_dropped"] += 1

        coverage = len(cleaned_subs) / len(subproblems) if subproblems else 0
        if coverage >= min_coverage and cleaned_subs:
            new_prob = dict(prob)
            new_prob["subproblems"] = cleaned_subs
            kept.append(new_prob)
            stats["problems_kept"] += 1
            stats["subproblems_kept"] += len(cleaned_subs)
        else:
            stats["problems_dropped"] += 1

    return kept, stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter dataset for higher-quality subproblems.")
    parser.add_argument("-i", "--input", required=True, help="Input JSON file.")
    parser.add_argument("-o", "--output", required=True, help="Output JSON file.")
    parser.add_argument("--min-tests", type=int, default=3, help="Minimum tests required to keep a subproblem.")
    parser.add_argument("--min-unique", type=float, default=0.5, help="Minimum unique ratio to keep a subproblem.")
    parser.add_argument("--max-none", type=float, default=0.5, help="Maximum allowed None ratio.")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.6,
        help="Minimum fraction of subproblems that must survive per problem.",
    )
    parser.add_argument("--max-tests-per-output", type=int, default=5, help="Cap per distinct output value.")
    parser.add_argument("--max-tests-per-subproblem", type=int, default=40, help="Cap per subproblem after trimming.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    inp = Path(args.input)
    if not inp.exists():
        raise SystemExit(f"Input not found: {inp}")

    with inp.open("r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned, stats = filter_dataset(
        data=data,
        min_tests=args.min_tests,
        min_unique=args.min_unique,
        max_none=args.max_none,
        min_coverage=args.min_coverage,
        max_per_output=args.max_tests_per_output,
        max_per_sub=args.max_tests_per_subproblem,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("Quality filter completed")
    print("=" * 60)
    print(f"Problems: {stats['problems_input']} -> {stats['problems_kept']} (dropped {stats['problems_dropped']})")
    print(
        f"Subproblems: {stats['subproblems_input']} -> {stats['subproblems_kept']} "
        f"(dropped {stats['subproblems_dropped']})"
    )
    print(f"Saved to: {out}")


if __name__ == "__main__":
    main()
