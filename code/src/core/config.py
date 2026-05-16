"""Global configuration for CodeFlow evaluation pipeline.

This module centralises API credentials, model choices, dataset paths, and
feature flags so that both dataset generation and evaluation share the same
source of truth.  Environment variables can override the default values to
avoid hard-coding secrets in the repository.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Literal


# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------

API_KEY: str = os.getenv("TOGETHER_API_KEY", "")
API_URL: str = os.getenv("TOGETHER_API_BASE", "https://api.together.xyz/v1")
ANTHROPIC_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

if not API_KEY and not ANTHROPIC_KEY:
    # Error注入不需要API，只有LLM评估才需要
    print("⚠️  未检测到 TOGETHER_API_KEY 或 ANTHROPIC_API_KEY，后续将无法进行LLM评估（error注入不受影响）。")


# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: Dict[str, str] = {
    "qwen-coder-32b": "Qwen/Qwen2.5-Coder-32B-Instruct",
    "qwen-thinking": "Qwen/Qwen3-235B-A22B-Thinking-2507",
    "deepseek-coder": "deepseek-ai/deepseek-coder-33b-instruct",
}

GENERATION_MODEL: str = os.getenv(
    "CODEFLOW_GENERATION_MODEL", AVAILABLE_MODELS["qwen-coder-32b"]
)
INFERENCE_MODEL: str = os.getenv(
    "CODEFLOW_INFERENCE_MODEL", AVAILABLE_MODELS["qwen-coder-32b"]
)


# ---------------------------------------------------------------------------
# Dataset configuration
# ---------------------------------------------------------------------------

# 数据源配置
DATA_SOURCE: str = os.getenv("CODEFLOW_DATA_SOURCE", "huggingface")  # "huggingface" 或 "local"
HF_DATASET_NAME: str = os.getenv("CODEFLOW_HF_DATASET", "WaterWang-001/CodeFlowBench-2505")
DATASET_SPLIT: str = os.getenv("CODEFLOW_DATASET_SPLIT", "train")

# 本地数据集路径（当DATA_SOURCE="local"时使用）
CONFIG_DIR = Path(__file__).resolve().parent
SRC_DIR = CONFIG_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
REPO_ROOT = PROJECT_ROOT.parent

INPUT_DATASET: str = os.getenv(
    "CODEFLOW_INPUT_DATASET",
    str(REPO_ROOT / "data" / "codeflowbench_sample_3_problems.json"),
)

OUTPUT_DIR: str = os.getenv(
    "CODEFLOW_OUTPUT_DIR",
    str(PROJECT_ROOT / "output"),
)

# 验证DATASET_TYPE
_dataset_type_raw = os.getenv("CODEFLOW_DATASET_TYPE", "single-file")
if _dataset_type_raw not in ("single-file", "multi-file"):
    raise ValueError(f"无效的DATASET_TYPE: {_dataset_type_raw}，必须是 'single-file' 或 'multi-file'")
DATASET_TYPE: Literal["single-file", "multi-file"] = _dataset_type_raw  # type: ignore

# 验证MULTIFILE_DIFFICULTY
_multifile_difficulty_raw = os.getenv("CODEFLOW_MULTIFILE_DIFFICULTY", "hard")
if _multifile_difficulty_raw not in ("easy", "medium", "hard", "extreme"):
    raise ValueError(f"无效的MULTIFILE_DIFFICULTY: {_multifile_difficulty_raw}，必须是 'easy', 'medium', 'hard' 或 'extreme'")
MULTIFILE_DIFFICULTY: Literal["easy", "medium", "hard", "extreme"] = _multifile_difficulty_raw  # type: ignore

NUM_PROBLEMS: int = int(os.getenv("CODEFLOW_NUM_PROBLEMS", "10"))
NUM_RUNS: int = int(os.getenv("CODEFLOW_NUM_RUNS", "1"))

# 需要生成的 adversarial 难度层（V2/V3 使用 extreme, 亦可根据需求扩展）
ADVERSARIAL_LEVELS: Iterable[str] = ("extreme",)


# ---------------------------------------------------------------------------
# Feature flags & runtime options
# ---------------------------------------------------------------------------

ENABLE_ADVERSARIAL: bool = os.getenv("CODEFLOW_ENABLE_ADVERSARIAL", "1") != "0"
ENABLE_METRICS: bool = os.getenv("CODEFLOW_ENABLE_METRICS", "1") != "0"
ENABLE_CROSS_RUN_ANALYSIS: bool = (
    os.getenv("CODEFLOW_ENABLE_CROSS_RUN_ANALYSIS", "0") == "1"
)

GENERATE_DETAILED_REPORTS: bool = (
    os.getenv("CODEFLOW_GENERATE_DETAILED_REPORTS", "1") != "0"
)
SAVE_INTERMEDIATE_LOGS: bool = (
    os.getenv("CODEFLOW_SAVE_INTERMEDIATE_LOGS", "1") != "0"
)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def get_config_value(cli_arg, env_var_name: str, default):
    """
    配置优先级: CLI参数 > 环境变量 > 默认值

    Args:
        cli_arg: 命令行参数值（如果为None则忽略）
        env_var_name: 环境变量名称
        default: 默认值

    Returns:
        根据优先级返回的配置值
    """
    if cli_arg is not None:
        return cli_arg
    env_value = os.getenv(env_var_name)
    if env_value is not None:
        return env_value
    return default


# ---------------------------------------------------------------------------
# Temperature schedule for反思式多轮调用
# ---------------------------------------------------------------------------

INITIAL_TEMPERATURE: float = float(os.getenv("CODEFLOW_INITIAL_TEMPERATURE", "0.6"))
TEMPERATURE_INCREASE: float = float(os.getenv("CODEFLOW_TEMPERATURE_STEP", "0.15"))
MAX_TEMPERATURE: float = float(os.getenv("CODEFLOW_MAX_TEMPERATURE", "0.95"))
MAX_ATTEMPTS: int = int(os.getenv("CODEFLOW_MAX_ATTEMPTS", "5"))


# ---------------------------------------------------------------------------
# Metric configuration
# ---------------------------------------------------------------------------

# pass@turn 统计的阈值集合，例如 ≤1, ≤2, ≤3
PASS_AT_TURN_BUCKETS = tuple(
    int(x) for x in os.getenv("CODEFLOW_PASS_AT_TURN_BUCKETS", "1,2,3").split(",")
    if x.strip().isdigit()
)

# Traceability 证据匹配的字符串模式（可按需更新）
TRACE_EVIDENCE_KEYS = (
    "test",  # 测试编号
    "assert",  # 断言
    "failure",
)

# Replayability 检查时允许的最多误差次数
REPLAY_TOLERANCE: int = int(os.getenv("CODEFLOW_REPLAY_TOLERANCE", "0"))

# ---------------------------------------------------------------------------
# Extended Metrics Configuration (Attribution, Propagation, Causality, etc.)
# ---------------------------------------------------------------------------

# Hit@attempt<=k: attempt级别的命中率（k值集合）
ATTEMPT_HIT_BUCKETS = tuple(
    int(x) for x in os.getenv("CODEFLOW_ATTEMPT_HIT_BUCKETS", "1,3,5").split(",")
    if x.strip().isdigit()
)

# Precision@k: 前k次尝试的成功率（k值集合）
PRECISION_K_VALUES = tuple(
    int(x) for x in os.getenv("CODEFLOW_PRECISION_K_VALUES", "1,3,5").split(",")
    if x.strip().isdigit()
)

# Pass-rate Slope: 通过率变化趋势（最小turn数要求）
PASS_RATE_SLOPE_MIN_TURNS: int = int(os.getenv("CODEFLOW_SLOPE_MIN_TURNS", "3"))

# Collapse Round: 连续失败检测
COLLAPSE_THRESHOLD: float = float(os.getenv("CODEFLOW_COLLAPSE_THRESHOLD", "0.3"))
COLLAPSE_CONSECUTIVE_ROUNDS: int = int(os.getenv("CODEFLOW_COLLAPSE_ROUNDS", "3"))

# Depth stratification: 是否启用按depth分层的metrics
ENABLE_DEPTH_STRATIFICATION: bool = os.getenv("CODEFLOW_DEPTH_STRATIFICATION", "1") != "0"


# ---------------------------------------------------------------------------
# Verification pipeline设置
# ---------------------------------------------------------------------------

VERIFICATION_STAGES = (
    "unit",
    "extended",
    "fuzz",
    "property",
    "symbolic",
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


__all__ = [
    "API_KEY",
    "API_URL",
    "AVAILABLE_MODELS",
    "GENERATION_MODEL",
    "INFERENCE_MODEL",
    "INPUT_DATASET",
    "OUTPUT_DIR",
    "DATASET_TYPE",
    "MULTIFILE_DIFFICULTY",
    "NUM_PROBLEMS",
    "NUM_RUNS",
    "ADVERSARIAL_LEVELS",
    "ENABLE_ADVERSARIAL",
    "ENABLE_METRICS",
    "ENABLE_CROSS_RUN_ANALYSIS",
    "GENERATE_DETAILED_REPORTS",
    "SAVE_INTERMEDIATE_LOGS",
    "INITIAL_TEMPERATURE",
    "TEMPERATURE_INCREASE",
    "MAX_TEMPERATURE",
    "MAX_ATTEMPTS",
    "PASS_AT_TURN_BUCKETS",
    "TRACE_EVIDENCE_KEYS",
    "REPLAY_TOLERANCE",
    "VERIFICATION_STAGES",
    "ATTEMPT_HIT_BUCKETS",
    "PRECISION_K_VALUES",
    "PASS_RATE_SLOPE_MIN_TURNS",
    "COLLAPSE_THRESHOLD",
    "COLLAPSE_CONSECUTIVE_ROUNDS",
    "ENABLE_DEPTH_STRATIFICATION",
    "ensure_output_dir",
]

