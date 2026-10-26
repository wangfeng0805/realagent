"""运动适宜性直达（新版 / real_agent）。

拦截「这里适合跑步吗/能健身吗/适合小孩运动吗」这类**运动适宜性**问法，取运动类商户 +
运动政策命中后渲染成稿；只问「有哪些场馆/订场」不在此拦截（交票务/预约工具）。

重建说明：由 .so 重建。词表（7 组）与 _is_sport_suitability 判定字节级/对拍一致；
取数(_fetch_*)与 _render 依赖运行时商户/政策数据，离线占位返回未命中(None)。
"""
from typing import Any

MEMBER_MPSESSID = ""

_SPORT_WORDS = ("运动", "锻炼", "健身", "跑步", "慢跑", "骑行", "滑板", "攀岩", "瑜伽")
_SUITABILITY_WORDS = ("适合", "适不适合", "能不能", "能否", "可以", "可不可以", "方便", "友好", "怎么样", "行不行", "值得")
_VENUE_WORDS = ("场馆", "球场", "场地")
_VENUE_QUERY_WORDS = ("有哪些", "哪些", "空位", "余位", "有没有位", "还有位", "剩余")
_BOOKING_WORDS = ("预约", "预订", "订场", "订球场", "订场地", "报名", "抢票")
_SPORT_TAGS = ("运动", "滑板", "攀岩", "健身", "瑜伽", "篮球", "网球", "羽毛球", "骑行", "滑冰", "游泳", "拳击", "跑步")
_SPORT_SUIT_PHRASES = (
    "能运动", "能锻炼", "能健身", "能跑步", "能慢跑", "能骑行", "能滑板", "能攀岩", "能瑜伽",
    "可运动", "可锻炼", "可健身", "可跑步", "可慢跑", "可骑行", "可滑板", "可攀岩", "可瑜伽",
    "会运动", "会锻炼", "会健身", "会跑步", "会慢跑", "会骑行", "会滑板", "会攀岩", "会瑜伽",
)


def _is_sport_suitability(query: str) -> bool:
    """是否「运动适宜性」问法：预约类排除；命中运动适宜短语，或（适宜词 + 运动词）同现。"""
    q = query or ""
    if any(b in q for b in _BOOKING_WORDS):
        return False
    # 「有哪些场馆/场地空位」这类场馆列表查询（venue 词 + 查询词同现）交票务/场馆工具，不算适宜性
    if any(v in q for v in _VENUE_WORDS) and any(vq in q for vq in _VENUE_QUERY_WORDS):
        return False
    if any(p in q for p in _SPORT_SUIT_PHRASES):
        return True
    return any(s in q for s in _SUITABILITY_WORDS) and any(w in q for w in _SPORT_WORDS)


def fetch_merchants(mpsessid: str = "", query: str = "", category: str = "",
                    limit: int = 10, tags: "list[str] | None" = None) -> dict:
    """取运动类商户（委托小程序商户接口）。"""
    from real_agent.app.integrations.miniprogram_api import fetch_merchants as _fm
    return _fm(mpsessid, query=query, category=category, limit=limit, tags=tags)


def _fetch_sport_merchants(session: str) -> "list[dict]":
    data = fetch_merchants(session, tags=list(_SPORT_TAGS), limit=10)
    return (data or {}).get("merchants") or (data or {}).get("items") or []


def _fetch_sport_policy() -> "list[dict]":
    """运动相关政策/须知（静态知识）。离线占位返回空。"""
    return []


def _render(merchants: "list[dict]", policy_hits: "list[dict]") -> str:
    """把运动商户 + 政策命中渲染成稿（readable；细节依赖数据）。"""
    from real_agent.app.agent.response_formatter import render_merchant_list
    return render_merchant_list(merchants)


def answer_sport_suitability_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中运动适宜性问法则取数渲染，否则 None。"""
    if not _is_sport_suitability(message):
        return None
    merchants = _fetch_sport_merchants(mpsessid or MEMBER_MPSESSID)
    if not merchants:
        return None
    return _render(merchants, _fetch_sport_policy())
