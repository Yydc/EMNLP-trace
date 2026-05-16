"""核心功能模块

包含数据加载、对抗数据生成等核心功能。
"""

from .dataset_loader import load_dataset_auto, load_from_huggingface, load_from_local
from .adversarial_generator import (
    generate_two_stage_adversarial_dataset,
    generate_llm_adversarial_dataset,
    LLMAdversarialGenerator,
)
from .multifile_converter import convert_to_multifile_problem, generate_multifile_dataset
from .report_generator import generate_comparison_report, generate_quick_summary
from . import config

__all__ = [
    # 数据加载
    "load_dataset_auto",
    "load_from_huggingface",
    "load_from_local",
    # 对抗数据生成
    "generate_two_stage_adversarial_dataset",
    "generate_llm_adversarial_dataset",
    "LLMAdversarialGenerator",
    # Multi-file转换
    "convert_to_multifile_problem",
    "generate_multifile_dataset",
    # 报告生成
    "generate_comparison_report",
    "generate_quick_summary",
    # 配置
    "config",
]
