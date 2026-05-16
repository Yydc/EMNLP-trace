#!/usr/bin/env python3
"""
Build TraceBench from CodeFlowBench using GPT extension.

Usage:
    # Mock mode (for testing)
    export TBGEN_MOCK=1
    python scripts/build_tracebench.py --output data/tracebench --limit 5

    # Real mode (requires OpenAI API key)
    export OPENAI_API_KEY=your_key
    python scripts/build_tracebench.py \
        --codeflow-path data/codeflow.json \
        --output data/tracebench \
        --target-turns 8 \
        --rollbacks 2 \
        --limit 20
"""
from __future__ import annotations
import argparse
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tbgen.benchmark_builder import (
    TraceBenchBuilder,
    ExtensionConfig,
    build_tracebench_from_codeflow
)

def main():
    parser = argparse.ArgumentParser(
        description="Build extended TraceBench from CodeFlowBench"
    )

    parser.add_argument(
        "--codeflow-path",
        default="",
        help="Path to CodeFlowBench dataset (or HuggingFace auto-download)"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for TraceBench tasks"
    )

    parser.add_argument(
        "--target-turns",
        type=int,
        default=8,
        help="Target number of turns per scenario (default: 8)"
    )

    parser.add_argument(
        "--rollbacks",
        type=int,
        default=2,
        help="Target number of rollback points (default: 2)"
    )

    parser.add_argument(
        "--noisy-rationales",
        type=int,
        default=3,
        help="Number of additional noisy rationales (default: 3)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of tasks to process"
    )

    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model to use (default: gpt-4o)"
    )

    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "together"],
        help="LLM provider to use (default: openai)"
    )

    parser.add_argument(
        "--api-key",
        default=None,
        help="API key (or use OPENAI_API_KEY/TOGETHER_API_KEY env var)"
    )

    parser.add_argument(
        "--no-fuzz",
        action="store_true",
        help="Disable fuzz trigger generation"
    )

    parser.add_argument(
        "--no-shift-tags",
        action="store_true",
        help="Disable shift_tags generation"
    )

    args = parser.parse_args()

    if not os.environ.get("TBGEN_MOCK"):
        if args.provider == "openai" and not (args.api_key or os.environ.get("OPENAI_API_KEY")):
            print("Error: Set OPENAI_API_KEY or use --api-key")
            sys.exit(1)
        elif args.provider == "together" and not (args.api_key or os.environ.get("TOGETHER_API_KEY")):
            print("Error: Set TOGETHER_API_KEY or use --api-key")
            sys.exit(1)

    config = ExtensionConfig(
        target_turns=args.target_turns,
        add_noisy_rationales=args.noisy_rationales,
        add_rollback_points=args.rollbacks,
        add_shift_tags=not args.no_shift_tags,
        add_fuzz_triggers=not args.no_fuzz,
        model=args.model,
        provider=args.provider,
        api_key=args.api_key
    )

    print("=== TraceBench Builder ===")
    print(f"Provider: {config.provider}")
    print(f"Model: {config.model}")
    print(f"Target turns: {config.target_turns}")
    print(f"Rollback points: {config.add_rollback_points}")
    print(f"Noisy rationales: {config.add_noisy_rationales}")
    print(f"Output: {args.output}")
    print()

    try:
        count = build_tracebench_from_codeflow(
            codeflow_dataset_path=args.codeflow_path,
            output_dir=args.output,
            config=config,
            limit=args.limit
        )

        print(f"\n✓ Successfully built {count} tasks")
        print(f"Output directory: {args.output}")

        analyze_built_dataset(args.output)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def analyze_built_dataset(output_dir: str):
    """Analyze the built dataset."""
    import json
    from collections import Counter

    output_path = Path(output_dir)
    tasks = list(output_path.glob("*/task.json"))

    if not tasks:
        return

    print("\n=== Dataset Analysis ===")
    print(f"Total tasks: {len(tasks)}")

    difficulties = []
    tracks = []
    turn_counts = []
    rollback_counts = []
    all_shift_tags = []

    for task_file in tasks:
        with open(task_file, 'r') as f:
            task = json.load(f)

        difficulties.append(task.get("difficulty", "unknown"))
        tracks.append(task.get("track", "unknown"))
        all_shift_tags.extend(task.get("shift_tags", []))

        scenarios = task.get("scenarios", {})
        for scenario in scenarios.values():
            turns = scenario.get("turns", [])
            turn_counts.append(len(turns))
            rollback_count = sum(1 for t in turns if t.get("rollback", False))
            rollback_counts.append(rollback_count)

    print(f"\nDifficulty distribution:")
    for difficulty, count in Counter(difficulties).items():
        print(f"  {difficulty}: {count}")

    print(f"\nTrack distribution:")
    for track, count in Counter(tracks).items():
        print(f"  {track}: {count}")

    if turn_counts:
        avg_turns = sum(turn_counts) / len(turn_counts)
        print(f"\nTurns per scenario:")
        print(f"  Average: {avg_turns:.1f}")
        print(f"  Range: {min(turn_counts)}-{max(turn_counts)}")

    if rollback_counts:
        avg_rollbacks = sum(rollback_counts) / len(rollback_counts)
        print(f"\nRollbacks per scenario:")
        print(f"  Average: {avg_rollbacks:.1f}")
        print(f"  Max: {max(rollback_counts)}")

    print(f"\nTop shift_tags:")
    for tag, count in Counter(all_shift_tags).most_common(10):
        print(f"  {tag}: {count}")

if __name__ == "__main__":
    main()
