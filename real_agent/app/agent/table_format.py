"""Markdown 表格渲染（新版 / real_agent）。

把结构化数据渲染成前端可读的 Markdown 表格：key_value_table（两列「项目/信息」）与
markdown_table（任意表头）。单元格统一经 _cell 清洗（空值→「—」、转义 | 、换行→<br>）。

重建说明：由 .so 重建；_cell/key_value_table/markdown_table 经对拍与原 .so 一致。
"""
from typing import Iterable


def _cell(value: object) -> str:
    """单元格清洗：None/空串→「—」；转义竖线；换行→<br>。"""
    if value is None:
        return "—"
    text = str(value)
    if text == "":
        return "—"
    return text.replace("|", "\\|").replace("\n", "<br>")


def key_value_table(rows: "Iterable[tuple[object, object]]") -> str:
    """两列表格：| 项目 | 信息 |。"""
    lines = ["| 项目 | 信息 |", "| --- | --- |"]
    for k, v in rows:
        lines.append(f"| {_cell(k)} | {_cell(v)} |")
    return "\n".join(lines)


def markdown_table(headers: "Iterable[object]", rows: "Iterable[Iterable[object]]") -> str:
    """任意表头的 Markdown 表格。"""
    headers = list(headers)
    head = "| " + " | ".join(_cell(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    lines = [head, sep]
    for row in rows:
        lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(lines)
