#!/usr/bin/env python3
"""统一的数据生成CLI接口

合并single-file和multi-file数据生成逻辑。
"""

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

from src.core.dataset_loader import load_dataset_auto, load_from_local
from src.core.adversarial_generator import generate_two_stage_adversarial_dataset
from src.core.multifile_converter import convert_to_multifile_problem
from src.core.tracebench_generator import TraceBenchGenerator
from src.core import config


def parse_args():
    parser = argparse.ArgumentParser(description="生成评测数据集（single-file或multi-file）")
    parser.add_argument("--mode", type=str, choices=["single", "multi"], required=True,
                       help="数据集模式: single (single-file) 或 multi (multi-file)")
    parser.add_argument("--format", type=str, choices=["standard", "tracebench"], default="standard",
                       help="输出格式: standard (LLM+规则) 或 tracebench (AST注入+验证)")
    parser.add_argument("--num-problems", type=int, default=10,
                       help="要生成的问题数量 (默认: 10)")
    parser.add_argument("--difficulty", type=str,
                       choices=["easy", "medium", "hard", "extreme", "mixed"],
                       default="extreme", help="对抗数据难度 (默认: extreme)")
    parser.add_argument("--output-dir", type=str,
                       default="output/generated_{mode}",
                       help="输出目录 (默认: output/generated_single 或 output/generated_multi)")
    parser.add_argument("--validate", action="store_true",
                       help="开启验证模式（仅TraceBench）- 过滤无效注入")
    parser.add_argument("--api-key", type=str, default=None,
                       help="Together API key (默认: 从环境变量TOGETHER_API_KEY读取)")
    parser.add_argument("--api-url", type=str,
                       default="https://api.together.xyz/v1",
                       help="API URL (默认: https://api.together.xyz/v1)")
    parser.add_argument("--generation-model", type=str,
                       default="Qwen/Qwen2.5-Coder-32B-Instruct",
                       help="LLM模型名称")
    parser.add_argument("--use-huggingface", action="store_true",
                       help="从HuggingFace加载数据集")
    parser.add_argument("--hf-dataset", type=str,
                       default="WaterWang-001/CodeFlowBench-2505",
                       help="HuggingFace数据集名称")
    parser.add_argument("--hf-split", type=str, default="train",
                       help="HuggingFace数据集split")
    parser.add_argument("--input", type=str, default=config.INPUT_DATASET,
                       help="本地输入文件路径")
    parser.add_argument("--random-order", action="store_true",
                       help="随机打乱问题顺序")
    parser.add_argument("--seed", type=int, default=42,
                       help="随机种子 (默认: 42)")
    return parser.parse_args()


def load_and_select(input_path, use_huggingface, hf_dataset, hf_split,
                    num_problems, random_order, seed):
    """加载并选择指定数量的问题"""
    if use_huggingface:
        print(f"从HuggingFace加载: {hf_dataset} (split={hf_split})")
        problems = load_dataset_auto(
            source="huggingface",
            dataset_name=hf_dataset,
            split=hf_split,
            num_problems=None,
        )
    else:
        print(f"从本地文件加载: {input_path}")
        problems = load_from_local(file_path=input_path)

    if random_order:
        rng = random.Random(seed)
        rng.shuffle(problems)

    return problems[:num_problems]


def generate_single_file_dataset(args, problems, output_dir):
    """生成single-file数据集"""
    print(f"\n[Single-file模式 - 格式: {args.format}]")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    baseline_path = output_dir / f"baseline_{timestamp}_{args.num_problems}p.json"
    baseline_path.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Baseline保存到: {baseline_path}")

    # TraceBench模式 - 使用AST注入
    if args.format == "tracebench":
        print("\n[TraceBench模式] 使用AST代码注入...")

        # 映射difficulty到TraceBench难度
        difficulty_map = {
            "easy": "single_single",
            "medium": "single_single",
            "hard": "single_multi",
            "extreme": "multi_multi",
            "mixed": "multi_multi",
        }
        tb_mode = difficulty_map.get(args.difficulty, "single_single")

        generator = TraceBenchGenerator()

        # 生成三种难度的TraceBench数据集
        for mode in ["single_single", "single_multi", "multi_multi"]:
            output_file = output_dir / f"tracebench_{mode}_{timestamp}.json"
            try:
                generator.generate_dataset(
                    input_file=str(baseline_path),
                    output_file=str(output_file),
                    difficulty_mode=mode,
                    num_problems=args.num_problems,
                    split="train",
                    validate=args.validate,
                )
                print(f"✓ TraceBench ({mode}) 保存到: {output_file}")
            except Exception as e:
                print(f"✗ TraceBench ({mode}) 生成失败: {e}")

        return {"tracebench": str(output_dir)}

    # Standard模式 - LLM+规则
    else:
        # 使用配置优先级: CLI参数 > 环境变量 > 默认值
        api_key = config.get_config_value(args.api_key, "TOGETHER_API_KEY", config.API_KEY)
        api_url = config.get_config_value(args.api_url, "TOGETHER_API_BASE", config.API_URL)
        generation_model = config.get_config_value(args.generation_model, "CODEFLOW_GENERATION_MODEL", config.GENERATION_MODEL)

        # 两阶段对抗数据生成
        print("\n生成两阶段对抗数据...")
        results = generate_two_stage_adversarial_dataset(
            input_file=str(baseline_path),
            output_dir=str(output_dir),
            api_key=api_key,
            api_url=api_url,
            model_name=generation_model,
            difficulty=args.difficulty,
            num_datasets=1,
        )

        print(f"\n✓ LLM版本保存到: {output_dir}/LLM/")
        print(f"✓ LLM+版本保存到: {output_dir}/LLM+/")
        return results


