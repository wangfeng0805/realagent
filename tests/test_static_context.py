"""静态知识检索/注入的单元测试（static_context）。

跑法：在 real_agent_rebuild_NEW 目录下
    pytest tests/test_static_context.py -v
验证：文档加载、bigram 规则、评分/覆盖率/阈值、排序、以及注入模板与出处清洗。
"""
import pytest
from real_agent.app.agent import static_context as sc


def test_clean_only_strips_edges():
    assert sc._clean("  停车 收费  ") == "停车 收费"
    assert sc._clean(None) == ""


def test_bigrams_strip_all_whitespace():
    assert sc._bigrams("15 分钟") == sc._bigrams("15分钟") == ["15", "5分", "分钟"]


def test_bigrams_single_char_is_empty():
    assert sc._bigrams("停") == []
    assert sc._bigrams("") == []


def test_hit_parking_fee_rule():
    hits = sc.search_lexical_context("停车收费标准")
    assert hits
    assert hits[0]["source"] == "gate_m_real_miniprogram_knowledge"
    assert "首小时 10 元" in hits[0]["text"]
    assert hits[0]["exact"] is True
    assert hits[0]["coverage"] == 1.0


def test_coverage_threshold_blocks_partial_phrasing():
    assert sc.search_lexical_context("停车怎么收费") == []


def test_low_coverage_returns_none_for_long_query():
    assert sc.search_lexical_context("停车收费标准是多少钱一小时怎么算") == []


def test_k_caps_result_count():
    assert len(sc.search_lexical_context("积分", 1)) == 1
    assert len(sc.search_lexical_context("积分", 10)) == 10


def test_sorted_by_score_desc():
    hits = sc.search_lexical_context("会员停车权益规则")
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 6.0


def test_digit_cjk_boundary_bigram_kept():
    hits = sc.search_lexical_context("11号线")
    assert hits and hits[0]["score"] == 3.0 and hits[0]["coverage"] == 1.0


def test_irrelevant_query_returns_empty():
    assert sc.search_lexical_context("完全无关的问题xyz") == []
    assert sc.search_lexical_context("你好") == []


def test_build_none_when_no_hit():
    assert sc.build_static_knowledge_context("你好") is None
    assert sc.build_static_knowledge_context("停车怎么收费") is None


def test_build_wraps_with_header_and_suffix():
    ctx = sc.build_static_knowledge_context("停车收费标准")
    assert ctx.startswith("【本轮已命中的内部静态知识】\n- ")
    assert ctx.endswith("必须直接作答，禁止继续调用工具。")
    assert "首小时 10 元" in ctx
    assert "不得提及知识库、截图、检索或来源" in ctx


def test_build_strips_source_clause():
    ctx = sc.build_static_knowledge_context("停车收费标准")
    assert "来源：" not in ctx
    assert ".png`" not in ctx and ".jpeg`" not in ctx


@pytest.mark.parametrize("q", ["积分规则", "会员等级", "卫生间", "15分钟", "免费停车"])
def test_build_smoke_natural_queries(q):
    ctx = sc.build_static_knowledge_context(q)
    assert ctx is None or ctx.startswith("【本轮已命中的内部静态知识】")
