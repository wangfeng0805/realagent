"""✅ 后处理三件套。"""
from real_agent.app.agent.customer_reply import sanitize_customer_reply
from real_agent.app.agent.action_cards import append_action_cards, trailing_action_cards
from real_agent.app.agent.exception_reply import reply_for

def test_sanitize_strips_source_prefix():
    assert sanitize_customer_reply("根据截图可知，停车费30元。") == "停车费30元。"

def test_append_cards_suppress_same_question():
    # 卡片的 action.q 与问句相同则不建议
    assert trailing_action_cards("X", "我有多少积分", ["member"]) == ""

def test_append_cards_nav_fallback():
    out = append_action_cards("X", "停车场入口怎么走", None)
    assert "```nav" in out

def test_append_cards_blank_answer_no_cards():
    assert append_action_cards("", "有哪些停车场", None) == ""

def test_exception_reply_unknown_falls_back():

    assert "暂时没拿到最新结果" in reply_for("no_data")

def test_exception_reply_retry_card_on_question():
    out = reply_for("upstream_timeout", question="停车费多少")
    assert '"重新查询"' in out and '"q": "停车费多少"' in out
