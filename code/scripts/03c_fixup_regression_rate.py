#!/usr/bin/env python3
"""Stage 3c: post-hoc RegressionRate fixup using saved per_test_results.

Why:
  metrics_v2.regression_rate_for_pair re-runs every test via subprocess.run
  (run_tests_per_test) for each attempt pair across all problems × all
  models — that's ~28K subprocesses, blowing 6h wall.

Fix:
  Each attempt log already carries `per_test_results: {test_index: bool}`
  (saved by run_multi_turn_debug_session). For each consecutive attempt
  pair (A→B) within a turn:
    passed_in_A = {i for i, ok in per_test_results[A].items() if ok}
    failed_in_B = {i for i, ok in per_test_results[B].items() if not ok}
    regression = passed_in_A ∩ failed_in_B
    rate = |regression| / |passed_in_A|  (0 if passed_in_A empty)

Aggregation:
  per_attempt rate → mean across pairs in turn → mean across turns → per-problem
  regression_rate. Stored as one row per (model, problem) so 03d_compute can
  join with outside_g_fixup.jsonl.

Inputs (read-only):
  out/records/<model>_full_records.jsonl

Outputs:
  results/v1_6model/analysis/regression_rate_fixup.jsonl   (per-problem)
  results/v1_6model/analysis/regression_rate_fixup_per_attempt.jsonl   (raw pairs)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from collections import defaultdict
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]


def _coerce_test_results(raw):
    """per_test_results may be saved as {str: bool} (JSON-roundtripped) or {int: bool}.
    Normalize to {int: bool}.
    """
    if not raw:
        return {}
    out = {}
    for k, v in raw.items():
        try:
            out[int(k)] = bool(v)
        except (TypeError, ValueError):
            continue
    return out


def regression_for_pair(ptr_a: dict, ptr_b: dict) -> float | None:
    """Per-pair regression rate using saved per_test_results.

    Returns None if A has no passing tests (rate undefined for that pair).
    """
    passed_a = {i for i, ok in ptr_a.items() if ok}
    if not passed_a:
        return None
    failed_b = {i for i, ok in ptr_b.items() if not ok}
    regressed = passed_a & failed_b
    return len(regressed) / len(passed_a)


def process_record(rec: dict) -> tuple[float | None, list[dict]]:
    """Walk subproblems × attempts; return (per-problem reg_rate, per-attempt-pair rows)."""
    per_pair = []
    per_turn = []
    for sp in rec.get('subproblems') or []:
        atts = sp.get('attempts') or []
        if len(atts) < 2:
            continue
        turn_rates = []
        for i in range(len(atts) - 1):
            a = atts[i]; b = atts[i + 1]
            ptr_a = _coerce_test_results(a.get('per_test_results'))
            ptr_b = _coerce_test_results(b.get('per_test_results'))
            if not ptr_a or not ptr_b:
                continue
            r = regression_for_pair(ptr_a, ptr_b)
            if r is None:
                continue
            turn_rates.append(r)
            per_pair.append({
                'problem_id': rec.get('problem_id'),
                'turn': a.get('turn'),
                'attempt_a': a.get('attempt_number'),
                'attempt_b': b.get('attempt_number'),
                'regression_rate': round(r, 4),
                'passed_in_a': sum(1 for v in ptr_a.values() if v),
                'failed_in_b_passed_in_a': sum(1 for i, v in ptr_a.items()
                                                if v and not ptr_b.get(i, True)),
            })
        if turn_rates:
            per_turn.append(mean(turn_rates))
    problem_rr = mean(per_turn) if per_turn else None
    return problem_rr, per_pair


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--records-dir', type=Path, default=REPO_ROOT / 'out/records')
    ap.add_argument('--output-dir', type=Path,
                    default=REPO_ROOT / 'results/v1_6model/analysis')
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_per_problem = args.output_dir / 'regression_rate_fixup.jsonl'
    out_per_pair = args.output_dir / 'regression_rate_fixup_per_attempt.jsonl'

    per_problem_rows = []
    per_pair_rows = []

    for rec_path in sorted(args.records_dir.glob('*_records.jsonl')):
        stem = rec_path.stem.rsplit('_records', 1)[0]
        if not stem.endswith('_full'):
            continue
        model = stem[:-5]

        n_records = 0
        n_with_rate = 0
        for line in rec_path.open():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            n_records += 1
            problem_rr, pair_rows = process_record(rec)
            for row in pair_rows:
                row['model'] = model
                per_pair_rows.append(row)
            if problem_rr is not None:
                n_with_rate += 1
            per_problem_rows.append({
                'model': model,
                'problem_id': rec.get('problem_id'),
                'regression_rate': round(problem_rr, 4) if problem_rr is not None else None,
                'n_attempt_pairs': len(pair_rows),
            })
        print(f"  {model}: {n_records} records, {n_with_rate} with valid reg_rate "
              f"({100*n_with_rate/max(n_records,1):.0f}%)", file=sys.stderr)

    with out_per_problem.open('w') as fh:
        for r in per_problem_rows:
            fh.write(json.dumps(r) + '\n')
    print(f"wrote {out_per_problem} ({len(per_problem_rows)} rows)", file=sys.stderr)

    with out_per_pair.open('w') as fh:
        for r in per_pair_rows:
            fh.write(json.dumps(r) + '\n')
    print(f"wrote {out_per_pair} ({len(per_pair_rows)} rows)", file=sys.stderr)

    # Per-model summary
    by_model = defaultdict(list)
    for r in per_problem_rows:
        if r['regression_rate'] is not None:
            by_model[r['model']].append(r['regression_rate'])

    print('\n=== per-model RegressionRate distribution ===')
    for m, values in sorted(by_model.items()):
        if not values:
            print(f"  {m}: no data"); continue
        values_sorted = sorted(values)
        def pct(p):
            i = max(0, min(len(values_sorted) - 1, int(len(values_sorted) * p)))
            return round(values_sorted[i], 3)
        print(f"  {m}: n={len(values)}  mean={round(mean(values), 4)}  "
              f"p10={pct(0.10)} p50={pct(0.50)} p90={pct(0.90)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
