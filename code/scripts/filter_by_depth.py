#!/usr/bin/env python3
"""
简化的深度过滤脚本
根据子问题深度过滤 CodeFlow 数据集

用法:
  python scripts/filter_by_depth.py -i data/datav3.json -o output/depth3.json --min-depth 3
  python scripts/filter_by_depth.py -i data/datav3.json -o output/depth3-4.json --min-depth 3 --max-depth 4
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any


def filter_by_depth(
    problems: List[Dict[str, Any]],
    min_depth: int,
    max_depth: int = None
) -> List[Dict[str, Any]]:
    """
    过滤包含指定深度范围子问题的题目

    Args:
        problems: 问题列表
        min_depth: 最小深度（包含）
        max_depth: 最大深度（包含），None 表示不限制

    Returns:
        过滤后的问题列表，每个问题只保留符合深度条件的子问题
    """
    filtered = []

    for prob in problems:
        subproblems = prob.get("subproblems", [])

        # 筛选符合深度条件的子问题
        matching_subs = []
        for sp in subproblems:
            depth = sp.get("depth", 0)
            if depth >= min_depth:
                if max_depth is None or depth <= max_depth:
                    matching_subs.append(sp)

        # 如果有符合条件的子问题，保留这个问题
        if matching_subs:
            prob_copy = dict(prob)
            prob_copy["subproblems"] = matching_subs
            filtered.append(prob_copy)

    return filtered


def print_statistics(original: List[Dict], filtered: List[Dict], min_depth: int, max_depth: int = None):
    """打印过滤统计信息"""

    # 统计原始数据
    orig_probs = len(original)
    orig_subs = sum(len(p.get("subproblems", [])) for p in original)

    # 统计深度分布
    depth_dist = {}
    for p in original:
        for sp in p.get("subproblems", []):
            d = sp.get("depth", 0)
            depth_dist[d] = depth_dist.get(d, 0) + 1

    # 统计过滤后数据
    filt_probs = len(filtered)
    filt_subs = sum(len(p.get("subproblems", [])) for p in filtered)

    # 统计过滤后深度分布
    filt_depth_dist = {}
    for p in filtered:
        for sp in p.get("subproblems", []):
            d = sp.get("depth", 0)
            filt_depth_dist[d] = filt_depth_dist.get(d, 0) + 1

    print("=" * 60)
    print("深度过滤完成")
    print("=" * 60)

    # 原始数据统计
    print(f"原始数据:")
    print(f"  问题数: {orig_probs}")
    print(f"  子问题数: {orig_subs}")
    print(f"  深度分布:")
    for depth in sorted(depth_dist.keys()):
        print(f"    depth {depth}: {depth_dist[depth]} 个子问题")

    print()

    # 过滤条件
    if max_depth is None:
        print(f"过滤条件: depth >= {min_depth}")
    else:
        print(f"过滤条件: {min_depth} <= depth <= {max_depth}")

    print()

    # 过滤后数据统计
    print(f"过滤后数据:")
    print(f"  问题数: {filt_probs} ({filt_probs * 100 / orig_probs:.1f}% 保留)")
    print(f"  子问题数: {filt_subs} ({filt_subs * 100 / orig_subs:.1f}% 保留)")

    if filt_depth_dist:
        print(f"  深度分布:")
        for depth in sorted(filt_depth_dist.keys()):
            print(f"    depth {depth}: {filt_depth_dist[depth]} 个子问题")

    # 警告信息
    if filt_probs == 0:
        print()
        print("⚠️  警告: 没有符合条件的问题！")
    elif filt_probs < 10:
        print()
        print(f"⚠️  警告: 过滤后问题数较少 ({filt_probs})，可能不足以训练模型")
    elif filt_subs < 50:
        print()
        print(f"⚠️  警告: 过滤后子问题数较少 ({filt_subs})，建议降低最小深度或增加数据源")


def main():
    parser = argparse.ArgumentParser(
        description="根据子问题深度过滤 CodeFlow 数据集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 过滤 depth >= 3 的问题
  python scripts/filter_by_depth.py -i data/datav3.json -o output/depth3plus.json --min-depth 3

  # 过滤 depth 4 only
  python scripts/filter_by_depth.py -i data/datav3.json -o output/depth4only.json --min-depth 4 --max-depth 4

  # 过滤 depth 2-3
  python scripts/filter_by_depth.py -i data/datav3.json -o output/depth2-3.json --min-depth 2 --max-depth 3
        """
    )

    parser.add_argument(
        "-i", "--input",
        required=True,
        help="输入 JSON 文件路径"
    )

    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出 JSON 文件路径"
    )

    parser.add_argument(
        "--min-depth",
        type=int,
        required=True,
        help="最小深度（包含）"
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="最大深度（包含），不指定则不限制"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="静默模式，不打印统计信息"
    )

    args = parser.parse_args()

    # 读取输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"✗ 错误: 输入文件不存在: {input_path}")
        return 1

    try:
        with input_path.open("r", encoding="utf-8") as f:
            problems = json.load(f)
    except json.JSONDecodeError as e:
        print(f"✗ 错误: 无法解析 JSON 文件: {e}")
        return 1
    except Exception as e:
        print(f"✗ 错误: 读取文件失败: {e}")
        return 1

    if not isinstance(problems, list):
        print(f"✗ 错误: 输入文件应该是一个 JSON 数组")
        return 1

    # 过滤
    filtered = filter_by_depth(problems, args.min_depth, args.max_depth)

    # 写入输出文件
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"✗ 错误: 写入文件失败: {e}")
        return 1

    # 打印统计信息
    if not args.quiet:
        print_statistics(problems, filtered, args.min_depth, args.max_depth)
        print()
        print(f"✓ 已保存到: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
