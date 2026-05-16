from __future__ import annotations
from dataclasses import dataclass
import pathlib, json

@dataclass
class RepoGenConfig:
    # 对于仓库级任务，更多是“映射/重写 spec 与 verbal”，而非 LLM 纯造题
    pass

def map_swe_verified(jsonl_path: str, out_dir: str):
    """
    将 SWE-bench Verified 的 JSONL 按 TraceBench/repo 对齐字段直接写出 task.json。
    TODO:
    - 可追加 LLM 生成“verbal 抽象反馈”或“迁移风险提示”，用于噪声实验。
    """
    src = pathlib.Path(jsonl_path)
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        item = json.loads(line)
        tid = f"repo:swe-verified:{item['instance_id']}"
        tdir = out / tid.replace(":", "__")
        tdir.mkdir(parents=True, exist_ok=True)
        task = {
            "task_id": tid,
            "track": "repo",
            "title": item.get("title", item["instance_id"]),
            "spec_md": item.get("problem_statement", ""),
            "repo": {"name": item.get("repo"), "base_commit": item.get("base_commit")},
            "tests": {
                "fail_to_pass": item.get("fail_to_pass", []),
                "pass_to_pass": item.get("pass_to_pass", []),
                "oracle_test_patch": item.get("test_patch", None),
                "unit": {"paths": item.get("unit_paths", [])},
            },
            "env": {"swebench": {"version": "verified", "environment_setup_commit": None}},
            "ground_truth": {"reference_patch": item.get("patch")},
            "feedback_profiles": ["compile+unit_lowcov+novice"],
            "shift_tags": item.get("shift_tags", []),
            "source": "SWE-bench Verified (mapped)",
        }
        (tdir / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return out