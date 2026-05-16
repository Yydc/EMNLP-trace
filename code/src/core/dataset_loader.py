"""数据集加载工具 - 支持从HuggingFace或本地文件加载数据集"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Dict, Optional


def load_from_huggingface(
    dataset_name: str = "WaterWang-001/CodeFlowBench-2505",
    split: str = "train",
    cache_dir: Optional[str] = None,
) -> List[Dict]:
    """从HuggingFace加载数据集

    Args:
        dataset_name: HuggingFace数据集名称
        split: 数据集分割（train/test/validation）
        cache_dir: 缓存目录（可选）

    Returns:
        问题列表
    """
    try:
        from datasets import load_dataset
    except ImportError:
        raise ImportError(
            "需要安装 datasets 库才能从 HuggingFace 加载数据集。\n"
            "请运行: pip install datasets"
        )

    print(f"正在从 HuggingFace 加载数据集: {dataset_name} (split={split})...")

    try:
        # 尝试正常加载
        dataset = load_dataset(dataset_name, split=split, cache_dir=cache_dir)
    except ValueError as e:
        if "Feature type 'List' not found" in str(e):
            print("检测到schema兼容性问题，尝试使用data_files方式加载...")
            # 回退方案：直接从data files加载
            try:
                dataset = load_dataset(
                    dataset_name,
                    split=split,
                    cache_dir=cache_dir,
                    verification_mode='no_checks'  # 跳过schema验证
                )
            except Exception as e2:
                print(f"回退方案也失败了: {e2}")
                print("\n建议解决方案:")
                print("1. 升级datasets库: pip install --upgrade datasets")
                print("2. 或使用预下载的本地文件:")
                print("   - 手动从HuggingFace下载数据集JSON文件")
                print("   - 设置 CODEFLOW_DATA_SOURCE=local")
                print("   - 设置 CODEFLOW_INPUT_DATASET=path/to/downloaded/file.json")
                raise RuntimeError(f"无法加载HuggingFace数据集: {e}") from e
        else:
            raise

    # 转换为列表格式
    problems = []
    for item in dataset:
        problems.append(dict(item))

    print(f"✓ 成功加载 {len(problems)} 个问题")
    return problems


def load_from_local(file_path: str) -> List[Dict]:
    """从本地JSON文件加载数据集

    Args:
        file_path: JSON文件路径

    Returns:
        问题列表
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"数据集文件不存在: {file_path}")

    print(f"正在从本地文件加载数据集: {file_path}...")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # 确保返回列表格式
    if isinstance(data, list):
        problems = data
    elif isinstance(data, dict):
        # 如果是字典，尝试提取problems字段
        problems = data.get("problems", [data])
    else:
        raise ValueError(f"不支持的数据格式: {type(data)}")

    print(f"✓ 成功加载 {len(problems)} 个问题")
    return problems


def load_dataset_auto(
    source: str = "huggingface",
    dataset_name: str = "WaterWang-001/CodeFlowBench-2505",
    local_path: Optional[str] = None,
    split: str = "train",
    num_problems: Optional[int] = None,
) -> List[Dict]:
    """自动选择加载方式

    Args:
        source: 数据源 ("huggingface" 或 "local")
        dataset_name: HuggingFace数据集名称
        local_path: 本地文件路径（当source="local"时使用）
        split: HuggingFace数据集分割
        num_problems: 限制加载的问题数量（可选）

    Returns:
        问题列表
    """
    if source == "huggingface":
        problems = load_from_huggingface(dataset_name, split=split)
    elif source == "local":
        if not local_path:
            raise ValueError("使用local模式时必须提供local_path参数")
        problems = load_from_local(local_path)
    else:
        raise ValueError(f"不支持的数据源: {source}，必须是 'huggingface' 或 'local'")

    # 限制问题数量
    if num_problems is not None and num_problems > 0:
        problems = problems[:num_problems]
        print(f"已限制为前 {len(problems)} 个问题")

    return problems


def save_dataset_to_local(problems: List[Dict], output_path: str) -> None:
    """将数据集保存到本地JSON文件

    Args:
        problems: 问题列表
        output_path: 输出文件路径
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)

    print(f"✓ 数据集已保存到: {output_path}")


# 方便的环境变量配置
def load_from_env() -> List[Dict]:
    """根据环境变量自动加载数据集

    环境变量:
        CODEFLOW_DATA_SOURCE: "huggingface" 或 "local" (默认: huggingface)
        CODEFLOW_HF_DATASET: HuggingFace数据集名称 (默认: WaterWang-001/CodeFlowBench-2505)
        CODEFLOW_LOCAL_DATASET: 本地文件路径
        CODEFLOW_DATASET_SPLIT: 数据集分割 (默认: train)
        CODEFLOW_NUM_PROBLEMS: 加载问题数量限制
    """
    source = os.getenv("CODEFLOW_DATA_SOURCE", "huggingface")
    dataset_name = os.getenv("CODEFLOW_HF_DATASET", "WaterWang-001/CodeFlowBench-2505")
    local_path = os.getenv("CODEFLOW_LOCAL_DATASET")
    split = os.getenv("CODEFLOW_DATASET_SPLIT", "train")
    num_problems = os.getenv("CODEFLOW_NUM_PROBLEMS")

    num_problems_int = int(num_problems) if num_problems and num_problems.isdigit() else None

    return load_dataset_auto(
        source=source,
        dataset_name=dataset_name,
        local_path=local_path,
        split=split,
        num_problems=num_problems_int,
    )


__all__ = [
    "load_from_huggingface",
    "load_from_local",
    "load_dataset_auto",
    "save_dataset_to_local",
    "load_from_env",
]
