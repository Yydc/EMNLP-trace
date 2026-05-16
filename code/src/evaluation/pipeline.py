"""Unified pipeline for dataset generation and evaluation with rich metrics."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.agent.generation import CodeGenerator

from src.core import config
from src.core.dataset_loader import load_dataset_auto
from src.core.adversarial_generator import generate_llm_adversarial_dataset
from src.core.multifile_converter import convert_to_multifile_problem
from src.evaluation.metrics import MetricsTracker
from src.evaluation.workflows import (
    generate_readable_report,
    solve_multifile_problem,
    solve_problem,
)


@dataclass
class DatasetArtifact:
    name: str
    file: Path
    description: str
    difficulty: Optional[str] = None
    dataset_type: str = "single-file"


def run_enhanced_pipeline(
    generation_model: str,
    inference_model: str,
    dataset_type: str,
    multifile_difficulty: str,
    num_problems: int,
    num_runs: int,
    dataset_path: Optional[str] = None,
    output_tag: Optional[str] = None,
    skip_adversarial: bool = False,
) -> Dict[str, object]:
    """Generate (optionally) and evaluate datasets with the requested metrics."""

    if dataset_type not in {"single-file", "multi-file"}:
        raise ValueError(f"Unsupported dataset_type: {dataset_type}")

    requires_api = dataset_type == "single-file" and not skip_adversarial
    if requires_api and not config.API_KEY:
        raise RuntimeError(
            "TOGETHER_API_KEY 未设置：当前配置需要调用 Together API 生成对抗数据"
        )

    config.ensure_output_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_prefix = _sanitize_tag(output_tag)
    run_dir = Path(config.OUTPUT_DIR) / f"evaluation_{dataset_type}{tag_prefix}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"CodeFlow {dataset_type.title()} Evaluation Pipeline")
    print("=" * 80)
    print(f"输出目录: {run_dir}")
    print(f"Generation 模型: {generation_model}")
    print(f"Inference 模型: {inference_model}")
    print(f"问题数量: {num_problems}")
    print(f"运行次数: {num_runs}")
    print("=" * 80)
    print()

    code_generator = CodeGenerator(config.API_KEY, config.API_URL)

    datasets = _prepare_datasets(
        base_dataset_path=dataset_path or config.INPUT_DATASET,
        generation_model=generation_model,
        run_dir=run_dir,
        num_problems=num_problems,
        skip_adversarial=skip_adversarial,
        dataset_type=dataset_type,
        multifile_difficulty=multifile_difficulty,
    )

    aggregated_runs: List[Dict[str, object]] = []

    for run_id in range(1, num_runs + 1):
        print(f"\n{'=' * 80}")
        print(f"RUN {run_id}/{num_runs}")
        print(f"{'=' * 80}")

        run_output_dir = run_dir / f"run_{run_id}"
        run_output_dir.mkdir(parents=True, exist_ok=True)

        run_summary: Dict[str, object] = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "datasets": [],
        }

        for ds in datasets:
            result = _evaluate_dataset(
                dataset=ds,
                output_dir=run_output_dir / ds.name,
                code_generator=code_generator,
                inference_model=inference_model,
                num_problems=num_problems,
                dataset_type=ds.dataset_type,
            )
            run_summary["datasets"].append(result)

        aggregated_runs.append(run_summary)

    summary_path = run_dir / "run_summary.json"
    with summary_path.open("w", encoding="utf-8") as fout:
        json.dump(aggregated_runs, fout, ensure_ascii=False, indent=2)

    print("\nPipeline 完成，结果保存在:", run_dir)
    return {"main_dir": str(run_dir), "runs": aggregated_runs}


def _prepare_datasets(
    base_dataset_path: str,
    generation_model: str,
    run_dir: Path,
    num_problems: int,
    skip_adversarial: bool,
    dataset_type: str,
    multifile_difficulty: str,
) -> List[DatasetArtifact]:
    artifacts: List[DatasetArtifact] = []

    # 根据配置决定数据源
    if config.DATA_SOURCE == "huggingface":
        print(f"从HuggingFace加载数据集: {config.HF_DATASET_NAME} (split={config.DATASET_SPLIT})")
        base_problems = load_dataset_auto(
            source="huggingface",
            dataset_name=config.HF_DATASET_NAME,
            split=config.DATASET_SPLIT,
            num_problems=num_problems,
        )
        # 保存到临时文件供后续使用
        temp_base_file = run_dir / "temp_base_dataset.json"
        with temp_base_file.open("w", encoding="utf-8") as f:
            json.dump(base_problems, f, ensure_ascii=False, indent=2)
        base_path = temp_base_file
    else:
        base_path = Path(base_dataset_path)
        if not base_path.exists():
            raise FileNotFoundError(f"基础数据集不存在: {base_dataset_path}")

    if dataset_type == "multi-file":
        if dataset_path_is_multifile(base_path):
            data = json.loads(base_path.read_text(encoding="utf-8"))
            baseline_file = run_dir / base_path.name
            baseline_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            baseline_file = run_dir / "multifile_baseline.json"
            with base_path.open("r", encoding="utf-8") as fin:
                singlefile_problems = json.load(fin)
            multifile_problems = [
                convert_to_multifile_problem(p, difficulty=multifile_difficulty)
                for p in singlefile_problems[:num_problems]
            ]
            with baseline_file.open("w", encoding="utf-8") as fout:
                json.dump(multifile_problems, fout, ensure_ascii=False, indent=2)
            data = multifile_problems

        artifacts.append(
            DatasetArtifact(
                name="multifile_baseline",
                file=baseline_file,
                description="Converted multi-file baseline dataset",
                difficulty=multifile_difficulty,
                dataset_type="multi-file",
            )
        )

        if not skip_adversarial:
            # 为multi-file也生成对抗数据集
            # Step 1: 先生成单文件格式的LLM对抗数据
            singlefile_baseline = run_dir / "temp_singlefile_baseline.json"
            with base_path.open("r", encoding="utf-8") as fin:
                base_problems = json.load(fin)
            if isinstance(base_problems, list):
                base_problems = base_problems[:num_problems]
            with singlefile_baseline.open("w", encoding="utf-8") as fout:
                json.dump(base_problems, fout, ensure_ascii=False, indent=2)

            # Step 2: 生成LLM对抗数据（单文件格式）
            llm_adversarial_single = run_dir / "temp_llm_adversarial_single.json"
            print(f"  [Multi-file] 生成LLM对抗数据...")
            generate_llm_adversarial_dataset(
                input_file=str(singlefile_baseline),
                output_file=str(llm_adversarial_single),
                api_key=config.API_KEY,
                api_url=config.API_URL,
                model_name=generation_model,
                difficulty=multifile_difficulty,
                num_datasets=1,
            )

            # Step 3: 转换为multi-file格式
            with llm_adversarial_single.open("r", encoding="utf-8") as fin:
                llm_problems = json.load(fin)

            multifile_adversarial = [
                convert_to_multifile_problem(problem, difficulty=multifile_difficulty)
                for problem in llm_problems
            ]

            multifile_llm_file = run_dir / f"multifile_adversarial_llm_{multifile_difficulty}.json"
            with multifile_llm_file.open("w", encoding="utf-8") as fout:
                json.dump(multifile_adversarial, fout, ensure_ascii=False, indent=2)

            artifacts.append(
                DatasetArtifact(
                    name="multifile_adversarial_llm",
                    file=multifile_llm_file,
                    description=f"Multi-file adversarial dataset (LLM-generated, {multifile_difficulty})",
                    difficulty=multifile_difficulty,
                    dataset_type="multi-file",
                )
            )

            # 清理临时文件
            if singlefile_baseline.exists():
                singlefile_baseline.unlink()
            if llm_adversarial_single.exists():
                llm_adversarial_single.unlink()

            print(f"  ✓ Multi-file对抗数据集已生成")

        return artifacts

    with base_path.open("r", encoding="utf-8") as fin:
        base_problems = json.load(fin)

    if isinstance(base_problems, list):
        base_problems = base_problems[:num_problems]

    baseline_file = run_dir / "baseline.json"
    with baseline_file.open("w", encoding="utf-8") as fout:
        json.dump(base_problems, fout, ensure_ascii=False, indent=2)

    artifacts.append(
        DatasetArtifact(
            name="baseline",
            file=baseline_file,
            description="Original baseline dataset",
            dataset_type="single-file",
        )
    )

    if skip_adversarial:
        return artifacts

    llm_dataset_file = run_dir / "adversarial_llm_extreme.json"
    generate_llm_adversarial_dataset(
        input_file=str(baseline_file),
        output_file=str(llm_dataset_file),
        api_key=config.API_KEY,
        api_url=config.API_URL,
        model_name=generation_model,
        difficulty="extreme",
        num_datasets=1,
    )

    artifacts.append(
        DatasetArtifact(
            name="adversarial_llm",
            file=llm_dataset_file,
            description="LLM-generated adversarial dataset (extreme difficulty)",
            difficulty="extreme",
            dataset_type="single-file",
        )
    )

    return artifacts


def dataset_path_is_multifile(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return bool(data[0].get("is_multifile"))
    except Exception:
        return False
    return False


def _evaluate_dataset(
    dataset: DatasetArtifact,
    output_dir: Path,
    code_generator: CodeGenerator,
    inference_model: str,
    num_problems: int,
    dataset_type: str,
) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)

    tracker = MetricsTracker() if config.ENABLE_METRICS else None
    solutions: Dict[str, object] = {}
    detailed_logs: List[Dict[str, object]] = []

    with dataset.file.open("r", encoding="utf-8") as fin:
        problems = json.load(fin)

    total = min(num_problems, len(problems))
    solved = 0

    for idx, problem in enumerate(problems[:total], start=1):
        print(f"[{dataset.name}] Problem {idx}/{total}: {problem.get('problem-id')}")

        if dataset_type == "multi-file" or problem.get("is_multifile"):
            solution, success, log = solve_multifile_problem(
                problem,
                code_generator,
                model_name=inference_model,
            )
        else:
            solution, success, log = solve_problem(
                problem,
                code_generator,
                model_name=inference_model,
            )

        log["solved"] = success
        detailed_logs.append(log)

        if tracker:
            tracker.record_problem_result(log)

        if success:
            solved += 1
            solutions[problem.get("problem-id")] = solution

    summary = {
        "dataset": dataset.name,
        "description": dataset.description,
        "difficulty": dataset.difficulty,
        "total": total,
        "solved": solved,
        "success_rate": solved / total if total else 0.0,
    }

    (output_dir / "solutions.json").write_text(
        json.dumps(solutions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _write_summary_markdown(output_dir, detailed_logs, summary)

    if config.SAVE_INTERMEDIATE_LOGS:
        (output_dir / "detailed_logs.json").write_text(
            json.dumps(detailed_logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if config.GENERATE_DETAILED_REPORTS:
        generate_readable_report(detailed_logs, str(output_dir))

    metrics_report = None
    if tracker and config.ENABLE_METRICS:
        metrics_path = output_dir / "metrics.json"
        tracker.save_metrics(str(metrics_path))
        metrics_report_path = output_dir / "metrics_report.md"
        tracker.generate_metrics_report(str(metrics_report_path))
        metrics_report = tracker.compute_final_metrics()

    return {
        "dataset": dataset.name,
        "summary": summary,
        "metrics": metrics_report,
        "logs_path": str(output_dir),
    }


def _sanitize_tag(tag: Optional[str]) -> str:
    if not tag:
        return ""
    cleaned = "_" + "".join(
        c if c.isalnum() or c in {"-", "_"} else "-" for c in tag.strip()
    )
    return cleaned


def _write_summary_markdown(output_dir: Path, logs: List[Dict[str, object]], summary: Dict[str, object]) -> None:
    lines: List[str] = [
        "# Dataset Summary",
        "",
        f"- Dataset: `{summary.get('dataset')}`",
        f"- Total problems: {summary.get('total')}",
        f"- Solved: {summary.get('solved')} ({summary.get('success_rate', 0)*100:.1f}%)",
        "",
        "| Problem | Status | Progress | Notes |",
        "|---------|--------|----------|-------|",
    ]

    for problem_log in logs:
        problem_id = problem_log.get("problem_id", "unknown")
        solved = problem_log.get("solved", False)
        status = "✅" if solved else "❌"
        subproblems = problem_log.get("subproblems", [])
        solved_count = sum(1 for sp in subproblems if sp.get("solved"))
        progress = f"{solved_count}/{len(subproblems)}"

        note = ""
        if not solved and subproblems:
            last_sub = subproblems[-1]
            attempts = last_sub.get("attempts", [])
            if attempts:
                note = str(attempts[-1].get("test_result", "")).replace("\n", " ")
        lines.append(f"| `{problem_id}` | {status} | {progress} | {note} |")

    summary_md = output_dir / "summary.md"
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


__all__ = ["run_enhanced_pipeline"]
