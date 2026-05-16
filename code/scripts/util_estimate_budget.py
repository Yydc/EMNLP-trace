#!/usr/bin/env python3
"""Print the cost/time roll-up from pipeline.yaml so the user knows
what the next `make all` will spend BEFORE launching it.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr); sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="pipeline.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))

    print("=" * 64)
    print(f"  Budget estimate for {cfg['project']} ({cfg['paper_target']})")
    print("=" * 64)

    # Per-model
    print("\nPer-model cost (single Full pass, single seed):")
    api_total = h100_total = 0
    for m in cfg["models"]:
        api = m.get("estimated_api_usd", 0)
        gpu = m.get("estimated_h100_hours", 0)
        api_total += api; h100_total += gpu
        print(f"  {m['id']:22s} access={m['access']:5s}  "
              f"H100={gpu:>4.1f}h   API=${api:>7.2f}")
    print("  " + "─" * 56)
    print(f"  {'TOTAL':22s}                  "
          f"H100={h100_total:>4.1f}h   API=${api_total:>7.2f}")

    # Stage roll-up
    print("\nPer-stage wall-clock (sequential):")
    total_min = 0
    for sname, s in cfg["stages"].items():
        est = s.get("estimated", {})
        wmin = est.get("wall_clock_minutes")
        whr  = est.get("wall_clock_hours")
        if whr is not None: wmin = whr * 60
        wmin = wmin or 0
        total_min += wmin
        cost = est.get("cost_usd", 0)
        print(f"  {sname:22s}  {wmin/60:>4.1f}h     ${cost:>7.2f}")

    print(f"\n  Total wall-clock (sequential): {total_min/60:.1f} h")
    print(f"  Total API cost:                ${api_total:.2f}")
    buf_pct = cfg["budget"].get("api_buffer_pct", 35)
    print(f"  + {buf_pct}% buffer:               ${api_total * buf_pct/100:.2f}")
    print(f"  GRAND TOTAL API:               ${api_total * (1 + buf_pct/100):.2f}")
    print()


if __name__ == "__main__":
    main()
