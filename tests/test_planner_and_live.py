"""planner + member_agent 路由 + live_* 纯函数 + official_* 静态成稿 的单元测试。

跑法： pytest tests/test_planner_and_live.py -v
覆盖已对拍 .so 的确定性部分（渲染/实时取数路径为装配点，不在此断言逐字）。
"""
import pytest
from datetime import date
from real_agent.app.agent import planner as P
from real_agent.app.agent import member_agent as MA
from real_agent.app.agent import live_activity as LA
from real_agent.app.agent import live_merchant as LM
from real_agent.app.agent import official_images as OI
from real_agent.app.agent import official_app_knowledge as OA


# ---------- planner.build_plan ----------
def _sig(steps): return [(s.domain, s.name, s.tier, round(s.timeout, 2)) for s in steps]

def test_plan_primary_necessary_others_enhancement():
    u = {"domains": ["parking", "merchant", "point_mall"], "search_strategy": "cross_domain", "entities": {}}
    assert _sig(P.build_plan(u, "S")) == [
        ("parking", "parking", "necessary", 1.8),
        ("merchant", "merchants", "enhancement", 0.8),
        ("point_mall", "point_mall", "enhancement", 0.8),
    ]

def test_plan_single_tool_budget_two():
    u = {"domains": ["parking", "merchant", "point_mall"], "search_strategy": "single_tool", "entities": {}}
    assert len(P.build_plan(u, "S")) == 2

def test_plan_knowledge_vector_timeout():
    u = {"domains": ["knowledge"], "search_strategy": "cross_domain", "entities": {}}
    assert _sig(P.build_plan(u, "S")) == [("knowledge", "knowledge", "necessary", 2.5)]

def test_plan_dedup_step_names():
    u = {"domains": ["merchant", "recommendation"], "search_strategy": "cross_domain", "entities": {}}
    # recommendation 的 merchants 与 merchant 同名被去重，只留 activities
    assert _sig(P.build_plan(u, "S")) == [
        ("merchant", "merchants", "necessary", 1.8),
        ("recommendation", "activities", "enhancement", 0.8),
    ]

def test_primary_domains_first_nonskip():
    assert P._primary_domains({"domains": ["navigation", "member", "parking"]}) == {"member"}
    assert P._primary_domains({"domains": ["navigation", "other"]}) == set()

def test_trim_drops_found_only():
    assert P._trim({"found": True, "a": 1, "raw": "r"}) == {"a": 1, "raw": "r"}


# ---------- member_agent.should_route ----------
@pytest.mark.parametrize("q,expected", [
    ("我的积分", True), ("积分规则", True), ("会员怎么升级", True), ("我有几张券", True),
    ("换绑手机号", True), ("生日福利", True), ("会员信息", True), ("升级会员需要多少成长值", True),
    ("停车费", False), ("我的停车", False), ("商城", False), ("车牌", False),
    ("积分", False), ("会员", False), ("你好", False), ("成长值还差多少", False),
    ("停车积分规则", False),  # 其他域词否决优先于会员域短语
    ("怎么入会", False),      # 路由内表未收此条
])
def test_should_route_member(q, expected):
    assert MA.should_route_to_member_agent(q) is expected


# ---------- live_activity 纯函数 ----------
def test_is_subsequence():
    assert LA._is_subsequence("星展", "星际展览") is True
    assert LA._is_subsequence("展览", "展") is False

def test_norm_title_falsy_zero_is_empty():
    assert LA._norm_title(0) == ""
    assert LA._norm_title(None) == ""
    assert LA._norm_title("星巴克·咖啡") == "星巴克咖啡"
    assert LA._norm_title("  Hello World ") == "helloworld"

def test_weekend_dates_current_week_saturday():
    # 周五 → 本周六日（次日起）
    assert LA._weekend_dates(date(2026, 10, 23)) == [date(2026, 10, 24), date(2026, 10, 25)]
    # 周日 → 本周六为昨天
    assert LA._weekend_dates(date(2026, 10, 25)) == [date(2026, 10, 24), date(2026, 10, 25)]

def test_date_label():
    assert LA._date_label(date(2026, 10, 23)) == "10月23日（周五）"

def test_activity_keyword_keeps_chang_ci():
    assert LA._activity_keyword("梵高展详情") == "梵高展"
    assert LA._activity_keyword("看看场次安排") == "看看场次安排"  # 「场次」不剥离


# ---------- live_merchant 纯函数 ----------
def test_merchant_is_generic():
    assert LM._is_generic_category("咖啡") is True
    assert LM._is_generic_category("星巴克") is False

def test_merchant_keyword_category():
    assert LM._keyword("有哪些咖啡") == "咖啡"
    assert LM._keyword("星巴克营业时间") == "星巴克"


# ---------- official_* 静态成稿（字节级）----------
def test_official_parking_static():
    r = OI.answer_official_image_request("停车指引图")
    assert r.startswith("西岸梦中心设有 A/B/C/D 四个停车分区")
    assert "/knowledge-images/0c0a9ebacfcf89241129adb1c7636589.jpeg" in r

def test_official_restroom_static():
    assert "馆内共有 7 处卫生间标记" in OI.answer_official_image_request("洗手间在哪")

def test_official_none():
    assert OI.answer_official_image_request("你好") is None

def test_official_app_nav():
    r = OA.answer_official_app_request("怎么去西岸梦中心")
    assert "上海市徐汇区龙腾大道2266号" in r and "```nav" in r
    assert OA.answer_official_app_request("你好") is None
