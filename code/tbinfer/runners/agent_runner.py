from __future__ import annotations
import pathlib, subprocess, shlex, os, sys, json, time
from typing import List

def run_task_with_agent(task_dir: pathlib.Path, agent_cmd: str, profile_path: str, out_dir: pathlib.Path, max_turns: int = 10):
    """
    用 tracebench 引擎 + 指定 agent 命令跑单个任务。
    返回该 run 的 artifacts 目录路径。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "tracebench.cli", "run",
        "--task-dir", str(task_dir),
        "--agent-cmd", agent_cmd,
        "--profile", profile_path,
        "--workspace", str(out_dir / ".workspace"),
        "--out", str(out_dir),
        "--max-turns", str(max_turns),
    ]
    proc = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"Run failed for {task_dir}")
    return out_dir

def run_glob(tasks_root: str, agent: str, profile: str, out_root: str, max_turns: int = 10):
    """
    批量运行：tasks_root 下每个包含 task.json 的目录视为一个任务。
    agent: ["rule_patch" | "openai_patch" | "<custom shell>"]
    """
    tasks_root = pathlib.Path(tasks_root)
    out_root = pathlib.Path(out_root)
    agent_cmd = {
        "rule_patch": f"{sys.executable} -m tbinfer.agents.rule_patch_agent",
        "openai_patch": f"{sys.executable} -m tbinfer.agents.openai_patch_agent",
    }.get(agent, agent)  # 若传自定义 shell 则直接使用

    for task_json in tasks_root.rglob("task.json"):
        task_dir = task_json.parent
        run_dir = out_root / task_dir.name
        print(f"[tbinfer] Running {task_dir} → {run_dir}")
        run_task_with_agent(task_dir, agent_cmd, profile, run_dir, max_turns=max_turns)

def summarize_runs(runs_root: str):
    """
    复用 tracebench 的 evaluator，输出聚合 JSON。
    """
    cmd = [sys.executable, "-m", "tracebench.cli", "eval", "--runs", runs_root]
    proc = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(2)