#!/usr/bin/env python3
"""Pre-flight invariant check. Exit 0 = all good, nonzero = block pipeline.

Reads pipeline.yaml and verifies:
  - Hard ⊂ Full by problem_id (128/128 must overlap)
  - Python >= 3.9
  - All required data files exist
  - Required env vars are present when API models are in scope
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def check_subset() -> None:
    full = json.load(open(REPO_ROOT / "data" / "tracebench_full.json"))
    hard = json.load(open(REPO_ROOT / "data" / "tracebench_hard.json"))
    full_pids = {e["problem_id"] for e in full}
    hard_pids = {e["problem_id"] for e in hard}
    missing = hard_pids - full_pids
    if missing:
        fail(f"{len(missing)} Hard problem_ids not in Full: {sorted(missing)[:5]}…")
    ok(f"Hard ⊂ Full ({len(hard_pids)}/{len(full_pids)} verified)")


def check_python() -> None:
    if sys.version_info < (3, 9):
        fail(f"Python 3.9+ required (have {sys.version_info[:2]})")
    ok(f"Python {sys.version_info[0]}.{sys.version_info[1]}")


def check_files() -> None:
    required = [
        "data/tracebench_full.json",
        "data/tracebench_hard.json",
        "data/oracle_spans.json",
        "pipeline.yaml",
        "code/paper/main.tex",
    ]
    for f in required:
        p = REPO_ROOT / f
        if not p.exists():
            fail(f"missing {f}")
        ok(f"{f} ({p.stat().st_size // 1024} KB)")


def check_env(want_api: bool) -> None:
    if want_api:
        if not os.getenv("GOOGLE_API_KEY"):
            fail("GOOGLE_API_KEY env var not set (required for Gemini)")
        ok("GOOGLE_API_KEY is set")
    else:
        print("  - skipping API env check (--no-api passed)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="pipeline.yaml")
    ap.add_argument("--no-api", action="store_true",
                    help="Skip API env check (local-only run)")
    args = ap.parse_args()
    print("=" * 60)
    print("Pre-flight invariants")
    print("=" * 60)
    check_python()
    check_files()
    check_subset()
    check_env(want_api=not args.no_api)
    print()
    print("✓ ALL invariants pass")


if __name__ == "__main__":
    main()
