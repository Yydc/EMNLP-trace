"""CodeFlow Evaluation - 代码流评测系统

高质量的编程问题评测框架，支持单文件和多文件模式。
"""

__version__ = "2.0.0"
__author__ = "CodeFlow Team"

# 包级别导出
from src.core.dataset_loader import load_dataset_auto
from src.core.adversarial_generator import (
    generate_two_stage_adversarial_dataset,
    LLMAdversarialGenerator,
)

__all__ = [
    "load_dataset_auto",
    "generate_two_stage_adversarial_dataset",
    "LLMAdversarialGenerator",
]
