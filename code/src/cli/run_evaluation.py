#!/usr/bin/env python3
"""统一的评测CLI接口

运行评测流程。
"""

import argparse
import json
from pathlib import Path
from typing import Optional

from src.core import config
from src.evaluation.pipeline import run_enhanced_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 CodeFlow 评测管线")
    parser.add_argument("--dataset", type=str, required=True, help="数据集 JSON 文件路径")
    parser.add_argument("--dataset-type", choices=["single-file", "multi-file"], required=True, help="数据集类型")
    parser.add_argument("--num-runs", type=int, default=1, help="重复运行次数 (默认: 1)")
    parser.add_argument("--generation-model", type=str, default=None, help="对抗数据生成模型（默认读取配置）")
    parser.add_argument("--inference-model", type=str, default=None, help="推理模型（默认读取配置）")
    parser.add_argument("--multifile-difficulty", type=str, default=None, help="多文件数据集难度标签（默认读取配置）")
    parser.add_argument("--skip-adversarial", action="store_true", help="仅评测 baseline，跳过对抗数据生成")
    parser.add_argument("--output-dir", type=str, default=None, help="评测输出目录（默认读取配置）")
    parser.add_argument("--output-tag", type=str, default=None, help="自定义输出标签")
    parser.add_argument("--api-key", type=str, default=None, help="Together API key（默认读取配置/环境）")
    parser.add_argument("--api-url", type=str, default=None, help="Together API 地址（默认读取配置）")
    parser.add_argument("--num-problems", type=int, default=None, help="评测题目数量（默认使用数据集中题目数）")
    return parser.parse_args()


def _infer_problem_count(dataset_path: Path) -> int:
    with dataset_path.open("r", encoding="utf-8") as fin:
        data = json.load(fin)
    if not isinstance(data, list):
        raise ValueError("数据集文件必须是问题列表 JSON")
    return len(data)


def _override_config(api_key: Optional[str], api_url: Optional[str], output_dir: Optional[str]) -> None:
    if api_key is not None:
        config.API_KEY = api_key
    if api_url is not None:
        config.API_URL = api_url
    if output_dir is not None:
        resolved = str(Path(output_dir).resolve())
        config.OUTPUT_DIR = resolved
        config.ensure_output_dir()


def main() -> None:
    args = parse_args()

    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"数据集不存在: {dataset_path}")

    generation_model = args.generation_model or config.GENERATION_MODEL
    inference_model = args.inference_model or config.INFERENCE_MODEL
    multifile_difficulty = args.multifile_difficulty or config.MULTIFILE_DIFFICULTY
    num_problems = args.num_problems or _infer_problem_count(dataset_path)

    _override_config(args.api_key, args.api_url, args.output_dir)

    print("=" * 80)
    print("CodeFlow 评测工具")
    print("=" * 80)
    print(f"数据集: {dataset_path}")
    print(f"类型: {args.dataset_type}")
    print(f"题目数量: {num_problems}")
    print(f"运行次数: {args.num_runs}")
    print(f"推理模型: {inference_model}")
    print(f"生成模型: {generation_model}")
    if args.dataset_type == "multi-file":
        print(f"Multi-file 难度: {multifile_difficulty}")
    if args.skip_adversarial:
        print("对抗生成: 已跳过 (baseline-only)")
    if args.output_dir:
        print(f"输出目录: {Path(args.output_dir).resolve()}")
    print("=" * 80)

    config.DATA_SOURCE = "local"
    config.INPUT_DATASET = str(dataset_path)

    run_enhanced_pipeline(
        generation_model=generation_model,
        inference_model=inference_model,
        dataset_type=args.dataset_type,
        multifile_difficulty=multifile_difficulty,
        num_problems=num_problems,
        num_runs=args.num_runs,
        dataset_path=str(dataset_path),
        output_tag=args.output_tag,
        skip_adversarial=args.skip_adversarial,
    )

    print("\n" + "=" * 80)
    print("✓ 评测完成！")
    print("=" * 80)


if __name__ == "__main__":
    main()
