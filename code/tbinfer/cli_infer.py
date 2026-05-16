from __future__ import annotations
import argparse, json, sys, pathlib
from tbinfer.runners.agent_runner import run_glob, summarize_runs
from tbinfer.reports.writer import write_markdown

def main():
    p = argparse.ArgumentParser("tbinfer (batch inference + evaluation)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run-batch", help="批量运行任务（多代理/多任务）")
    pr.add_argument("--tasks-root", required=True)
    pr.add_argument("--agent", required=True, help="rule_patch | openai_patch | <custom shell>")
    pr.add_argument("--profile", required=True)
    pr.add_argument("--out", required=True)
    pr.add_argument("--max-turns", type=int, default=10)
    pr.set_defaults(fn=lambda a: run_glob(a.tasks_root, a.agent, a.profile, a.out, a.max_turns))

    ps = sub.add_parser("summarize", help="汇总 runs 结果为 JSON 并生成简单 Markdown")
    ps.add_argument("--runs", required=True)
    ps.add_argument("--md-out", default="REPORT.md")
    def _sum(a):
        # 直接复用 tracebench 的 eval 输出
        import subprocess, sys
        cmd = [sys.executable, "-m", "tracebench.cli", "eval", "--runs", a.runs]
        proc = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            raise SystemExit(2)
        report = proc.stdout
        md_path = write_markdown(json.loads(report), a.md_out)
        print(f"[tbinfer] Markdown written to {md_path}")
    ps.set_defaults(fn=_sum)

    args = p.parse_args()
    args.fn(args)

if __name__ == "__main__":
    main()