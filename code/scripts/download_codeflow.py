#!/usr/bin/env python3
"""Download CodeFlowBench from HuggingFace"""
import sys
from pathlib import Path

try:
    from datasets import load_dataset

    print("Downloading CodeFlowBench from HuggingFace...")
    print("Dataset: WaterWang-001/CodeFlowBench-2505")
    print()

    dataset = load_dataset("WaterWang-001/CodeFlowBench-2505")

    print(f"✓ Downloaded successfully!")
    print(f"  Train split: {len(dataset['train'])} samples")
    print()

    # Show first few examples
    print("First 3 examples:")
    for i, item in enumerate(dataset['train'][:3]):
        print(f"\n  [{i+1}] ID: {item.get('id', 'unknown')}")
        print(f"      Track: {item.get('track', 'unknown')}")
        print(f"      Difficulty: {item.get('difficulty', 'unknown')}")
        title = item.get('title', '')
        if len(title) > 60:
            title = title[:60] + "..."
        print(f"      Title: {title}")

    # Save to file for later use
    output_dir = Path("data/codeflow_raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    import json
    with open(output_dir / "codeflow_sample.json", 'w') as f:
        sample = [dataset['train'][i] for i in range(min(20, len(dataset['train'])))]
        json.dump(sample, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved 20 samples to: {output_dir}/codeflow_sample.json")

except ImportError:
    print("Error: datasets package not installed")
    print("Install: pip install datasets")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
