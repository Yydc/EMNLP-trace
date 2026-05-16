#!/usr/bin/env python3
"""Stage 3: analyze records → paper-grade numbers + tables.

Ingests `out/records/*_records.jsonl` (which must carry per-attempt detail
under the ``subproblems`` field — see 02_run_evaluation.py), the labeled
dataset (`data/derived/tracebench_*_labeled.json` from `make label`), and
runs each problem through ``TraceabilityMetrics.analyze`` to get
blame@k / outside_g / regression_rate / slope / repeats / cf_valid@1.

Outputs (under --output-dir / "tables" or "analysis"):
    tables/main_gap_table.csv             (model × split rows × 12 cols)
    tables/fault_family_distribution.csv  (5 families; dataset-derived)
    tables/outside_g_regression.csv       (r, n, p, ci per model + pooled)
    tables/cost_accounting.csv            (per-model: calls, tokens)

    analysis/numbers.json                 (single source of truth)
    analysis/per_edit_scatter.jsonl       (for fig_micro_propagation)
    analysis/per_problem_metrics.jsonl    (one row per (model, problem))

Hard rows are DERIVED from Full rows via problem_id slicing.
"""
from __future__ import annotations
import argparse, csv, json, math, sys
from pathlib import Path
from collections import defaultdict
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))


def load_records(records_dir: Path) -> dict:
    """Return {(model, split): [record, ...]}."""
    out = defaultdict(list)
    for jsonl in records_dir.glob("*_records.jsonl"):
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


