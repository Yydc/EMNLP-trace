#!/usr/bin/env python3
"""Run one Stage-2 eval cell.

Handles both access types end-to-end:
  - local:  start `vllm serve` as a subprocess, wait for /v1/models, run
            02_run_evaluation.py, then kill the vllm process group.
  - api:    just verify the API key env var is set, then run
            02_run_evaluation.py.

Pulls all knobs (local_path, vllm_port, max_model_len, gpu_memory_utilization,
served-model-name=hf_repo) from code/configs/models/<id>.yaml. Designed to be
called per-model from the Makefile or a top-level loop so failures are
isolated per cell.

Usage:
    scripts/run_cell.py <model_id> [--limit N] [--max-usd U] [--max-wall-clock-hours H]
"""
from __future__ import annotations
import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
VLLM_BIN  = os.environ.get("VLLM_BIN", "/data2/yix/conda-envs/aime26/bin/vllm")
VLLM_READY_TIMEOUT_S = int(os.environ.get("VLLM_READY_TIMEOUT_S", "900"))   # 15 min cold load ceiling
VLLM_KILL_GRACE_S    = int(os.environ.get("VLLM_KILL_GRACE_S", "30"))


def _load_model_cfg(model_id: str) -> tuple[dict, dict]:
    pipeline = yaml.safe_load(open(REPO_ROOT / "pipeline.yaml"))
    entry = next((m for m in pipeline["models"] if m["id"] == model_id), None)
    if entry is None:
        sys.exit(f"model id {model_id!r} not in pipeline.yaml")
    model_cfg = yaml.safe_load(open(REPO_ROOT / entry["config"]))
    return entry, model_cfg


def _wait_for_vllm(port: int, timeout_s: int) -> None:
    url = f"http://localhost:{port}/v1/models"
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    print(f"  vllm READY at {url} after {int(time.time() - (deadline - timeout_s))}s")
                    return
        except (urllib.error.URLError, ConnectionResetError, OSError) as e:
            last_err = e
        time.sleep(3)
    raise RuntimeError(f"vllm at :{port} not ready within {timeout_s}s; last err: {last_err}")


def _start_vllm(model_cfg: dict) -> subprocess.Popen:
    local_path = model_cfg.get("local_path")
    served_name = model_cfg["hf_repo"]
    port = int(model_cfg.get("vllm_port", 8000))
    gpu_util = float(model_cfg.get("gpu_memory_utilization", 0.9))
    max_len = int(model_cfg.get("max_model_len", 8192))

    if not local_path or not Path(local_path).is_dir():
        sys.exit(f"local_path missing or not a dir: {local_path!r}")

    cmd = [
        VLLM_BIN, "serve", local_path,
        "--served-model-name", served_name,
        "--port", str(port),
        "--gpu-memory-utilization", str(gpu_util),
        "--max-model-len", str(max_len),
    ]
    log_path = REPO_ROOT / "out" / "vllm_logs" / f"{model_cfg['id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a")
    log_fh.write(f"\n===== START {time.strftime('%Y-%m-%d %H:%M:%S')} cmd={' '.join(cmd)} =====\n")
    log_fh.flush()
    print(f"  spawning: {' '.join(cmd)}")
    # Inherit env but ensure (a) the conda env's bin/ (ninja, etc.) is on PATH
    # and (b) CUDA_HOME points at a real toolkit. flashinfer's JIT kernel
    # compile hardcodes "$CUDA_HOME/bin/nvcc" in the cached build.ninja files;
    # if CUDA_HOME isn't set or points at /usr/local/cuda (a missing symlink
    # on this box), nvcc returns 127 and the engine refuses requests.
    env = os.environ.copy()
    vllm_bin_dir = str(Path(VLLM_BIN).parent)
    env["PATH"] = f"{vllm_bin_dir}:{env.get('PATH', '')}"
    cuda_home = env.get("CUDA_HOME") or env.get("CUDA_PATH")
    if not cuda_home or not (Path(cuda_home) / "bin" / "nvcc").is_file():
        for cand in ("/usr/local/cuda", "/usr/local/cuda-12.4", "/usr/local/cuda-12.6"):
            if (Path(cand) / "bin" / "nvcc").is_file():
                env["CUDA_HOME"] = cand
                env["CUDA_PATH"] = cand
                env["PATH"] = f"{cand}/bin:{env['PATH']}"
                print(f"  CUDA_HOME={cand}")
                break
        else:
            print("  WARNING: no nvcc found in standard locations; JIT kernels will fail")
    # Parallelize ninja-driven flashinfer JIT compile (default is serial = ~9h for 35 kernels).
    env.setdefault("MAX_JOBS", os.environ.get("MAX_JOBS", "32"))
    proc = subprocess.Popen(
        cmd, stdout=log_fh, stderr=subprocess.STDOUT, start_new_session=True, env=env
    )
    return proc


def _kill_vllm(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    pgid = os.getpgid(proc.pid)
    print(f"  SIGTERM pgid={pgid}")
    os.killpg(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=VLLM_KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        print(f"  SIGKILL pgid={pgid} (didn't exit in {VLLM_KILL_GRACE_S}s)")
        os.killpg(pgid, signal.SIGKILL)
        proc.wait()


def _run_evaluation(model_id: str, extra_args: list[str]) -> int:
    py = sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT/'code'/'src'}:{REPO_ROOT/'code'}"
    cmd = [
        py, str(REPO_ROOT / "code" / "scripts" / "02_run_evaluation.py"),
        "--config", str(REPO_ROOT / "pipeline.yaml"),
        "--model", model_id,
        "--split", "full",
        *extra_args,
    ]
    print(f"  exec: {' '.join(cmd)}")
    return subprocess.call(cmd, env=env, cwd=REPO_ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_id")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-usd", type=float, default=None)
    ap.add_argument("--max-wall-clock-hours", type=float, default=None)
    args = ap.parse_args()

    pipeline_entry, model_cfg = _load_model_cfg(args.model_id)
    print(f"=== cell start: {args.model_id} access={pipeline_entry['access']} ===")

    extra = []
    if args.limit is not None:                 extra += ["--limit", str(args.limit)]
    if args.max_usd is not None:               extra += ["--max-usd", str(args.max_usd)]
    if args.max_wall_clock_hours is not None:  extra += ["--max-wall-clock-hours", str(args.max_wall_clock_hours)]

    vllm_proc: subprocess.Popen | None = None
    rc = 1
    try:
        if pipeline_entry["access"] == "local":
            vllm_proc = _start_vllm(model_cfg)
            _wait_for_vllm(int(model_cfg.get("vllm_port", 8000)), VLLM_READY_TIMEOUT_S)
        elif pipeline_entry["access"] == "api":
            key_var = model_cfg.get("api_env_var", "GOOGLE_API_KEY")
            if not os.environ.get(key_var):
                sys.exit(f"required env {key_var} not set")
        rc = _run_evaluation(args.model_id, extra)
        print(f"=== cell end: {args.model_id} exit={rc} ===")
    finally:
        if vllm_proc is not None:
            _kill_vllm(vllm_proc)
            # Give CUDA a beat to release VRAM before next cell starts.
            time.sleep(5)
    return rc


if __name__ == "__main__":
    sys.exit(main())
