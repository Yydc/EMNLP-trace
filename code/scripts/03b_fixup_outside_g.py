#!/usr/bin/env python3
"""Stage 3b: post-hoc Outside-G fixup using anchor_value string matching.

Why:
  03_analyze computes Outside-G with TraceabilityMetrics.active_spans_from_entry,
  which returns the labeler's anchor_line in ORIGINAL codebase coordinates
  (e.g. line 29 of the original clean file). But the runner shows the LLM
  a per-turn snippet (accumulated_code + target_code), and records
  edited_lines / patch_spans in SNIPPET coordinates (line 1..N of the
  snippet). The two coordinate systems never overlap → out_g ≈ 1.0 for
  every problem, an artifact, not a real metric.

Fix:
  Each labeled injection carries an `anchor.anchor_value` field — a
  unique TRACER_XXXX string inserted at the injection point during
  dataset generation. We grep that string in the model's code_before
  (which IS the snippet shown to the LLM) to find the snippet-coord
  anchor line. Then G-region = [snippet_line ± radius] in snippet
  coords matches the attempt's edited_lines coordinate system.

Inputs (read-only — does NOT modify records or labeler output):
  out/records/<model>_full_records.jsonl   (must have subproblems[].attempts[]
                                            with code_before + edited_lines)
  data/derived/tracebench_full_labeled.json

Outputs:
  out/analysis/outside_g_fixup.jsonl   (one row per (model, problem, turn,
                                        attempt) with corrected outside_g)
  out/analysis/outside_g_fixup_summary.json   (per-model + pooled stats)

Stand-alone: does not touch 03_analyze.py. Run after the cell finishes.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
from collections import defaultdict
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[2]

ANCHOR_RADIUS = 3  # G-region = [anchor_line - 3, anchor_line + 3]


def _find_anchor_line(snippet: str, anchor_value: str) -> int | None:
    """Return 1-based line number where anchor_value appears, or None."""
    if not (snippet and anchor_value):
        return None
    for i, line in enumerate(snippet.splitlines(), 1):
        if anchor_value in line:
            return i
    return None


def _build_G_region(snippet_anchor_lines: list[int], radius: int) -> set[int]:
    """Union of [line - radius, line + radius] per anchor → set of int lines."""
    g = set()
    for ln in snippet_anchor_lines:
        g.update(range(max(1, ln - radius), ln + radius + 1))
    return g


def _pearson_r(xs, ys):
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


def _fisher_ci(r, n, alpha=0.05):
    if r is None or n is None or n < 4:
        return None, None, None
    from math import erfc
    rs = max(-0.999999, min(0.999999, r))
    z = math.atanh(rs)
    se = 1.0 / math.sqrt(n - 3)
    p = erfc(abs(z) * math.sqrt(n - 3) / math.sqrt(2))
    zc = 1.959963984540054
    return math.tanh(z - zc*se), math.tanh(z + zc*se), p


def fixup_record(rec: dict, entry: dict) -> list[dict]:
    """For one (model, problem) record, walk subproblems × attempts and emit
    one row per attempt with the corrected outside_g.

    Skips attempts where we can't translate (no active fault for this turn,
    anchor_value not found in code_before, or no edited_lines).
    """
    # Build inj_id -> anchor_value (from labeler's top-level injections)
    inj_by_id = {inj.get('injection_id'): inj
                 for inj in (entry.get('injections') or [])
                 if inj.get('injection_id')}
    afpt = entry.get('active_faults_per_turn') or {}

    rows = []
    for sp in rec.get('subproblems') or []:
        turn_id = sp.get('turn_id')
        if turn_id is None:
            continue
        tid_key = str(turn_id)
        active_ids = afpt.get(tid_key) or []
        if not active_ids:
            continue  # no faults in this turn → outside_g undefined

        attempts = sp.get('attempts') or []
        if not attempts:
            continue

        # Resolve snippet_anchor_line(s) using the FIRST attempt's code_before
        # (which has the TRACER intact, before the model rewrote the file).
        first_cb = attempts[0].get('code_before') or ''
        anchor_lines = []
        for iid in active_ids:
            inj = inj_by_id.get(iid)
            if not inj:
                continue
            av = (inj.get('anchor') or {}).get('anchor_value')
            ln = _find_anchor_line(first_cb, av)
            if ln is not None:
                anchor_lines.append(ln)

        if not anchor_lines:
            # Anchor untranslatable for this turn — mark and skip
            for att in attempts:
                rows.append({
                    'problem_id': rec.get('problem_id'),
                    'model': rec.get('model'),
                    'turn': turn_id,
                    'attempt_number': att.get('attempt_number'),
                    'outside_g_fixup': None,
                    'reason': 'anchor_untranslatable',
                })
            continue

        G = _build_G_region(anchor_lines, ANCHOR_RADIUS)

        for att in attempts:
            edited = att.get('edited_lines') or []
            if not edited:
                rows.append({
                    'problem_id': rec.get('problem_id'),
                    'model': rec.get('model'),
                    'turn': turn_id,
                    'attempt_number': att.get('attempt_number'),
                    'outside_g_fixup': None,
                    'reason': 'no_edited_lines',
                })
                continue
            outside = sum(1 for ln in edited if ln not in G)
            ratio = outside / len(edited)
            rows.append({
                'problem_id': rec.get('problem_id'),
                'model': rec.get('model'),
                'turn': turn_id,
                'attempt_number': att.get('attempt_number'),
                'outside_g_fixup': round(ratio, 4),
                'edited_lines_count': len(edited),
                'G_region_size': len(G),
                'snippet_anchor_lines': anchor_lines,
                'reason': None,
            })

    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--records-dir', type=Path,
                    default=REPO_ROOT / 'out/records')
    ap.add_argument('--labeled-full', type=Path,
                    default=REPO_ROOT / 'data/derived/tracebench_full_labeled.json')
    ap.add_argument('--output-dir', type=Path,
                    default=REPO_ROOT / 'out/analysis')
    args = ap.parse_args()

    print(f"loading {args.labeled_full} ...", file=sys.stderr)
    labeled = {e['problem_id']: e for e in json.load(open(args.labeled_full))}
    print(f"  {len(labeled)} labeled entries", file=sys.stderr)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixup_path = args.output_dir / 'outside_g_fixup.jsonl'

    all_rows = []
    per_model_problems = defaultdict(list)  # model -> [outside_g_per_problem]

    for rec_path in sorted(args.records_dir.glob('*_records.jsonl')):
        stem = rec_path.stem.rsplit('_records', 1)[0]
        if not (stem.endswith('_full') or stem.endswith('_hard')):
            continue
        model = stem.rsplit('_', 1)[0]
        split = stem.rsplit('_', 1)[1]
        if split != 'full':
            continue

        rows_for_model = []
        for line in rec_path.open():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            pid = rec.get('problem_id')
            entry = labeled.get(pid)
            if entry is None:
                continue
            attempt_rows = fixup_record(rec, entry)
            for r in attempt_rows:
                r['model'] = model
                rows_for_model.append(r)

        all_rows.extend(rows_for_model)

        # Aggregate to per-problem (mean of valid attempts) → per-model summary
        per_problem = defaultdict(list)
        for r in rows_for_model:
            if r['outside_g_fixup'] is not None:
                per_problem[r['problem_id']].append(r['outside_g_fixup'])
        problem_means = [mean(v) for v in per_problem.values()]
        per_model_problems[model].extend(problem_means)

        n_attempts = len(rows_for_model)
        n_valid = sum(1 for r in rows_for_model if r['outside_g_fixup'] is not None)
        n_problems = len(per_problem)
        print(f"  {model}: {n_attempts} attempts, {n_valid} valid outside_g "
              f"({100*n_valid/max(n_attempts,1):.0f}%), {n_problems} problems with data",
              file=sys.stderr)

    # Write per-attempt fixup jsonl
    with fixup_path.open('w') as fh:
        for r in all_rows:
            fh.write(json.dumps(r) + '\n')
    print(f"wrote {fixup_path} ({len(all_rows)} rows)", file=sys.stderr)

    # Per-model stats
    summary = {
        '_meta': {
            'generator': 'code/scripts/03b_fixup_outside_g.py',
            'method': 'anchor_value string match in code_before snippet (snippet coords)',
            'anchor_radius': ANCHOR_RADIUS,
        },
        'per_model': {},
    }
    for model, og_values in per_model_problems.items():
        og_values = sorted(og_values)
        if not og_values:
            summary['per_model'][model] = {'n_problems_with_outside_g': 0}
            continue
        # Quintiles for distribution insight
        def pct(p):
            idx = max(0, min(len(og_values) - 1, int(len(og_values) * p)))
            return round(og_values[idx], 3)
        summary['per_model'][model] = {
            'n_problems_with_outside_g': len(og_values),
            'mean_outside_g': round(mean(og_values), 4),
            'p10': pct(0.10), 'p25': pct(0.25), 'p50': pct(0.50),
            'p75': pct(0.75), 'p90': pct(0.90),
        }

    sum_path = args.output_dir / 'outside_g_fixup_summary.json'
    sum_path.write_text(json.dumps(summary, indent=2))
    print(f"wrote {sum_path}", file=sys.stderr)

    print('\n=== per-model Outside-G fixup distribution ===')
    for m, s in summary['per_model'].items():
        if s.get('n_problems_with_outside_g', 0) == 0:
            print(f"  {m}: (no valid outside_g)")
            continue
        print(f"  {m}: n={s['n_problems_with_outside_g']}  mean={s['mean_outside_g']}  "
              f"p10={s['p10']} p50={s['p50']} p90={s['p90']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
