"""✅ 活动卡/商户卡（agent/response_formatter.py）。"""
from real_agent.app.agent.response_formatter import (
    render_program_list, render_merchant_list, render_merchant_detail)

def test_program_card_minprice_and_meta():
    out = render_program_list([{"name": "展览A", "startTime": "2026-10-01",
                                "endTime": "2026-12-31", "minPrice": 50}])
    assert "近期可以关注的活动有 **1 项**" in out
    assert '"meta": "10月1日-12月31日"' in out and '"price": "¥50"' in out

def test_program_no_start_no_meta():
    out = render_program_list([{"name": "A", "endTime": "2026-12-31"}])
    assert '"meta"' not in out            # 无 startTime 则不出 meta

def test_program_overflow_tail():
    items = [{"name": f"A{i}", "startTime": "2026-10-01"} for i in range(10)]
    assert "还有 2 项" in render_program_list(items)

def test_merchant_list_limit_and_total():
    import json
    items = [{"name": f"M{i}", "category": "餐饮"} for i in range(11)]
    out = render_merchant_list(items, None)
    payload = json.loads(out.split("\n")[1])
    assert payload["total"] == 11 and len(payload["shops"]) == 8

def test_merchant_detail_omits_absent():
    assert render_merchant_detail({"name": "星巴克"}) == "### 星巴克"
