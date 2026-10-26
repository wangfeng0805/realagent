"""✅ Markdown 表格（agent/table_format.py）。"""
from real_agent.app.agent.table_format import _cell, key_value_table, markdown_table

def test_cell_escapes():
    assert _cell(None) == "—"
    assert _cell("") == "—"
    assert _cell("a|b") == "a\\|b"
    assert _cell("多\n行") == "多<br>行"

def test_kv_table():
    out = key_value_table([("名称", "星巴克"), ("类型", None)])
    assert "| 名称 | 星巴克 |" in out and "| 类型 | — |" in out
