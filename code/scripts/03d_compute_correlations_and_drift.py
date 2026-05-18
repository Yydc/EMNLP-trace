#!/usr/bin/env python3
"""Stage 3d: Outside-G × RegressionRate Pearson + Early-drift Hit-vs-Miss deltas.

Inputs:
  results/v1_6model/analysis/outside_g_fixup.jsonl       (per-attempt, from 03b)
  results/v1_6model/analysis/regression_rate_fixup.jsonl (per-problem, from 03c)
  out/records/<model>_full_records.jsonl                 (for cum_patch + last-turn lookup)

Outputs:
  results/v1_6model/tables/outside_g_regression.csv   (per-model Pearson + pooled)
  results/v1_6model/analysis/numbers.json             (writes outside_g_r/n/p/ci_lo/ci_hi +
                                                       early_drift_cum_patch_delta +
                                                       early_drift_outside_g_delta with bootstrap CIs)
  results/v1_6model/analysis/early_drift_summary.json (per-model Hit vs Miss breakdown)

Definitions used:
  Hit  := problem where the FIRST attempt at turn 0 has outside_g_fixup == 0
          (model's earliest edit was inside the active fault region)
  Miss := outside_g_fixup > 0 for that first attempt (mis-localized early)

  cum_patch_size(problem) := total len(edited_lines) summed across all attempts
                              in the problem's trajectory
  last_turn_outside_g(problem) := mean outside_g_fixup across attempts in the
                                  LAST turn that has any valid outside_g

  Deltas (per model, then pooled):
    cum_patch_delta  = mean(cum_patch_size | Miss) - mean(cum_patch_size | Hit)
    outside_g_delta  = mean(last_turn_outside_g | Miss) - mean(last_turn_outside_g | Hit)

  CIs: percentile bootstrap, 200 iters, 95%.
"""
from __future__ import annotations
import argparse, csv, json, math, random, sys
from pathlib import Path
from collections import defaultdict
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_ITERS = 200
ALPHA = 0.05
random.seed(20260518)


# ---------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------

def pearson_r(xs, ys):
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x - mx)*(y - my) for x, y in zip(xs, ys))
    sx2 = sum((x - mx)**2 for x in xs)
    sy2 = sum((y - my)**2 for y in ys)
    if sx2 == 0 or sy2 == 0:
        return None
    return num / math.sqrt(sx2 * sy2)


def fisher_ci(r, n, alpha=0.05):
    if r is None or n is None or n < 4:
        return None, None, None
    from math import erfc
    rs = max(-0.999999, min(0.999999, r))
    z = math.atanh(rs)
    se = 1.0 / math.sqrt(n - 3)
    p = erfc(abs(z) * math.sqrt(n - 3) / math.sqrt(2))
    zc = 1.959963984540054
    return math.tanh(z - zc*se), math.tanh(z + zc*se), p


def bootstrap_delta(hit_vals, miss_vals, n_iter=BOOTSTRAP_ITERS):
    """Percentile bootstrap on mean(miss) - mean(hit). Returns (point, lo, hi)."""
    if not hit_vals or not miss_vals:
        return None, None, None
    point = mean(miss_vals) - mean(hit_vals)
    deltas = []
    for _ in range(n_iter):
        h = [random.choice(hit_vals) for _ in range(len(hit_vals))]
        m = [random.choice(miss_vals) for _ in range(len(miss_vals))]
        deltas.append(mean(m) - mean(h))
    deltas.sort()
    lo_i = int(ALPHA / 2 * n_iter)
    hi_i = int((1 - ALPHA / 2) * n_iter) - 1
    return point, deltas[lo_i], deltas[hi_i]


# ---------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------

def load_outside_g_per_attempt(path):
    """Returns {model: {problem_id: [(turn, attempt_number, outside_g), ...]}}.

    attempt_number may be None for some rows; use ordinal index as fallback.
    """
    out = defaultdict(lambda: defaultdict(list))
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get('outside_g_fixup') is None:
                continue
            out[r['model']][r['problem_id']].append(
                (r.get('turn'), r.get('attempt_number'), r['outside_g_fixup'])
            )
    return out


