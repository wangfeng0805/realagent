"""✅ 渲染 render（capabilities/renderer.py）。payload→中文成稿。"""
from real_agent.app.capabilities.renderer import render

PAYLOAD = {"member": {"member_level_name": "钻石", "points": 1200,
                      "effective_growth_value": 5000, "membership_end_time": "2026-12-31"}}

def test_member_points():
    assert render("member.points", PAYLOAD) == "您当前有 **1200 积分**。"

def test_member_info_table():
    out = render("member.info", PAYLOAD)
    assert "会员等级 | 钻石" in out and "当前积分 | 1200 积分" in out

def test_unknown_intent_returns_none():
    assert render("no.such.intent", PAYLOAD) is None
