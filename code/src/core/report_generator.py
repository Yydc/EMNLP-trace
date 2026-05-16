"""数据集对比报告生成器

用于生成Baseline vs LLM vs LLM+的详细对比报告
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def analyze_dataset(data: List[Dict[str, Any]], dataset_name: str) -> Dict[str, Any]:
    """分析单个数据集的统计信息"""
    total_problems = len(data)
    total_subproblems = sum(len(p.get("subproblems", [])) for p in data)

    # 计算总字符数
    total_chars = 0
    subproblem_lengths = []

    for problem in data:
        for sp in problem.get("subproblems", []):
            stmt = sp.get("statement", "")
            total_chars += len(stmt)
            subproblem_lengths.append(len(stmt))

    avg_chars = total_chars / total_subproblems if total_subproblems > 0 else 0

    # 对抗性信息
    is_adversarial = any(p.get("is_adversarial", False) for p in data)
    adversarial_stages = data[0].get("adversarial_stages", "N/A") if data else "N/A"

    return {
        "name": dataset_name,
        "total_problems": total_problems,
        "total_subproblems": total_subproblems,
        "total_characters": total_chars,
        "avg_chars_per_subproblem": round(avg_chars, 2),
        "min_chars": min(subproblem_lengths) if subproblem_lengths else 0,
        "max_chars": max(subproblem_lengths) if subproblem_lengths else 0,
        "is_adversarial": is_adversarial,
        "adversarial_stages": adversarial_stages,
    }


def generate_comparison_report(
    baseline_path: str,
    llm_path: str,
    llm_plus_path: str,
    output_path: str = None
) -> str:
    """生成三个数据集的对比报告

    Args:
        baseline_path: Baseline数据集路径
        llm_path: LLM重构版本路径
        llm_plus_path: LLM+规则版本路径
        output_path: 报告输出路径（可选）

    Returns:
        报告内容的字符串
    """
    # 加载数据集
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    with open(llm_path, "r", encoding="utf-8") as f:
        llm = json.load(f)

    with open(llm_plus_path, "r", encoding="utf-8") as f:
        llm_plus = json.load(f)

    # 分析每个数据集
    baseline_stats = analyze_dataset(baseline, "Baseline")
    llm_stats = analyze_dataset(llm, "LLM (重构版)")
    llm_plus_stats = analyze_dataset(llm_plus, "LLM+ (重构+规则)")

    # 生成报告
    report_lines = [
        "=" * 80,
        "                    CodeFlow 数据集对比报告",
        "=" * 80,
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 数据集概览",
        "",
    ]

    # 添加统计表格
    report_lines.extend([
        "| 指标 | Baseline | LLM (重构) | LLM+ (重构+规则) |",
        "|------|----------|------------|------------------|",
        f"| 问题数量 | {baseline_stats['total_problems']} | {llm_stats['total_problems']} | {llm_plus_stats['total_problems']} |",
        f"| 子问题数量 | {baseline_stats['total_subproblems']} | {llm_stats['total_subproblems']} | {llm_plus_stats['total_subproblems']} |",
        f"| 总字符数 | {baseline_stats['total_characters']:,} | {llm_stats['total_characters']:,} | {llm_plus_stats['total_characters']:,} |",
        f"| 平均字符/子问题 | {baseline_stats['avg_chars_per_subproblem']:.0f} | {llm_stats['avg_chars_per_subproblem']:.0f} | {llm_plus_stats['avg_chars_per_subproblem']:.0f} |",
        f"| 最小字符数 | {baseline_stats['min_chars']} | {llm_stats['min_chars']} | {llm_plus_stats['min_chars']} |",
        f"| 最大字符数 | {baseline_stats['max_chars']} | {llm_stats['max_chars']} | {llm_plus_stats['max_chars']} |",
        f"| 对抗性 | {'否' if not baseline_stats['is_adversarial'] else '是'} | {'是' if llm_stats['is_adversarial'] else '否'} | {'是' if llm_plus_stats['is_adversarial'] else '否'} |",
        "",
    ])

    # 计算增长比例
    llm_growth = (llm_stats['total_characters'] / baseline_stats['total_characters'] - 1) * 100 if baseline_stats['total_characters'] > 0 else 0
    llm_plus_growth = (llm_plus_stats['total_characters'] / baseline_stats['total_characters'] - 1) * 100 if baseline_stats['total_characters'] > 0 else 0

    report_lines.extend([
        "## 内容增长分析",
        "",
        f"**LLM重构版本**:",
        f"- 总字符增长: {llm_stats['total_characters'] - baseline_stats['total_characters']:,} 字符 (+{llm_growth:.1f}%)",
        f"- 平均每个子问题增长: {llm_stats['avg_chars_per_subproblem'] - baseline_stats['avg_chars_per_subproblem']:.0f} 字符",
        "",
        f"**LLM+规则版本**:",
        f"- 总字符增长: {llm_plus_stats['total_characters'] - baseline_stats['total_characters']:,} 字符 (+{llm_plus_growth:.1f}%)",
        f"- 平均每个子问题增长: {llm_plus_stats['avg_chars_per_subproblem'] - baseline_stats['avg_chars_per_subproblem']:.0f} 字符",
        f"- 相比LLM版本额外增长: {llm_plus_stats['total_characters'] - llm_stats['total_characters']:,} 字符",
        "",
    ])

    # 逐问题对比（前3个问题）
    report_lines.extend([
        "## 问题级别详细对比 (前3个问题)",
        "",
    ])

    for i, (b_p, l_p, lp_p) in enumerate(zip(baseline[:3], llm[:3], llm_plus[:3])):
        report_lines.append(f"### 问题 {i+1}: {b_p.get('problem-id')}")
        report_lines.append("")

        for j, (b_sp, l_sp, lp_sp) in enumerate(zip(
            b_p.get("subproblems", []),
            l_p.get("subproblems", []),
            lp_p.get("subproblems", [])
        )):
            b_len = len(b_sp.get("statement", ""))
            l_len = len(l_sp.get("statement", ""))
            lp_len = len(lp_sp.get("statement", ""))

            report_lines.extend([
                f"**子问题 {j+1} ({b_sp.get('name')})**:",
                f"- Baseline: {b_len} 字符",
                f"- LLM: {l_len} 字符 (+{l_len - b_len}, {l_len/b_len:.2f}x)",
                f"- LLM+: {lp_len} 字符 (+{lp_len - b_len}, {lp_len/b_len:.2f}x)",
                "",
            ])

    # API调用验证
    api_calls_detected = llm_growth > 10  # 如果增长超过10%认为API调用成功

    report_lines.extend([
        "## API调用验证",
        "",
        f"**状态**: {'✅ 成功' if api_calls_detected else '⚠️  可能使用fallback'}",
        f"**证据**: LLM版本内容增长 {llm_growth:.1f}%",
        "",
        "如果增长 > 10%，说明LLM API被成功调用并生成了扩展内容。",
        "如果增长 < 5%，可能使用了fallback机制。",
        "",
    ])

    report_lines.extend([
        "=" * 80,
        "报告结束",
        "=" * 80,
    ])

    report_text = "\n".join(report_lines)

    # 保存报告
    if output_path:
        Path(output_path).write_text(report_text, encoding="utf-8")
        print(f"✓ 对比报告已保存到: {output_path}")

    return report_text


def generate_quick_summary(baseline_path: str, llm_path: str, llm_plus_path: str) -> str:
    """生成快速摘要（适合在终端显示）"""
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    with open(llm_path, "r", encoding="utf-8") as f:
        llm = json.load(f)
    with open(llm_plus_path, "r", encoding="utf-8") as f:
        llm_plus = json.load(f)

    b_chars = sum(len(sp.get("statement", "")) for p in baseline for sp in p.get("subproblems", []))
    l_chars = sum(len(sp.get("statement", "")) for p in llm for sp in p.get("subproblems", []))
    lp_chars = sum(len(sp.get("statement", "")) for p in llm_plus for sp in p.get("subproblems", []))

    return f"""
📊 数据集对比摘要
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Baseline:  {len(baseline)} 问题, {b_chars:,} 字符
LLM版本:   {len(llm)} 问题, {l_chars:,} 字符 (+{(l_chars/b_chars-1)*100:.1f}%)
LLM+版本:  {len(llm_plus)} 问题, {lp_chars:,} 字符 (+{(lp_chars/b_chars-1)*100:.1f}%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
