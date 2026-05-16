from __future__ import annotations
import argparse, pathlib
from tbgen.generators.function_gen import FunctionGenerator, FunctionGenConfig
from tbgen.generators.flow_gen import FlowGenerator, FlowGenConfig
from tbgen.generators.repo_gen import map_swe_verified

def main():
    p = argparse.ArgumentParser("tbgen (LLM-powered dataset generation)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("function", help="生成函数级任务（LLM）")
    pf.add_argument("--out", required=True)
    pf.add_argument("--n", type=int, default=1)
    pf.set_defaults(fn=lambda a: FunctionGenerator(FunctionGenConfig()).generate_n(a.out, a.n))

    pflow = sub.add_parser("flow", help="生成多函数流程任务（LLM）")
    pflow.add_argument("--out", required=True)
    pflow.add_argument("--n", type=int, default=1)
    pflow.set_defaults(fn=lambda a: FlowGenerator(FlowGenConfig()).generate_n(a.out, a.n))

    pr = sub.add_parser("repo-map", help="从 SWE-verified JSONL 映射为 TraceBench/repo")
    pr.add_argument("--jsonl", required=True)
    pr.add_argument("--out", required=True)
    pr.set_defaults(fn=lambda a: map_swe_verified(a.jsonl, a.out))

    args = p.parse_args()
    args.fn(args)

if __name__ == "__main__":
    main()