#!/usr/bin/env python3
"""Stage 3: single-pass analysis.

Ingests all `out/records/*_full_records.jsonl`, the labeled dataset
files, and produces the 8 canonical CSV tables + `numbers.json`
(every scalar claim the paper makes is a key here).

Hard rows are DERIVED from Full rows via problem_id slicing — there is
no separate Hard run.

Outputs (under --output-dir / "tables" or "analysis"):
    tables/main_gap_table.csv             (12 rows × 11 cols)
    tables/difficulty_bins.csv            (3 bands)
    tables/fault_family_distribution.csv  (5 families; dataset-derived)
    tables/fault_family_performance.csv   (5 families × 5 metrics on one model)
    tables/outside_g_regression.csv       (r, p, n, CI per model + pooled)
    tables/early_drift.csv                (Miss-Hit deltas)
    tables/failure_modes.csv              (5 modes × 6 models, fractions)
    tables/cost_accounting.csv            (per-model: calls, tokens, time)

    analysis/numbers.json                 (single source of truth)
    analysis/per_edit_scatter.jsonl       (for fig_micro_propagation)
    analysis/per_turn_curves.json         (for fig_micro_drift)
"""
from __future__ import annotations
import argparse, csv, json, statistics, sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))


def load_records(records_dir: Path) -> dict:
    """Return {(model, split): [record, ...]}."""
    out = defaultdict(list)
    for jsonl in records_dir.glob("*_records.jsonl"):
        # filename: <model>_<split>_records.jsonl
        stem = jsonl.stem.rsplit("_records", 1)[0]
        if stem.endswith("_full"):
            model, split = stem[:-5], "full"
        elif stem.endswith("_hard"):
            model, split = stem[:-5], "hard"
        else:
            continue
        with jsonl.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out[(model, split)].append(json.loads(line))
    return out


def main_gap_rows(records_by_cell: dict, hard_pids: set) -> list:
    """Build the 12-row main result table from Full records + Hard derivation."""
    out = []
    for (model, split), rows in sorted(records_by_cell.items()):
        if split != "full":
            continue
        # Compute aggregates over Full
        n = len(rows)
        if n == 0: continue
        pass1 = sum(1 for r in rows if r["solved"]) / n * 100
        # Placeholder: real Blame@1 etc. depend on metric_v2 / traceability_metrics.
        out.append({
            "model": model, "split": "full",
            "n": n, "pass1": round(pass1, 1),
            "blame1": None, "blame3": None, "out_g": None,
            "reg_rate": None, "avg_turns": None, "repeats": None,
            "slope": None, "gap": None,
        })
        # Derive Hard
        hard_rows = [r for r in rows if r["problem_id"] in hard_pids]
        n_hard = len(hard_rows)
        if n_hard > 0:
            pass1_h = sum(1 for r in hard_rows if r["solved"]) / n_hard * 100
            out.append({
                "model": model, "split": "hard",
                "n": n_hard, "pass1": round(pass1_h, 1),
                "blame1": None, "blame3": None, "out_g": None,
                "reg_rate": None, "avg_turns": None, "repeats": None,
                "slope": None, "gap": None,
            })
    return out


def write_csv(path: Path, rows: list, fieldnames: list = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print(f"  (skip {path.name} — no rows)")
        return
    if not fieldnames:
        fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"  wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="pipeline.yaml")
    ap.add_argument("--records-dir", required=True, type=Path)
    ap.add_argument("--labeled-full", type=Path)
    ap.add_argument("--labeled-hard", type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()

    out_tables = args.output_dir / "tables"
    out_analysis = args.output_dir / "analysis"
    out_tables.mkdir(parents=True, exist_ok=True)
    out_analysis.mkdir(parents=True, exist_ok=True)

    # 1. Hard problem_ids for slicing
    hard_data = json.load(open(args.labeled_hard or REPO_ROOT / "data/tracebench_hard.json"))
    hard_pids = {e["problem_id"] for e in hard_data}
    print(f"Hard subset: {len(hard_pids)} problem_ids")

    # 2. Load all records
    records_by_cell = load_records(args.records_dir)
    if not records_by_cell:
        print("WARN: no records found. Did `make eval` finish?", file=sys.stderr)
        return
    print(f"Loaded records from {len(records_by_cell)} (model,split) cells")

    # 3. Main gap table (currently minimal — populate metrics_v2 + traceability_metrics
    #    integration here when the runners actually emit edited_lines / blame_spans)
    rows = main_gap_rows(records_by_cell, hard_pids)
    write_csv(out_tables / "main_gap_table.csv", rows,
              fieldnames=["model", "split", "n", "pass1", "blame1", "blame3",
                          "out_g", "reg_rate", "avg_turns", "repeats", "slope", "gap"])

    # 4. Fault-family distribution from the dataset itself
    full_data = json.load(open(args.labeled_full or REPO_ROOT / "data/tracebench_full.json"))
    from core.fault_families import family_counts_by_difficulty, render_family_table
    fam = family_counts_by_difficulty(full_data)
    fam_rows = []
    for family, by_band in fam.items():
        row = {"family": family, "easy_med": by_band["easy_med"],
               "hard": by_band["hard"], "very_hard_plus": by_band["very_hard_plus"],
               "total": sum(by_band.values())}
        fam_rows.append(row)
    write_csv(out_tables / "fault_family_distribution.csv", fam_rows)

    # 5. Single source of truth: numbers.json
    # Population grows as we wire in more metric computations.
    numbers = {
        "_meta": {
            "generated_by": "code/scripts/03_analyze.py",
            "records_dir": str(args.records_dir),
            "n_cells_processed": len(records_by_cell),
            "hard_n": len(hard_pids),
            "full_n": len(full_data),
        },
        "n_models": len({m for (m, _) in records_by_cell}),
        "n_full_problems": len(full_data),
        "n_hard_problems": len(hard_pids),
        # placeholders for outside_g_regression — wired in when per-edit logs available
        "outside_g_r": None,
        "outside_g_n": None,
        "outside_g_p": None,
        "outside_g_ci_lo": None,
        "outside_g_ci_hi": None,
        # early drift Miss-Hit
        "early_drift_cum_patch_delta": None,
        "early_drift_outside_g_delta": None,
        "early_drift_blame1_delta": None,
    }
    (out_analysis / "numbers.json").write_text(json.dumps(numbers, indent=2))
    print(f"  wrote {out_analysis / 'numbers.json'}")

    print("\nDone. Next: `make figures && make tex && make check`.")


if __name__ == "__main__":
    main()
