from __future__ import annotations
import abc, json, os, pathlib, sys

class BaseAgent(abc.ABC):
    """
    所有代理必须实现 run_one_turn：读取 TRACEBENCH_TURN_INPUT 并输出 agent_output JSON。
    在批量运行中将被 tracebench 引擎以 shell 命令方式调用。
    """
    @abc.abstractmethod
    def run_one_turn(self) -> dict:
        ...

    @staticmethod
    def _read_turn_input() -> dict:
        p = os.environ.get("TRACEBENCH_TURN_INPUT")
        if not p: return {}
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))

    @staticmethod
    def _write_stdout(obj: dict):
        print(json.dumps(obj, ensure_ascii=False))