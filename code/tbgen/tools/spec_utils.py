from __future__ import annotations
import json, pathlib
from typing import Any, Dict

def ensure_task_shape(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    轻量形状校验（避免硬依赖 jsonschema）——用于生成阶段的快速失败。
    TODO:
    - 可切换为严格 jsonschema 校验并输出可读错误（集成 tracebench/schemas）。
    """
    required = ["task_id", "track", "title", "tests", "env"]
    for k in required:
        if k not in task:
            raise ValueError(f"Missing required field: {k}")
    if "unit" not in task["tests"]:
        raise ValueError("tests.unit.paths 必须存在")
    return task

def write_task(dest_dir: pathlib.Path, task: Dict[str, Any]):
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")