#!/usr/bin/env python3
"""
多轮交互 TraceBench 冒烟测试
测试 1-2 个样本，验证对话链评测流程是否正常工作
"""

import json
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from tracebench_runner import run_debug_session


def test_multi_turn():
    """测试多轮交互评测"""

    # 加载测试数据
    data_path = Path("output/tracebench.json")
    if not data_path.exists():
        print(f"❌ 测试数据不存在: {data_path}")
        return False

    with open(data_path) as f:
        data = json.load(f)

    if not data:
        print("❌ 测试数据为空")
        return False

    # 找一个多轮交互的样本
    multi_turn_entry = None
    for entry in data:
        if entry.get('multi_turn') and entry.get('meta_data', {}).get('num_injections', 0) > 0:
            multi_turn_entry = entry
            break

    if not multi_turn_entry:
        print("❌ 没有找到多轮交互且有错误注入的样本")
        return False

    trace_id = multi_turn_entry.get('trace_id')
    num_turns = multi_turn_entry.get('meta_data', {}).get('num_turns', 0)
    num_injections = multi_turn_entry.get('meta_data', {}).get('num_injections', 0)

    print("=" * 80)
    print("多轮交互 TraceBench 冒烟测试")
    print("=" * 80)
    print(f"测试样本: {trace_id}")
    print(f"轮次数: {num_turns}")
    print(f"注入错误数: {num_injections}")
    print()

    # 测试 baseline 模式（不使用 LLM，只验证数据结构）
    print("测试 baseline 模式（数据结构验证）...")
    try:
        # 由于没有 API key，我们只能验证数据结构
        # 实际测试需要设置 TOGETHER_API_KEY 环境变量

        # 检查对话历史结构
        conv_history = multi_turn_entry.get('conversation_history', [])
        print(f"✓ 对话历史轮次: {len(conv_history)}")

        for turn in conv_history:
            turn_id = turn.get('turn_id')
            subproblems = turn.get('subproblems', [])
            has_error = turn.get('has_error', False)
            test_count = len(turn.get('test_cases', []))

            print(f"  Turn {turn_id}: {subproblems} - "
                  f"{'有错误' if has_error else '正常'} - "
                  f"{test_count} 个测试")

        print()
        print("✓ 数据结构验证通过")
        print()

        # 如果有 API key，可以进行真实测试
        import os
        if os.getenv('TOGETHER_API_KEY') or os.getenv('ANTHROPIC_API_KEY'):
            print("检测到 API key，进行真实评测...")
            print()

            result = run_debug_session(
                entry=multi_turn_entry,
                mode='baseline',
                enable_adaptive_decoding=False,
                max_turns=3  # 限制每轮尝试次数
            )

            print("评测结果:")
            print(f"  问题ID: {result.get('problem_id')}")
            print(f"  是否解决: {result.get('solved')}")
            print(f"  总轮次: {result.get('total_turns')}")
            print(f"  总尝试次数: {result.get('total_attempts')}")
            print(f"  对话链长度: {result.get('dialogue_chain_length')}")
            print()

            # 打印每轮结果
            for turn_result in result.get('turn_results', []):
                turn_id = turn_result['turn_id']
                solved = turn_result['solved']
                attempts = len(turn_result['attempts'])
                print(f"  Turn {turn_id}: {'✓ 成功' if solved else '✗ 失败'} "
                      f"({attempts} 次尝试)")

            print()
            print("=" * 80)
            print("✅ 冒烟测试完成！")
            print("=" * 80)
        else:
            print("⚠️  未检测到 API key，跳过真实评测")
            print("   设置 TOGETHER_API_KEY 或 ANTHROPIC_API_KEY 环境变量来进行完整测试")
            print()
            print("=" * 80)
            print("✅ 数据结构验证完成！")
            print("=" * 80)

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_multi_turn()
    sys.exit(0 if success else 1)
