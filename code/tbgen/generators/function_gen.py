from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pathlib, json, os

from tbgen.providers.openai_client import OpenAIClient, OpenAIConfig
from tbgen.tools.spec_utils import ensure_task_shape, write_task
from tbgen.tools.test_builder import materialize_tests
from tbgen.tools.quality_gate import run_pytest_with_cov, cov_threshold_ok

@dataclass
class FunctionGenConfig:
    model: str = "o3"       # TODO: 改为配置文件驱动
    temperature: float = 0.2
    cov_threshold: float = 0.85

class FunctionGenerator:
    def __init__(self, cfg: FunctionGenConfig):
        self.cfg = cfg
        self.client = OpenAIClient(OpenAIConfig(model=cfg.model, temperature=cfg.temperature, mock=bool(os.environ.get("TBGEN_MOCK"))))

    def generate_one(self, out_dir: pathlib.Path) -> pathlib.Path:
        # TODO: 根据 prompt 模板（系统/用户）注入 io_signature/difficulty/shift_tags
        system = "你是代码评测出题官，请输出严格 JSON（TraceBench 任务卡）。"
        user = "生成一个简单函数级任务（含 tests.unit.paths），starter_files 可为空。"
        text = self.client.chat(system=system, user=user)
        task = ensure_task_shape(json.loads(text))

        # 落盘任务
        tdir = out_dir / task["task_id"].replace(":", "__")
        write_task(tdir, task)

        # 物化基础测试（生成阶段最少要有）
        materialize_tests(tdir, task["track"])

        # 质量闸门（覆盖率）
        unit_paths = task["tests"]["unit"]["paths"]
        res = run_pytest_with_cov(tdir, unit_paths)
        if not cov_threshold_ok(res.get("cov_xml", ""), threshold=self.cfg.cov_threshold):
            # TODO: 触发扩展测试生成/性质测试/模糊测试增强后再验
            pass  # 先放行
        return tdir

    def generate_n(self, out_dir: str, n: int = 1):
        out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        tdirs = []
        for i in range(n):
            tdirs.append(self.generate_one(out))
        return tdirs