def load_reg_rate_per_problem(path):
    """Returns {(model, problem_id): reg_rate}."""
    out = {}
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get('regression_rate') is None:
                continue
            out[(r['model'], r['problem_id'])] = r['regression_rate']
    return out


def load_records_index(records_dir):
    """Returns {(model, problem_id): record_dict} for fast lookup."""
    out = {}
    for p in sorted(records_dir.glob('*_full_records.jsonl')):
        model = p.stem.rsplit('_records', 1)[0][:-5]
        for line in p.open():
            try:
                r = json.loads(line)
                out[(model, r['problem_id'])] = r
            except Exception:
                continue
    return out


# ---------------------------------------------------------------------
# Derived features
# ---------------------------------------------------------------------

def cum_patch_size(rec):
    """Sum of len(edited_lines) across all attempts in this problem."""
    total = 0
    for sp in rec.get('subproblems') or []:
        for att in sp.get('attempts') or []:
            total += len(att.get('edited_lines') or [])
    return total


def first_turn0_outside_g(og_attempts_for_problem):
    """Find the first (lowest attempt_number) outside_g at turn 0."""
    turn0 = [(an, og) for (t, an, og) in og_attempts_for_problem if str(t) == '0' or t == 0]
    if not turn0:
        return None
    # Sort by attempt_number (None last)
    turn0.sort(key=lambda x: (x[0] is None, x[0] or 0))
    return turn0[0][1]


