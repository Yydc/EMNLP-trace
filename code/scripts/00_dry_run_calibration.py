#!/usr/bin/env python3
"""Day-0 dry-run calibration.

For each of 6 models, run a fixed 30-task stratified sample (10 each from
Easy/Med, Hard, VeryHard+) and report per-model:
  - parse_ok_rate (JSON blame_spans parseable)
  - empty_blame_rate
  - invalid_code_rate (extracted python doesn't parse)
  - timeout_rate
  - avg_input_tokens / avg_output_tokens
  - avg_latency_s
  - projected_full_cost_usd (Gemini only)

Output:
  out/dry_run/<model>_calibration.jsonl   — per-task raw
  out/dry_run/calibration_summary.csv     — 6 rows
  out/dry_run/calibration_report.md       — human-readable

This MUST be inspected before launching `make eval`. Gate criteria are
defined in pipeline.yaml `stages.dry_run.gate`.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time, random
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr); sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))


def sample_calibration(full_data: list, n_per_band: int = 4, seed: int = 12345) -> list:
    """Stratified sample: n_per_band each from Easy/Med, Hard, VeryHard+.

    Default n_per_band=4 → 12 tasks total per model. Across 6 models this
    fits comfortably in a 1-hour dry-run wall-clock budget (Gemini runs
    in parallel with the 5 sequential local-vLLM runs).
    """
    rng = random.Random(seed)
    bands = {"easy_med": [], "hard": [], "very_hard_plus": []}
    for e in full_data:
        d = e.get("difficulty", "unrated")
        if d in {"easy", "medium", "unrated"}:
            bands["easy_med"].append(e)
        elif d == "hard":
            bands["hard"].append(e)
        elif d in {"very_hard", "extreme"}:
            bands["very_hard_plus"].append(e)
    out = []
    for band in ("easy_med", "hard", "very_hard_plus"):
        pool = bands[band]
        rng.shuffle(pool)
        out.extend(pool[:n_per_band])
    return out


# Back-compat alias for older callers
def sample_calibration_30(full_data: list, seed: int = 12345) -> list:
    return sample_calibration(full_data, n_per_band=10, seed=seed)


def _resolve_provider(model_cfg: dict) -> tuple[str, str] | None:
    """Map a model_cfg → (provider, model_id) for MultiModelGenerator.

    Returns None if the env isn't ready (key missing / wrong backend), so
    the caller can fall back to mock for THIS model only.
    """
    access  = model_cfg.get("access")
    backend = model_cfg.get("backend")
    if access == "api" and backend == "google":
        key_var = model_cfg.get("api_env_var", "GOOGLE_API_KEY")
        if not (os.getenv(key_var) or os.getenv("GEMINI_API_KEY")):
            return None
        return ("google", model_cfg["api_model_id"])
    if access == "local":
        # Caller is responsible for `vllm serve <hf_repo>` on $vllm_port.
        port = model_cfg.get("vllm_port", 8000)
        os.environ["OPENAI_API_BASE"] = f"http://localhost:{port}/v1"
        os.environ["OPENAI_API_KEY"]  = "EMPTY"
        return ("local", model_cfg["hf_repo"])
    return None


def run_one_model(model_cfg: dict, tasks: list, out_jsonl: Path,
                  guard=None) -> dict:
    """Run a single model on the calibration set.

    For each task, calls multi_model_runner.run_debug_session and records:
      - parse_ok       — runner produced ≥1 attempt with extracted code
      - empty_blame    — every attempt's blame_spans was empty
      - code_ok        — final candidate parses as Python
      - timeout        — sandbox subprocess timed out
      - input_tokens / output_tokens — sum across all turns
      - latency_s      — wall-clock for this task

    Falls back to _mock_summary if:
      (a) multi_model_runner can't be imported, or
      (b) provider env isn't ready (e.g. GOOGLE_API_KEY missing).
    """
    import ast as _ast

    resolved = _resolve_provider(model_cfg)
    try:
        import multi_model_runner as mmr
    except Exception as e:
        print(f"  ⚠ multi_model_runner import failed ({e}); using mock", file=sys.stderr)
        return _mock_summary(model_cfg, tasks, out_jsonl)
    if resolved is None:
        print(f"  ⚠ {model_cfg['id']}: provider env not ready; using mock", file=sys.stderr)
        return _mock_summary(model_cfg, tasks, out_jsonl)

    provider, model_id = resolved
    raw_rows = []
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w") as fh:
        for i, t in enumerate(tasks):
            if guard is not None and guard.should_stop():
                print(f"  ⚠ budget cut at task {i}: {guard.reason()}", file=sys.stderr)
                break
            t0 = time.time()
            try:
                pl = mmr.run_debug_session(
                    t,
                    mode="baseline",
                    max_turns=model_cfg.get("t_max", 5),
                    provider=provider,
                    model=model_id,
                    temperature=float(model_cfg.get("temperature", 0.2)),
                )
            except Exception as e:
                print(f"    task {i} {t.get('problem_id')}: runner crashed: {e}",
                      file=sys.stderr)
                continue
            latency = time.time() - t0

            attempts = []
            for sp in pl.get("subproblems", []):
                attempts.extend(sp.get("attempts", []))
            extracted = [a for a in attempts if a.get("generated_code")]
            blame_empty = all(not a.get("blame_spans") for a in attempts) if attempts else True
            timeout = any("timeout" in str(a.get("test_result", "")).lower() for a in attempts)
            code_ok = False
            if extracted:
                try:
                    _ast.parse(extracted[-1]["generated_code"])
                    code_ok = True
                except SyntaxError:
                    code_ok = False
            row = {
                "task_index": i,
                "problem_id": t.get("problem_id"),
                "difficulty": t.get("difficulty"),
                "parse_ok": bool(extracted),
                "empty_blame": blame_empty,
                "code_ok": code_ok,
                "timeout": timeout,
                "input_tokens":  int(pl.get("total_input_tokens", 0)),
                "output_tokens": int(pl.get("total_output_tokens", 0)),
                "latency_s": round(latency, 2),
                "solved": bool(pl.get("solved")),
            }
            raw_rows.append(row)
            fh.write(json.dumps(row) + "\n"); fh.flush()
            if guard is not None and model_cfg.get("access") == "api":
                pin  = model_cfg["pricing"]["input_usd_per_million"]
                pout = model_cfg["pricing"]["output_usd_per_million"]
                guard.add_cost(row["input_tokens"], row["output_tokens"], pin, pout)
            elif guard is not None:
                guard.add_call_no_cost()

    n = max(1, len(raw_rows))
    parse_ok = sum(1 for r in raw_rows if r["parse_ok"])
    timeout  = sum(1 for r in raw_rows if r["timeout"])
    empty    = sum(1 for r in raw_rows if r["empty_blame"])
    code_ok  = sum(1 for r in raw_rows if r["code_ok"])
    avg_in   = sum(r["input_tokens"]  for r in raw_rows) / n
    avg_out  = sum(r["output_tokens"] for r in raw_rows) / n
    avg_lat  = sum(r["latency_s"]     for r in raw_rows) / n
    full_calls = 2402
    if model_cfg.get("access") == "api":
        pin = model_cfg["pricing"]["input_usd_per_million"]
        pout = model_cfg["pricing"]["output_usd_per_million"]
        proj_usd = (full_calls * avg_in * pin + full_calls * avg_out * pout) / 1e6
    else:
        proj_usd = 0.0
    return {
        "model": model_cfg["id"],
        "n_tasks": len(raw_rows),
        "parse_ok_rate": parse_ok / n,
        "empty_blame_rate": empty / n,
        "invalid_code_rate": 1 - code_ok / n,
        "timeout_rate": timeout / n,
        "avg_input_tokens": avg_in,
        "avg_output_tokens": avg_out,
        "avg_latency_s": avg_lat,
        "projected_full_cost_usd": round(proj_usd, 2),
        "_mock": False,
    }


def _mock_summary(model_cfg: dict, tasks: list, out_jsonl: Path) -> dict:
    """Synthetic placeholder when runner not importable (development)."""
    # 30 mock per-task entries
    raw_rows = []
    for i, t in enumerate(tasks):
        raw_rows.append({
            "task_index": i,
            "problem_id": t.get("problem_id"),
            "difficulty": t.get("difficulty"),
            "parse_ok": (i % 30) > 1,
            "empty_blame": (i % 30) <= 1,
            "code_ok": True,
            "timeout": False,
            "input_tokens": 7200,
            "output_tokens": 1900,
            "latency_s": 8.0 + 2 * (i % 4),
        })
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w") as fh:
        for r in raw_rows:
            fh.write(json.dumps(r) + "\n")
    n = len(raw_rows)
    parse_ok = sum(1 for r in raw_rows if r["parse_ok"])
    timeout  = sum(1 for r in raw_rows if r["timeout"])
    empty    = sum(1 for r in raw_rows if r["empty_blame"])
    code_ok  = sum(1 for r in raw_rows if r["code_ok"])
    avg_in   = sum(r["input_tokens"]  for r in raw_rows) / n
    avg_out  = sum(r["output_tokens"] for r in raw_rows) / n
    avg_lat  = sum(r["latency_s"]     for r in raw_rows) / n
    # Project to Full
    full_calls = 2402  # from pipeline.yaml splits.full.n_turn_rounds
    if model_cfg.get("access") == "api":
        pin = model_cfg["pricing"]["input_usd_per_million"]
        pout = model_cfg["pricing"]["output_usd_per_million"]
        proj_usd = (full_calls * avg_in * pin + full_calls * avg_out * pout) / 1e6
    else:
        proj_usd = 0.0
    return {
        "model": model_cfg["id"],
        "n_tasks": n,
        "parse_ok_rate": parse_ok / n,
        "empty_blame_rate": empty / n,
        "invalid_code_rate": 1 - code_ok / n,
        "timeout_rate": timeout / n,
        "avg_input_tokens": avg_in,
        "avg_output_tokens": avg_out,
        "avg_latency_s": avg_lat,
        "projected_full_cost_usd": round(proj_usd, 2),
        "_mock": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="pipeline.yaml")
    ap.add_argument("--output-dir", default="out/dry_run/")
    ap.add_argument("--n-per-band", type=int, default=4,
                    help="Tasks per difficulty band (default 4 → 12 total per model)")
    ap.add_argument("--max-wall-clock-minutes", type=int, default=55,
                    help="Hard cap on total wall-clock for the dry-run (default 55min, "
                         "leaving 5min headroom under the 1-hour goal)")
    ap.add_argument("--max-usd", type=float, default=5.0,
                    help="API spend cap for the whole dry-run")
    ap.add_argument("--mock-only", action="store_true",
                    help="Skip real LLM calls; useful for testing the pipeline.")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "code" / "src"))
    from core.budget import BudgetGuard

    cfg = yaml.safe_load(open(args.config))
    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)

    guard = BudgetGuard(
        max_wall_clock_seconds=args.max_wall_clock_minutes * 60,
        max_usd=args.max_usd,
        persist_path=out_dir / "_budget_state.json",
    )
    guard.start()
    print(f"BudgetGuard initialized: max_clock={args.max_wall_clock_minutes}min, max_usd=${args.max_usd}")

    # Load Full + sample stratified tasks
    full = json.load(open(REPO_ROOT / "data" / "tracebench_full.json"))
    tasks = sample_calibration(full, n_per_band=args.n_per_band,
                                seed=cfg["defaults"]["seed"])
    print(f"Calibration set: {len(tasks)} problems "
          f"({sum(1 for t in tasks if t['difficulty'] in ('easy','medium','unrated'))}/"
          f"{sum(1 for t in tasks if t['difficulty']=='hard')}/"
          f"{sum(1 for t in tasks if t['difficulty'] in ('very_hard','extreme'))})")

    summaries = []
    for m in cfg["models"]:
        if guard.should_stop():
            print(f"\n!! BUDGET CUT: {guard.reason()}  (stopping before {m['id']})")
            break

        mcfg = yaml.safe_load(open(REPO_ROOT / m["config"]))
        out_jsonl = out_dir / f"{m['id']}_calibration.jsonl"
        print(f"\nRunning {m['id']} on {len(tasks)}-task pilot... "
              f"({guard})")
        t0 = time.time()
        if args.mock_only:
            summary = _mock_summary(mcfg, tasks, out_jsonl)
        else:
            # run_one_model now drives multi_model_runner per task and
            # charges per-call into `guard` itself; it falls back to
            # _mock_summary internally if provider env isn't ready
            # (e.g. local vLLM not up, or GOOGLE_API_KEY missing).
            summary = run_one_model(mcfg, tasks, out_jsonl, guard=guard)
        summary["wall_clock_s"] = round(time.time() - t0, 1)
        summaries.append(summary)

        # If we landed in mock for any reason, the guard wasn't charged —
        # do a one-shot accounting so the report's running tally is honest.
        if summary.get("_mock"):
            if mcfg.get("access") == "api":
                avg_in = summary.get("avg_input_tokens", 0)
                avg_out = summary.get("avg_output_tokens", 0)
                n = summary.get("n_tasks", 0)
                pin  = mcfg["pricing"]["input_usd_per_million"]
                pout = mcfg["pricing"]["output_usd_per_million"]
                guard.add_cost(n * avg_in, n * avg_out, pin, pout)
            else:
                for _ in range(summary.get("n_tasks", 0)):
                    guard.add_call_no_cost()

    # Write summary CSV
    csv_path = out_dir / "calibration_summary.csv"
    with csv_path.open("w", newline="") as fh:
        cols = ["model", "n_tasks", "parse_ok_rate", "empty_blame_rate",
                "invalid_code_rate", "timeout_rate", "avg_input_tokens",
                "avg_output_tokens", "avg_latency_s",
                "projected_full_cost_usd", "wall_clock_s"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(summaries)
    print(f"\nwrote {csv_path}")

    # Write human-readable report
    md = ["# Day-0 Calibration Report", ""]
    md.append("| Model | Parse OK | Empty blame | Code OK | Timeout | Avg latency | Proj. Full $ |")
    md.append("|-------|---------:|------------:|--------:|--------:|------------:|-------------:|")
    for s in summaries:
        md.append(f"| {s['model']} | {s['parse_ok_rate']:.0%} | "
                  f"{s['empty_blame_rate']:.0%} | {1 - s['invalid_code_rate']:.0%} | "
                  f"{s['timeout_rate']:.0%} | {s['avg_latency_s']:.1f}s | "
                  f"${s['projected_full_cost_usd']:.2f} |")
    md.append("")
    md.append("## Gate check")
    md.append("Block `make eval` if any of the following are TRUE:")
    md.append("- parse_ok < 80% on any model")
    md.append("- projected_full_cost > $250 for Gemini")
    md.append("- timeout_rate > 20% on any model")
    md_path = out_dir / "calibration_report.md"
    md_path.write_text("\n".join(md))
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
