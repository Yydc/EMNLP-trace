#!/usr/bin/env python3
"""Stage 2 wrapper: run one (model, split) evaluation cell.

Reads the model config from pipeline.yaml (via --config + --model),
launches the appropriate runner (local vLLM or Gemini API), writes the
per-problem records jsonl + summary json.

Resumable: if the checkpoint jsonl already has records for problem_ids,
they are skipped.

Outputs (per cell):
    out/checkpoints/<model>_<split>.jsonl       — resume state
    out/records/<model>_<split>_records.jsonl   — per-problem records
    out/records/<model>_<split>_summary.json    — aggregate metrics
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr); sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))
sys.path.insert(0, str(REPO_ROOT / "code"))   # for tracebench_runner.py at code/


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="pipeline.yaml")
    ap.add_argument("--model", required=True,
                    help="model id (matches an entry in pipeline.yaml `models`)")
    ap.add_argument("--split", required=True, choices=["full"],
                    help="evaluation split; Hard is derived later via slice")
    ap.add_argument("--limit", type=int, default=None,
                    help="(debug) only run the first N problems")
    ap.add_argument("--max-usd", type=float, default=None,
                    help="Hard API spend cap for THIS cell. If exceeded, "
                         "checkpoint is saved and the script exits non-zero.")
    ap.add_argument("--max-wall-clock-hours", type=float, default=None,
                    help="Hard wall-clock cap for THIS cell (hours).")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "code" / "src"))
    from core.budget import BudgetGuard

    cfg = yaml.safe_load(open(args.config))
    model_entry = next((m for m in cfg["models"] if m["id"] == args.model), None)
    if model_entry is None:
        sys.exit(f"model id {args.model!r} not in pipeline.yaml")

    model_cfg = yaml.safe_load(open(REPO_ROOT / model_entry["config"]))

    # Resolve split path: prefer labeled version if present
    labeled = REPO_ROOT / "data" / "derived" / f"tracebench_{args.split}_labeled.json"
    orig    = REPO_ROOT / f"data/tracebench_{args.split}.json"
    src_path = labeled if labeled.exists() else orig
    if not src_path.exists():
        sys.exit(f"data file missing: {src_path}")
    print(f"reading {src_path}")
    data = json.load(open(src_path))
    if args.limit: data = data[: args.limit]

    out_root = REPO_ROOT / cfg["defaults"]["workspace"]
    ckpt_path = out_root / "checkpoints" / f"{args.model}_{args.split}.jsonl"
    rec_path  = out_root / "records"     / f"{args.model}_{args.split}_records.jsonl"
    sum_path  = out_root / "records"     / f"{args.model}_{args.split}_summary.json"
    for p in (ckpt_path, rec_path): p.parent.mkdir(parents=True, exist_ok=True)

    # Resume: collect problem_ids we've already done
    done = set()
    if ckpt_path.exists():
        for line in ckpt_path.open():
            try:
                done.add(json.loads(line).get("problem_id"))
            except Exception:
                pass
        print(f"resumed: {len(done)} problems already in checkpoint")

    # ---- Runner dispatch ----
    # We use multi_model_runner.run_debug_session — it has the only complete
    # multi-provider path (qwen/openai/claude/google/local). The older
    # tracebench_runner.run_debug_session only handles Together + Anthropic.
    print(f"launching runner for {args.model} (access={model_cfg['access']})")
    try:
        import multi_model_runner as mmr
        runner = mmr.run_debug_session
    except Exception as e:
        sys.exit(f"failed to import multi_model_runner: {e}")

    # Per-cell decoding env (read inside MultiModelGenerator._generate_openai
    # for OpenAI-seed reproducibility).
    os.environ["TRACEBENCH_SEED"] = str(model_cfg.get("seed", 12345))

    # Resolve provider + model id, and set provider-specific env vars that
    # MultiModelGenerator._setup_api reads.
    if model_cfg["access"] == "api" and model_cfg["backend"] == "google":
        if not os.getenv(model_cfg["api_env_var"]):
            sys.exit(f"{model_cfg['api_env_var']} not set in env")
        provider_arg = "google"
        model_arg    = model_cfg["api_model_id"]
        # GOOGLE_API_KEY is already in env from the caller.
    elif model_cfg["access"] == "local":
        # Caller is responsible for `vllm serve <repo>` on $vllm_port.
        port = model_cfg.get("vllm_port", 8000)
        os.environ["OPENAI_API_BASE"] = f"http://localhost:{port}/v1"
        os.environ["OPENAI_API_KEY"]  = "EMPTY"
        provider_arg = "local"
        model_arg    = model_cfg["hf_repo"]
        # MultiModelGenerator(provider="local") reads OPENAI_API_BASE +
        # OPENAI_API_KEY and uses the OpenAI-compatible client.
    else:
        sys.exit(f"unsupported model access/backend: "
                 f"{model_cfg.get('access')}/{model_cfg.get('backend')}")

    # ---- Budget guard (per-cell) ----
    # API pricing for this model (0/0 if local)
    pin  = model_cfg.get("pricing", {}).get("input_usd_per_million", 0.0)
    pout = model_cfg.get("pricing", {}).get("output_usd_per_million", 0.0)
    guard = BudgetGuard(
        max_wall_clock_seconds=(args.max_wall_clock_hours or 0) * 3600 or None,
        max_usd=args.max_usd,
        persist_path=out_root / "budget" / f"{args.model}_{args.split}.json",
    )
    guard.start()
    if args.max_usd or args.max_wall_clock_hours:
        print(f"BudgetGuard: max_usd={args.max_usd}, "
              f"max_wall_clock_h={args.max_wall_clock_hours}")

    # ---- Run loop ----
    n_done = len(done)
    t0 = time.time()
    aborted = False
    with rec_path.open("a") as rec_fh, ckpt_path.open("a") as ckpt_fh:
        for i, entry in enumerate(data, 1):
            pid = entry.get("problem_id")
            if pid in done:
                continue

            # Budget check BEFORE each problem
            if guard.should_stop():
                print(f"\n!! BUDGET CUT: {guard.reason()}", file=sys.stderr)
                aborted = True
                break

            try:
                problem_log = runner(
                    entry,
                    mode="baseline",
                    max_turns=model_cfg.get("t_max", 5),
                    provider=provider_arg,
                    model=model_arg,
                    temperature=float(model_cfg.get("temperature", 0.2)),
                )
            except Exception as e:
                print(f"  [{i}] {pid}: runner crashed: {e}", file=sys.stderr)
                continue

            # Charge tokens to guard (best-effort: read from problem_log if runner reports)
            in_tok  = problem_log.get("total_input_tokens", 0)
            out_tok = problem_log.get("total_output_tokens", 0)
            if model_cfg.get("access") == "api":
                guard.add_cost(in_tok, out_tok, pin, pout)
            else:
                guard.add_call_no_cost()

            # Minimal per-problem record
            record = {
                "problem_id": pid,
                "trace_id": entry.get("trace_id"),
                "model": args.model,
                "split": args.split,
                "solved": bool(problem_log.get("solved")),
                "total_turns": problem_log.get("total_turns"),
                "total_attempts": problem_log.get("total_attempts"),
                "turn_results": problem_log.get("turn_results"),
                "total_input_tokens": in_tok,
                "total_output_tokens": out_tok,
            }
            rec_fh.write(json.dumps(record, ensure_ascii=False) + "\n"); rec_fh.flush()
            ckpt_fh.write(json.dumps({"problem_id": pid, "solved": record["solved"]})
                          + "\n"); ckpt_fh.flush()
            n_done += 1
            if n_done % 25 == 0:
                rate = n_done / max(time.time() - t0, 1e-9)
                eta = (len(data) - n_done) / max(rate, 1e-9)
                print(f"  [{n_done}/{len(data)}] rate={rate:.1f}/s  "
                      f"eta={eta/60:.0f}m  {guard}")

    # Summary
    summary = {
        "model": args.model, "split": args.split,
        "n_problems": len(data),
        "n_done": n_done,
        "aborted": aborted,
        "wall_clock_s": round(time.time() - t0, 1),
        "records_path": str(rec_path),
        "budget": guard.summary(),
    }
    sum_path.write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {rec_path}")
    print(f"wrote {sum_path}")
    if aborted:
        print(f"\n!! cell {args.model}_{args.split} ABORTED after {n_done}/{len(data)} problems",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