def pearson_r(xs, ys):
    """Pure-Python Pearson r. Returns None if undefined (n<2 or zero variance)."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx2 = sum((x - mx) ** 2 for x in xs)
    sy2 = sum((y - my) ** 2 for y in ys)
    if sx2 == 0 or sy2 == 0:
        return None
    return num / math.sqrt(sx2 * sy2)


def fisher_ci(r, n, alpha=0.05):
    """Fisher-z 95% CI for Pearson r + two-tailed p (normal approx).

    Returns (lo, hi, p) or (None, None, None) if undefined.
    """
    if r is None or n is None or n < 4:
        return None, None, None
    from math import erfc
    r_safe = max(-0.999999, min(0.999999, r))
    z = math.atanh(r_safe)
    se = 1.0 / math.sqrt(n - 3)
    p = erfc(abs(z) * math.sqrt(n - 3) / math.sqrt(2))
    z_crit = 1.959963984540054  # invnorm(0.975)
    z_lo, z_hi = z - z_crit * se, z + z_crit * se
    return math.tanh(z_lo), math.tanh(z_hi), p


def _safe_mean(xs):
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def _safe_mean_pct(xs):
    """Mean over non-None values, as percentage rounded to 1dp."""
    v = _safe_mean(xs)
    return round(v * 100, 1) if v is not None else None


def compute_per_problem_metrics(
    records_by_cell: dict,
    labeled_by_pid: dict,
) -> dict:
    """For each (model, split), run TraceabilityMetrics.analyze on each record.

    Returns {(model, split): [{problem_id, **metrics, solved, total_turns, ...}, ...]}.
    Records lacking ``subproblems`` (pre-patch runs) are still processed; metrics
    that need per-attempt detail will be None.
    """
    from core.traceability_metrics import TraceabilityMetrics
    tm = TraceabilityMetrics(k_values=[1, 3, 5])

    per_problem = defaultdict(list)
    for (model, split), recs in records_by_cell.items():
        n_skipped = 0
        for rec in recs:
            pid = rec.get("problem_id")
            entry = labeled_by_pid.get(pid)
            if entry is None:
                n_skipped += 1
                continue
            # Reconstruct problem_log from the record. NOTE: our `turn_results`
            # uses `attempts: int` (count summary), but TraceabilityMetrics expects
            # `attempts: list[dict]`. We pass only `subproblems` (the real per-attempt
            # detail) and omit turn_results so the metrics code takes the
            # subproblems branch.
            problem_log = {
                "problem_id": pid,
                "solved": rec.get("solved", False),
                "total_turns": rec.get("total_turns"),
                "total_attempts": rec.get("total_attempts"),
                "subproblems": rec.get("subproblems") or [{"attempts": []}],
            }

            file_path = (
                (entry.get("code_context") or {}).get("file_path")
                or "solution.py"
            )
            try:
                metrics = tm.analyze(entry, problem_log, file_path)
            except Exception as e:
                print(f"  ! {model} {pid}: analyze crashed: {e}", file=sys.stderr)
                continue

            per_problem[(model, split)].append({
                "problem_id": pid,
                "solved": bool(rec.get("solved")),
                "total_turns": rec.get("total_turns"),
                "total_attempts": rec.get("total_attempts"),
                "blame_at_1": metrics.get("blame_at_k", {}).get(1),
                "blame_at_3": metrics.get("blame_at_k", {}).get(3),
                "outside_g": metrics.get("outside_g"),
                "regression_rate": metrics.get("regression_rate"),
                "trajectory_slope": metrics.get("trajectory_slope"),
                "repeats": metrics.get("repeats"),
                "patch_locality_min_dist": (metrics.get("patch_locality") or {}).get("min_distance"),
                "precision_at_1": metrics.get("precision_at_1"),
                "cf_valid_at_1": metrics.get("cf_valid_at_1"),
            })
        if n_skipped:
            print(f"  ! {model}: {n_skipped} records skipped (problem_id missing from labeled)",
                  file=sys.stderr)
    return per_problem


def _aggregate_cell(model: str, split: str, probs: list) -> dict:
    n = len(probs)
    if n == 0:
        return {"model": model, "split": split, "n": 0}
    pass1 = round(sum(int(p["solved"]) for p in probs) / n * 100, 1)
    return {
        "model": model, "split": split, "n": n,
        "pass1": pass1,
        "blame1":   _safe_mean_pct([p.get("blame_at_1") for p in probs]),
        "blame3":   _safe_mean_pct([p.get("blame_at_3") for p in probs]),
        "out_g":    _safe_mean([p.get("outside_g") for p in probs]),
        "reg_rate": _safe_mean([p.get("regression_rate") for p in probs]),
        "avg_turns": round(_safe_mean([p.get("total_turns") for p in probs]) or 0, 2),
        "repeats":  round(_safe_mean([p.get("repeats") for p in probs]) or 0, 2),
        "slope":    _safe_mean([p.get("trajectory_slope") for p in probs]),
        "gap":      None,
    }


def build_main_gap_rows(per_problem: dict, hard_pids: set) -> list:
    """One row per (model, {full, hard}) cell, aggregated from per-problem."""
    out = []
    for (model, split), probs in sorted(per_problem.items()):
        if split != "full":
            continue
        out.append(_aggregate_cell(model, "full", probs))
        hard = [p for p in probs if p["problem_id"] in hard_pids]
        if hard:
            out.append(_aggregate_cell(model, "hard", hard))
    # Fill hard rows' "gap" = full_pass1 - hard_pass1
    by_model = defaultdict(dict)
    for r in out:
        if r.get("pass1") is not None:
            by_model[r["model"]][r["split"]] = r["pass1"]
    for r in out:
        if r["split"] == "hard":
            full_pass = by_model[r["model"]].get("full")
            if full_pass is not None and r.get("pass1") is not None:
                r["gap"] = round(full_pass - r["pass1"], 1)
    return out


def build_outside_g_regression(per_problem: dict) -> tuple[list, dict]:
    """Per-model Pearson(outside_g, regression_rate) + pooled across all models."""
    rows = []
    pooled_x, pooled_y = [], []
    for (model, split), probs in sorted(per_problem.items()):
        if split != "full":
            continue
        pairs = [
            (p["outside_g"], p["regression_rate"])
            for p in probs
            if p["outside_g"] is not None and p["regression_rate"] is not None
        ]
        if not pairs:
            rows.append({"model": model, "n": 0, "r": None, "p": None, "ci_lo": None, "ci_hi": None})
            continue
        xs = [x for x, _ in pairs]
        ys = [y for _, y in pairs]
        r = pearson_r(xs, ys)
        lo, hi, p = fisher_ci(r, len(xs))
        rows.append({
            "model": model, "n": len(xs),
            "r": round(r, 4) if r is not None else None,
            "p": round(p, 6) if p is not None else None,
            "ci_lo": round(lo, 4) if lo is not None else None,
            "ci_hi": round(hi, 4) if hi is not None else None,
        })
        pooled_x.extend(xs); pooled_y.extend(ys)

    pooled = {"model": "_pooled", "n": len(pooled_x),
              "r": None, "p": None, "ci_lo": None, "ci_hi": None}
    if pooled_x:
        r = pearson_r(pooled_x, pooled_y)
        lo, hi, p = fisher_ci(r, len(pooled_x))
        pooled.update({
            "r": round(r, 4) if r is not None else None,
            "p": round(p, 6) if p is not None else None,
            "ci_lo": round(lo, 4) if lo is not None else None,
            "ci_hi": round(hi, 4) if hi is not None else None,
        })
    rows.append(pooled)
    return rows, pooled


def build_cost_accounting(records_by_cell: dict) -> list:
    """Per-model totals: problems, attempts, tokens."""
    out = []
    for (model, split), recs in sorted(records_by_cell.items()):
        if split != "full":
            continue
        n = len(recs)
        attempts = sum(r.get("total_attempts", 0) or 0 for r in recs)
        in_tok = sum(r.get("total_input_tokens", 0) or 0 for r in recs)
        out_tok = sum(r.get("total_output_tokens", 0) or 0 for r in recs)
        out.append({
            "model": model, "n_problems": n,
            "total_attempts": attempts,
            "total_input_tokens": in_tok,
            "total_output_tokens": out_tok,
            "tokens_per_problem_in":  round(in_tok / n) if n else 0,
            "tokens_per_problem_out": round(out_tok / n) if n else 0,
            "attempts_per_problem":   round(attempts / n, 2) if n else 0,
        })
    return out


def build_per_edit_scatter(per_problem: dict) -> list:
    """One row per problem with (outside_g, regression_rate) — fig scatter input."""
    rows = []
    for (model, split), probs in per_problem.items():
        if split != "full":
            continue
        for p in probs:
            og = p.get("outside_g")
            rr = p.get("regression_rate")
            if og is None and rr is None:
                continue
            rows.append({
                "model": model,
                "problem_id": p["problem_id"],
                "outside_g": og, "regression_rate": rr,
                "blame_at_1": p.get("blame_at_1"),
                "solved": p.get("solved"),
                "total_attempts": p.get("total_attempts"),
            })
    return rows


def write_csv(path: Path, rows: list, fieldnames=None) -> None:
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


def write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"  wrote {path} ({len(rows)} rows)")


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

    # 1. Labeled datasets (prefer derived/labeled; fall back to raw)
    lf = args.labeled_full or (REPO_ROOT / "data" / "derived" / "tracebench_full_labeled.json")
    lh = args.labeled_hard or (REPO_ROOT / "data" / "derived" / "tracebench_hard_labeled.json")
    if not lf.exists():
        print(f"WARN: {lf} missing — outside_g / blame@k / cf_valid@1 will be null. "
              f"Run `make label` first.", file=sys.stderr)
        lf = REPO_ROOT / "data" / "tracebench_full.json"
    if not lh.exists():
        lh = REPO_ROOT / "data" / "tracebench_hard.json"

    full_data = json.load(open(lf))
    hard_data = json.load(open(lh))
    hard_pids = {e["problem_id"] for e in hard_data}
    labeled_by_pid = {e["problem_id"]: e for e in full_data}
    print(f"Loaded {len(full_data)} full + {len(hard_data)} hard entries (labeled={lf.name})")
    print(f"Hard subset: {len(hard_pids)} problem_ids")

    # 2. Records
    records_by_cell = load_records(args.records_dir)
    if not records_by_cell:
        print("WARN: no records found.", file=sys.stderr); return
    print(f"Loaded records from {len(records_by_cell)} (model,split) cells")

    # 3. Per-problem metrics via TraceabilityMetrics
    print("\nComputing per-problem metrics (TraceabilityMetrics)...")
    per_problem = compute_per_problem_metrics(records_by_cell, labeled_by_pid)
    n_problems = sum(len(v) for v in per_problem.values())
    print(f"  computed metrics for {n_problems} (model, problem) pairs")

    per_prob_rows = []
    for (model, split), probs in per_problem.items():
        for p in probs:
            per_prob_rows.append({"model": model, "split": split, **p})
    write_jsonl(out_analysis / "per_problem_metrics.jsonl", per_prob_rows)

    # 4. Main gap table
    rows = build_main_gap_rows(per_problem, hard_pids)
    write_csv(out_tables / "main_gap_table.csv", rows,
              fieldnames=["model", "split", "n", "pass1", "blame1", "blame3",
                          "out_g", "reg_rate", "avg_turns", "repeats", "slope", "gap"])

    # 5. Outside-G / RegressionRate correlation (the paper's flagship claim)
    og_rows, og_pooled = build_outside_g_regression(per_problem)
    write_csv(out_tables / "outside_g_regression.csv", og_rows,
              fieldnames=["model", "n", "r", "p", "ci_lo", "ci_hi"])

    # 6. Cost accounting
    cost_rows = build_cost_accounting(records_by_cell)
    write_csv(out_tables / "cost_accounting.csv", cost_rows)

    # 7. Per-edit scatter (for figures)
    scatter_rows = build_per_edit_scatter(per_problem)
    write_jsonl(out_analysis / "per_edit_scatter.jsonl", scatter_rows)

    # 8. Fault-family distribution (dataset-derived; independent of records)
    try:
        from core.fault_families import family_counts_by_difficulty
        fam = family_counts_by_difficulty(full_data)
        fam_rows = []
        for family, by_band in fam.items():
            fam_rows.append({
                "family": family,
                "easy_med": by_band["easy_med"],
                "hard": by_band["hard"],
                "very_hard_plus": by_band["very_hard_plus"],
                "total": sum(by_band.values()),
            })
        write_csv(out_tables / "fault_family_distribution.csv", fam_rows)
    except Exception as e:
        print(f"  ! fault_family_distribution skipped: {e}")

    # 9. numbers.json
    numbers = {
        "_meta": {
            "generated_by": "code/scripts/03_analyze.py",
            "records_dir": str(args.records_dir),
            "n_cells_processed": len(records_by_cell),
            "hard_n": len(hard_pids),
            "full_n": len(full_data),
            "n_problems_with_metrics": n_problems,
        },
        "n_models": len({m for (m, _) in records_by_cell}),
        "n_full_problems": len(full_data),
        "n_hard_problems": len(hard_pids),
        "outside_g_r":    og_pooled.get("r"),
        "outside_g_n":    og_pooled.get("n"),
        "outside_g_p":    og_pooled.get("p"),
        "outside_g_ci_lo": og_pooled.get("ci_lo"),
        "outside_g_ci_hi": og_pooled.get("ci_hi"),
        # early-drift placeholders — implementation TBD (miss-hit stratification)
        "early_drift_cum_patch_delta": None,
        "early_drift_outside_g_delta": None,
        "early_drift_blame1_delta": None,
    }
    (out_analysis / "numbers.json").write_text(json.dumps(numbers, indent=2))
    print(f"  wrote {out_analysis / 'numbers.json'}")

    print("\nDone. Next: `make figures && make tex && make check`.")


if __name__ == "__main__":
    main()