def last_turn_outside_g(og_attempts_for_problem):
    """Mean outside_g in the LAST turn that has any value."""
    if not og_attempts_for_problem:
        return None
    by_turn = defaultdict(list)
    for (t, an, og) in og_attempts_for_problem:
        try:
            by_turn[int(t)].append(og)
        except (TypeError, ValueError):
            continue
    if not by_turn:
        return None
    last_t = max(by_turn.keys())
    return mean(by_turn[last_t])


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--records-dir', type=Path, default=REPO_ROOT / 'out/records')
    ap.add_argument('--results-dir', type=Path, default=REPO_ROOT / 'results/v1_6model')
    args = ap.parse_args()

    og_path = args.results_dir / 'analysis' / 'outside_g_fixup.jsonl'
    rr_path = args.results_dir / 'analysis' / 'regression_rate_fixup.jsonl'
    if not og_path.exists() or not rr_path.exists():
        sys.exit(f"missing inputs: {og_path} or {rr_path}")

    print(f"loading {og_path} ...", file=sys.stderr)
    og_per_attempt = load_outside_g_per_attempt(og_path)
    print(f"loading {rr_path} ...", file=sys.stderr)
    rr_per_problem = load_reg_rate_per_problem(rr_path)
    print(f"loading records from {args.records_dir} ...", file=sys.stderr)
    records = load_records_index(args.records_dir)

    # -----------------------------------------------------------------
    # Per-problem aggregation of outside_g (mean across attempts)
    # -----------------------------------------------------------------
    og_per_problem = {}  # (model, pid) -> mean outside_g
    for model, by_pid in og_per_attempt.items():
        for pid, rows in by_pid.items():
            vals = [og for (_, _, og) in rows]
            if vals:
                og_per_problem[(model, pid)] = mean(vals)

    # -----------------------------------------------------------------
    # Per-model Pearson r(outside_g, reg_rate) + pooled
    # -----------------------------------------------------------------
    correlation_rows = []
    pooled_x, pooled_y = [], []
    for model in sorted(og_per_attempt.keys()):
        xs, ys = [], []
        for pid in og_per_attempt[model].keys():
            og = og_per_problem.get((model, pid))
            rr = rr_per_problem.get((model, pid))
            if og is None or rr is None:
                continue
            xs.append(og); ys.append(rr)
        if not xs:
            correlation_rows.append({'model': model, 'n': 0,
                                     'r': None, 'p': None, 'ci_lo': None, 'ci_hi': None})
            continue
        r = pearson_r(xs, ys)
        lo, hi, p = fisher_ci(r, len(xs))
        correlation_rows.append({
            'model': model, 'n': len(xs),
            'r': round(r, 4) if r is not None else None,
            'p': round(p, 6) if p is not None else None,
            'ci_lo': round(lo, 4) if lo is not None else None,
            'ci_hi': round(hi, 4) if hi is not None else None,
        })
        pooled_x.extend(xs); pooled_y.extend(ys)

    pooled = {'model': '_pooled', 'n': len(pooled_x),
              'r': None, 'p': None, 'ci_lo': None, 'ci_hi': None}
    if pooled_x:
        r = pearson_r(pooled_x, pooled_y)
        lo, hi, p = fisher_ci(r, len(pooled_x))
        pooled.update({
            'r': round(r, 4) if r is not None else None,
            'p': round(p, 6) if p is not None else None,
            'ci_lo': round(lo, 4) if lo is not None else None,
            'ci_hi': round(hi, 4) if hi is not None else None,
        })
    correlation_rows.append(pooled)

    # Write correlation table
    csv_path = args.results_dir / 'tables' / 'outside_g_regression.csv'
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['model', 'n', 'r', 'p', 'ci_lo', 'ci_hi'])
        w.writeheader(); w.writerows(correlation_rows)
    print(f"wrote {csv_path}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Early-drift Hit-vs-Miss
    # -----------------------------------------------------------------
    drift_summary = {'per_model': {}, '_meta': {'bootstrap_iters': BOOTSTRAP_ITERS, 'seed': 20260518}}
    all_hit_cum, all_miss_cum = [], []
    all_hit_og,  all_miss_og  = [], []

    for model in sorted(og_per_attempt.keys()):
        hit_cum, miss_cum = [], []
        hit_og, miss_og = [], []
        for pid, og_rows in og_per_attempt[model].items():
            t0_og = first_turn0_outside_g(og_rows)
            if t0_og is None:
                continue
            rec = records.get((model, pid))
            if rec is None:
                continue
            cps = cum_patch_size(rec)
            last_og = last_turn_outside_g(og_rows)
            if t0_og == 0:
                hit_cum.append(cps)
                if last_og is not None: hit_og.append(last_og)
            else:
                miss_cum.append(cps)
                if last_og is not None: miss_og.append(last_og)

        cum_delta, cum_lo, cum_hi = bootstrap_delta(hit_cum, miss_cum)
        og_delta, og_lo, og_hi    = bootstrap_delta(hit_og,  miss_og)
        drift_summary['per_model'][model] = {
            'n_hit': len(hit_cum), 'n_miss': len(miss_cum),
            'cum_patch_mean_hit':  round(mean(hit_cum), 3) if hit_cum else None,
            'cum_patch_mean_miss': round(mean(miss_cum), 3) if miss_cum else None,
            'cum_patch_delta':     round(cum_delta, 3) if cum_delta is not None else None,
            'cum_patch_ci_lo':     round(cum_lo, 3) if cum_lo is not None else None,
            'cum_patch_ci_hi':     round(cum_hi, 3) if cum_hi is not None else None,
            'outside_g_last_mean_hit':  round(mean(hit_og), 4) if hit_og else None,
            'outside_g_last_mean_miss': round(mean(miss_og), 4) if miss_og else None,
            'outside_g_delta':          round(og_delta, 4) if og_delta is not None else None,
            'outside_g_ci_lo':          round(og_lo, 4) if og_lo is not None else None,
            'outside_g_ci_hi':          round(og_hi, 4) if og_hi is not None else None,
        }
        all_hit_cum.extend(hit_cum); all_miss_cum.extend(miss_cum)
        all_hit_og.extend(hit_og);   all_miss_og.extend(miss_og)

    pooled_cum_delta, pooled_cum_lo, pooled_cum_hi = bootstrap_delta(all_hit_cum, all_miss_cum)
    pooled_og_delta, pooled_og_lo, pooled_og_hi    = bootstrap_delta(all_hit_og,  all_miss_og)
    drift_summary['_pooled'] = {
        'n_hit': len(all_hit_cum), 'n_miss': len(all_miss_cum),
        'cum_patch_delta':  round(pooled_cum_delta, 3) if pooled_cum_delta is not None else None,
        'cum_patch_ci_lo':  round(pooled_cum_lo, 3) if pooled_cum_lo is not None else None,
        'cum_patch_ci_hi':  round(pooled_cum_hi, 3) if pooled_cum_hi is not None else None,
        'outside_g_delta':  round(pooled_og_delta, 4) if pooled_og_delta is not None else None,
        'outside_g_ci_lo':  round(pooled_og_lo, 4) if pooled_og_lo is not None else None,
        'outside_g_ci_hi':  round(pooled_og_hi, 4) if pooled_og_hi is not None else None,
    }

    drift_path = args.results_dir / 'analysis' / 'early_drift_summary.json'
    drift_path.write_text(json.dumps(drift_summary, indent=2))
    print(f"wrote {drift_path}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Update numbers.json
    # -----------------------------------------------------------------
    numbers_path = args.results_dir / 'analysis' / 'numbers.json'
    try:
        numbers = json.load(open(numbers_path))
    except Exception:
        numbers = {}

    numbers.setdefault('_meta', {})['updated_by'] = '03d_compute_correlations_and_drift.py'
    numbers['outside_g_r']    = pooled['r']
    numbers['outside_g_n']    = pooled['n']
    numbers['outside_g_p']    = pooled['p']
    numbers['outside_g_ci_lo'] = pooled['ci_lo']
    numbers['outside_g_ci_hi'] = pooled['ci_hi']
    numbers['early_drift_cum_patch_delta'] = drift_summary['_pooled']['cum_patch_delta']
    numbers['early_drift_cum_patch_ci_lo'] = drift_summary['_pooled']['cum_patch_ci_lo']
    numbers['early_drift_cum_patch_ci_hi'] = drift_summary['_pooled']['cum_patch_ci_hi']
    numbers['early_drift_outside_g_delta'] = drift_summary['_pooled']['outside_g_delta']
    numbers['early_drift_outside_g_ci_lo'] = drift_summary['_pooled']['outside_g_ci_lo']
    numbers['early_drift_outside_g_ci_hi'] = drift_summary['_pooled']['outside_g_ci_hi']
    numbers['early_drift_blame1_delta']    = None  # blame@k dropped; not computed
    numbers_path.write_text(json.dumps(numbers, indent=2))
    print(f"wrote {numbers_path}", file=sys.stderr)

    # -----------------------------------------------------------------
    # Console summary
    # -----------------------------------------------------------------
    print('\n=== Outside-G ↔ RegressionRate Pearson ===')
    for row in correlation_rows:
        print(f"  {row['model']:18s}  n={row['n']:4d}  r={row['r']}  p={row['p']}  "
              f"CI=[{row['ci_lo']}, {row['ci_hi']}]")

    print('\n=== Early-drift Hit-vs-Miss ===')
    pm = drift_summary['per_model']
    print(f"  {'model':18s}  {'n_hit':>5}  {'n_miss':>6}  {'cum_patch_delta':>16}  {'outside_g_delta':>16}")
    for m, d in sorted(pm.items()):
        print(f"  {m:18s}  {d['n_hit']:>5}  {d['n_miss']:>6}  "
              f"{d['cum_patch_delta'] if d['cum_patch_delta'] is not None else '—':>16}  "
              f"{d['outside_g_delta'] if d['outside_g_delta'] is not None else '—':>16}")
    pd = drift_summary['_pooled']
    print(f"  {'_POOLED':18s}  {pd['n_hit']:>5}  {pd['n_miss']:>6}  "
          f"{pd['cum_patch_delta']:>16}  {pd['outside_g_delta']:>16}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
