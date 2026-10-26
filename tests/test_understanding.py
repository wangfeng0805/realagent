"""✅ 门控 should_route_direct（understanding.py）。纯逻辑。"""
from real_agent.app.agent.understanding import should_route_direct

def test_none_and_empty_route_direct():
    assert should_route_direct(None) is True
    assert should_route_direct({}) is True

def test_high_confidence_single_domain_direct():
    u = {"fallback_required": False, "ambiguity": "low",
         "tasks": [{"type": "member.points"}],
         "intents": [{"intent": "member", "confidence": 0.99}]}
    assert should_route_direct(u) is True

def test_route_direct_flag_blocks():
    # 真实门控：显式 route_direct=True 反而不直达（已对拍）
    assert should_route_direct({"route_direct": True}) is False
