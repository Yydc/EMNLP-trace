#!/usr/bin/env python3
"""Stage 1 wrapper: invoke the active-fault labeler in-process.

Thin CLI over `src.core.active_fault_labeler.label_dataset`.

Usage::
    python code/scripts/01_label_active_faults.py \\
        --input  data/tracebench_full.json \\
        --output data/derived/tracebench_full_labeled.json \\
        --workers 8

Or, after both are labeled:
    python code/scripts/01_label_active_faults.py --summary-only \\
        --inputs data/derived/tracebench_full_labeled.json data/derived/tracebench_hard_labeled.json \\
        --output-csv out/analysis/active_fault_label_summary.csv
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))


def label(args) -> None:
    from core.active_fault_labeler import label_dataset
    label_dataset(args.input, args.output,
                  max_workers=args.workers, limit=args.limit)


def summarize(args) -> None:
    rows = []
    for path in args.inputs:
        name = Path(path).stem
        data = json.load(open(path))
        counter = Counter()
        n_entries = len(data)
        n_with_active = 0
        n_with_trusted = 0
        for e in data:
            labels = e.get("active_faults_per_turn", {})
            diag = labels.get("_labels", {})
            has_active = any(v for k, v in labels.items() if k != "_labels" and v)
            if has_active: n_with_active += 1
            for v in diag.values():
                tag = v.split(":")[0]
                counter[tag] += 1
                if tag == "trusted": n_with_trusted += 1
        rows.append({
            "dataset": name,
            "n_entries": n_entries,
            "n_with_active_label": n_with_active,
            "n_with_trusted_fallback": n_with_trusted,
            **{f"diag_{k}": v for k, v in counter.most_common()},
        })
    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fieldnames = sorted({k for r in rows for k in r.keys()})
        with out_csv.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader(); w.writerows(rows)
        print(f"wrote {out_csv}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode")

    # Default: label mode (no subcommand; backward compat with Makefile)
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None,
                    help="(debug) only label first N entries")
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--inputs", nargs="+",
                    help="(with --summary-only) labeled JSONs to summarize")
    ap.add_argument("--output-csv",
                    help="(with --summary-only) output CSV path")
    args = ap.parse_args()

    if args.summary_only:
        summarize(args)
    else:
        if not args.input or not args.output:
            ap.error("--input and --output are required (or use --summary-only)")
        label(args)


if __name__ == "__main__":
    main()
