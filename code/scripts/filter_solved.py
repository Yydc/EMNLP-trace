#!/usr/bin/env python3
"""
Filter solved problems from a generated solutions file.

Outputs two files:
- data_solved.json: only problems whose solutions pass the harness (or are accepted without verification).
- data_solved_original.json: the matching original problems (from the unmodified dataset).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure repo root is on path so `harness` resolves when called from scripts/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import TestHarness


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def filter_solved(
    solutions_path: Path,
    original_path: Path,
    out_solved: Path,
    out_original: Path,
    out_unsolved: Optional[Path] = None,
    out_unsolved_original: Optional[Path] = None,
    verify: bool = True,
):
    solutions = load_json(solutions_path)
    original = load_json(original_path)
    orig_map: Dict[str, Dict] = {p.get("problem-id"): p for p in original}

    harness = TestHarness() if verify else None
    solved: List[Dict] = []
    solved_original: List[Dict] = []
    unsolved: List[Dict] = []
    unsolved_original: List[Dict] = []

    for prob in solutions:
        pid = prob.get("problem-id")
        sol_code = prob.get("solution")
        if not sol_code or len(str(sol_code)) < 50:
            unsolved.append(prob)
            if pid in orig_map:
                unsolved_original.append(orig_map[pid])
            continue

        if verify and harness:
            ok, _ = harness.run_all_tests(sol_code, prob)
            if not ok:
                unsolved.append(prob)
                if pid in orig_map:
                    unsolved_original.append(orig_map[pid])
                continue

        solved.append(prob)
        if pid in orig_map:
            solved_original.append(orig_map[pid])

    if harness:
        harness.cleanup()

    out_solved.parent.mkdir(parents=True, exist_ok=True)
    out_original.parent.mkdir(parents=True, exist_ok=True)
    out_solved.write_text(json.dumps(solved, indent=2, ensure_ascii=False), encoding="utf-8")
    out_original.write_text(json.dumps(solved_original, indent=2, ensure_ascii=False), encoding="utf-8")

    if out_unsolved:
        out_unsolved.parent.mkdir(parents=True, exist_ok=True)
        out_unsolved.write_text(json.dumps(unsolved, indent=2, ensure_ascii=False), encoding="utf-8")
    if out_unsolved_original:
        out_unsolved_original.parent.mkdir(parents=True, exist_ok=True)
        out_unsolved_original.write_text(
            json.dumps(unsolved_original, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(f"Solved problems: {len(solved)}")
    print(f"Written solved: {out_solved}")
    print(f"Written solved originals: {out_original}")
    if out_unsolved:
        print(f"Unsolved problems: {len(unsolved)}")
        print(f"Written unsolved: {out_unsolved}")
    if out_unsolved_original:
        print(f"Written unsolved originals: {out_unsolved_original}")


def main():
    parser = argparse.ArgumentParser(description="Filter solved problems from solutions JSON.")
    parser.add_argument("--solutions", required=True, help="Path to generated solutions JSON")
    parser.add_argument("--original", required=True, help="Path to original dataset JSON")
    parser.add_argument("--out-solved", default="output/data_solved.json", help="Where to write solved problems with solutions")
    parser.add_argument(
        "--out-original",
        default="output/data_solved_original.json",
        help="Where to write the matching original problems",
    )
    parser.add_argument(
        "--out-unsolved",
        default=None,
        help="Optional: write problems that failed verification or have no solution",
    )
    parser.add_argument(
        "--out-unsolved-original",
        default=None,
        help="Optional: write originals for the unsolved subset",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip harness verification (use solution presence only)",
    )
    args = parser.parse_args()

    filter_solved(
        solutions_path=Path(args.solutions),
        original_path=Path(args.original),
        out_solved=Path(args.out_solved),
        out_original=Path(args.out_original),
        out_unsolved=Path(args.out_unsolved) if args.out_unsolved else None,
        out_unsolved_original=Path(args.out_unsolved_original) if args.out_unsolved_original else None,
        verify=not args.no_verify,
    )


if __name__ == "__main__":
    main()
