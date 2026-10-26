"""✅ 两个判定函数（sport_suitability / parking_agent）。"""
import pytest
from real_agent.app.agent.sport_suitability import _is_sport_suitability
from real_agent.app.agent.parking_agent import should_route_to_parking_agent

@pytest.mark.parametrize("q,expected", [
    ("适合小孩的运动", True),
    ("这里能健身吗", True),
    ("有哪些运动场馆", False),     # 场馆列表查询 → 交票务/场馆工具
    ("预约篮球适合吗", False),     # 预约类排除
])
def test_sport(q, expected):
    assert _is_sport_suitability(q) is expected

@pytest.mark.parametrize("q,expected", [
    ("停车费多少", True),
    ("停车券", True),
    ("停车导航", True),
    ("我要停车", False),          # 停车语境但无动作/入口词
    ("积分多少", False),
])
def test_parking_route(q, expected):
    assert should_route_to_parking_agent(q) is expected
