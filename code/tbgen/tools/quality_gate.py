from __future__ import annotations
import pathlib, subprocess, json, tempfile, shutil, sys
from typing import Dict, Any, List

def run_pytest_with_cov(task_dir: pathlib.Path, unit_paths: List[str]) -> Dict[str, Any]:
    """
    在隔离目录下运行 pytest + coverage，回传基础统计。
    TODO:
    - 对接真实 fuzz/hypothesis/crosshair 并记录指标。
    - 失败时回传 failing tests，用于生成 verbal 反馈。 
    """
    work = pathlib.Path(tempfile.mkdtemp(prefix="tbgen_qg_"))
    try:
        shutil.copytree(task_dir, work / "task", dirs_exist_ok=True)
        cov_xml = work / "task" / ".coverage.xml"
        cmd = ["pytest", "-q", "--disable-warnings", "--maxfail=50", "--cache-clear",
               "--cov=./", f"--cov-report=xml:{cov_xml}"] + unit_paths
        proc = subprocess.run(" ".join(cmd), shell=True, cwd=work / "task", capture_output=True, text=True, timeout=300)
        out = proc.stdout + "\n" + proc.stderr
        return {"rc": proc.returncode, "out": out, "cov_xml": str(cov_xml)}
    finally:
        shutil.rmtree(work, ignore_errors=True)

def cov_threshold_ok(cov_xml_path: str, threshold: float = 0.85) -> bool:
    import re, os
    if not os.path.exists(cov_xml_path):
        return False
    text = open(cov_xml_path, "r", encoding="utf-8", errors="ignore").read()
    m = re.search(r'line-rate="([0-9.]+)"', text)
    if not m: return False
    return float(m.group(1)) >= threshold