def generate_multi_file_dataset(args, problems, output_dir):
    """生成multi-file数据集"""
    print(f"\n[Multi-file模式]")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. 生成baseline (single-file格式)
    baseline_path = output_dir / f"baseline_{timestamp}_{args.num_problems}p.json"
    baseline_path.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Baseline保存到: {baseline_path}")

    # 2. 使用配置优先级
    api_key = config.get_config_value(args.api_key, "TOGETHER_API_KEY", config.API_KEY)
    api_url = config.get_config_value(args.api_url, "TOGETHER_API_BASE", config.API_URL)
    generation_model = config.get_config_value(args.generation_model, "CODEFLOW_GENERATION_MODEL", config.GENERATION_MODEL)

    # 3. 生成LLM和LLM+版本（single-file格式）
    print("\n生成两阶段对抗数据...")
    temp_output = output_dir / "temp_singlefile"
    temp_output.mkdir(parents=True, exist_ok=True)

    results = generate_two_stage_adversarial_dataset(
        input_file=str(baseline_path),
        output_dir=str(temp_output),
        api_key=api_key,
        api_url=api_url,
        model_name=generation_model,
        difficulty=args.difficulty,
        num_datasets=1,
    )

    # 4. 转换为multi-file格式
    print("\n转换为multi-file格式...")
    for version_name in ["LLM", "LLM+"]:
        version_dir = output_dir / version_name
        version_dir.mkdir(parents=True, exist_ok=True)

        # 查找对应版本的文件
        temp_version_dir = temp_output / version_name
        if temp_version_dir.exists():
            for singlefile_json in temp_version_dir.glob("*.json"):
                print(f"  转换 {singlefile_json.name} -> multi-file")

                with open(singlefile_json, "r", encoding="utf-8") as f:
                    singlefile_data = json.load(f)

                # 转换每个问题为multi-file格式
                multifile_data = []
                for problem in singlefile_data:
                    multifile_problem = convert_to_multifile_problem(
                        problem,
                        difficulty=args.difficulty
                    )
                    multifile_data.append(multifile_problem)

                # 保存multi-file版本
                output_filename = singlefile_json.name.replace(".json", "_multifile.json")
                output_path = version_dir / output_filename
                output_path.write_text(
                    json.dumps(multifile_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"    ✓ 保存到: {output_path}")

    # 5. 清理临时文件
    import shutil
    shutil.rmtree(temp_output)

    print(f"\n✓ LLM版本保存到: {output_dir}/LLM/")
    print(f"✓ LLM+版本保存到: {output_dir}/LLM+/")
    return results


def main():
    args = parse_args()

    # 解析输出目录
    if "{mode}" in args.output_dir:
        mode_name = "singlefile" if args.mode == "single" else "multifile"
        args.output_dir = args.output_dir.format(mode=mode_name)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 处理输入路径
    input_path = Path(args.input).resolve() if args.input else None
    if input_path and not args.use_huggingface and not input_path.exists():
        raise FileNotFoundError(f"输入数据集不存在: {input_path}")

    # 加载数据
    print("=" * 70)
    print("CodeFlow 数据生成工具")
    print("=" * 70)
    print(f"模式: {args.mode}")
    print(f"问题数量: {args.num_problems}")
    print(f"难度: {args.difficulty}")
    print(f"输出目录: {output_dir}")
    print("=" * 70)

    problems = load_and_select(
        input_path,
        args.use_huggingface,
        args.hf_dataset,
        args.hf_split,
        args.num_problems,
        args.random_order,
        args.seed
    )

    # 根据模式生成数据
    if args.mode == "single":
        generate_single_file_dataset(args, problems, output_dir)
    else:
        generate_multi_file_dataset(args, problems, output_dir)

    print("\n" + "=" * 70)
    print("✓ 数据生成完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
