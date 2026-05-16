from __future__ import annotations
import json, pathlib, datetime as dt

def write_markdown(report_json: dict, out_path: str):
    """
    TODO: 绘制曲线（失败序列恢复概率）、按 shift_tags 的分桶表格、代理对比。
    """
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append(f"# TraceBench 报告 ({dt.datetime.utcnow().isoformat()}Z)\n")
    lines.append("## 全局指标\n")
    lines.append("```json\n" + json.dumps(report_json, ensure_ascii=False, indent=2) + "\n```\n")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p