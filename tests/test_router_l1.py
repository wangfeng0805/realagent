"""✅ L1 关键词路由（capabilities/router.py）。纯逻辑，无网络。"""
import pytest
from real_agent.app.capabilities.router import deterministic_intents

@pytest.mark.parametrize("q,expected", [
    ("我的积分还有多少", ["member.points"]),
    ("有哪些停车场", []),
    ("你好", []),
])
def test_deterministic_intents(q, expected):
    assert deterministic_intents(q) == expected
