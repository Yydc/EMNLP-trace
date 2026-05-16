#!/usr/bin/env python3
"""Warm up flashinfer JIT kernel cache for every local model.

First-time `vllm serve` for Qwen3.5/Qwen3.6/GLM-4.7/DeepSeek-R1 has to
JIT-compile flashinfer's GDN (Gated Delta Network) kernels with nvcc, which
takes 30-60 min per model with MAX_JOBS=32 (was ~9h serial). After the cache
is warm at /home/yix/.cache/flashinfer, subsequent `vllm serve` cold-starts
in a couple minutes.

This script: for each local model in pipeline.yaml (in order), start
`vllm serve`, watch the log for "Application startup complete" → kill it,
move on. Cache persists between cells.

Run from repo root: `scripts/warmup_local.py [model_id ...]`
"""
from __future__ import annotations
import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
VLLM_BIN  = "/data2/yix/conda-envs/aime26/bin/vllm"
CUDA_HOME = "/usr/local/cuda-12.4"
MAX_JOBS  = os.environ.get("MAX_JOBS", "32")
READY_RE  = re.compile(r"Application startup complete")
FAIL_RE   = re.compile(r"AssertionError|OutOfMemoryError|RuntimeError: CUDA error|Killed")
WARMUP_TIMEOUT_S = int(os.environ.get("WARMUP_TIMEOUT_S", "7200"))   # 2 h ceiling per model


def warmup_one(model_id: str) -> tuple[bool, float, str]:
    pipeline = yaml.safe_load(open(REPO_ROOT / "pipeline.yaml"))
    entry = next((m for m in pipeline["models"] if m["id"] == model_id), None)
    if entry is None or entry.get("access") != "local":
        return False, 0.0, "not a local model in pipeline.yaml"
    model_cfg = yaml.safe_load(open(REPO_ROOT / entry["config"]))
    local_path = model_cfg.get("local_path")
    served_name = model_cfg["hf_repo"]
    port = int(model_cfg.get("vllm_port", 8000))
    gpu_util = float(model_cfg.get("gpu_memory_utilization", 0.9))
    max_len = int(model_cfg.get("max_model_len", 8192))

    log_path = REPO_ROOT / "out" / "vllm_logs" / f"warmup_{model_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w")

    env = os.environ.copy()
    env["CUDA_HOME"] = CUDA_HOME
    env["CUDA_PATH"] = CUDA_HOME
    env["MAX_JOBS"]  = MAX_JOBS
    env["PATH"] = f"{CUDA_HOME}/bin:{Path(VLLM_BIN).parent}:{env.get('PATH','')}"

    cmd = [
        VLLM_BIN, "serve", local_path,
        "--served-model-name", served_name,
        "--port", str(port),
        "--gpu-memory-utilization", str(gpu_util),
        "--max-model-len", str(max_len),
        "--enable-prefix-caching",
    ]
    print(f"\n===== WARMUP {model_id} pid_about_to_spawn =====", flush=True)
    print(f"  cmd: {' '.join(cmd)}", flush=True)
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT,
                            start_new_session=True, env=env)
    print(f"  vllm pid={proc.pid} pgid={os.getpgid(proc.pid)}", flush=True)

    ready = False
    msg = "timeout"
    # Tail the log file from the start.
    deadline = t0 + WARMUP_TIMEOUT_S
    last_size = 0
    while time.time() < deadline:
        if proc.poll() is not None:
            msg = f"vllm exited unexpectedly (rc={proc.returncode})"
            break
        # Check log for ready / fatal
        try:
            cur_size = log_path.stat().st_size
        except FileNotFoundError:
            cur_size = 0
        if cur_size > last_size:
            with open(log_path, "rb") as fh:
                fh.seek(last_size)
                chunk = fh.read(cur_size - last_size).decode("utf-8", "replace")
            last_size = cur_size
            if READY_RE.search(chunk):
                ready = True
                msg = "ready"
                break
            if FAIL_RE.search(chunk):
                msg = "fatal-pattern-in-log"
                break
        time.sleep(5)

    elapsed = time.time() - t0
    print(f"  signal: SIGTERM pgid={os.getpgid(proc.pid)}", flush=True)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=30)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=10)
        except Exception:
            pass
    # Give CUDA a beat to release VRAM
    time.sleep(8)
    print(f"===== {model_id} ready={ready} elapsed={elapsed:.0f}s msg={msg} =====", flush=True)
    return ready, elapsed, msg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*",
                    help="model ids; default = all local models in pipeline.yaml")
    args = ap.parse_args()

    pipeline = yaml.safe_load(open(REPO_ROOT / "pipeline.yaml"))
    all_local = [m["id"] for m in pipeline["models"] if m.get("access") == "local"]
    targets = args.models or all_local
    print(f"warming up: {targets}")

    results = []
    for mid in targets:
        ready, elapsed, msg = warmup_one(mid)
        results.append((mid, ready, elapsed, msg))

    print("\n===== WARMUP SUMMARY =====")
    for mid, ready, elapsed, msg in results:
        flag = "OK" if ready else "FAIL"
        print(f"  {flag:>4}  {mid:<22}  {elapsed:>6.0f}s  {msg}")
    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
