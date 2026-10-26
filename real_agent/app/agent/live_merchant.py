"""商户直达 live_merchant（新版 / real_agent）。

拦截商户类问法：
  - **详情**：含 _DETAIL_WORDS（营业时间/几点开门/详情/怎么样…）→ 取该商户详情并渲染；
  - **列表**：问法落到某个「通用品类」（_CATEGORY_WORDS：咖啡/餐厅/火锅…）且带列表语气 →
    取该品类商户列表并渲染。
不命中返回 None，交回 graph 走 understand + ReActAgent。

重建说明：由 .so 重建。常量 _CATEGORY_WORDS / _DETAIL_WORDS / UNKNOWN_REPLY 字节级；纯函数
_keyword（返回问句中第一个出现的品类词，否则原句）/_detail_keyword（去掉 _DETAIL_WORDS 后 strip）/
_is_generic_category（是否通用品类）与 .so 对拍一致；取数委托 miniprogram_api.fetch_merchants
（session, keyword, limit=6），渲染委托已字节级重建的 render_merchant_list / render_merchant_detail。
answer_* 的列表触发为**结构忠实**：要求通用品类词 + 列表语气（偏保守，避免误拦），其余结构忠于 .so。
"""
import re  # noqa: F401

from real_agent.app.integrations.miniprogram_api import fetch_merchants
from real_agent.app.agent.response_formatter import render_merchant_list, render_merchant_detail

MEMBER_MPSESSID = ""
UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"

# 通用品类词（命中则按品类取列表）。
_CATEGORY_WORDS = ("咖啡", "餐厅", "餐饮", "火锅", "奶茶", "茶饮", "甜品", "面包", "酒吧", "亲子", "运动", "服装", "美食")
# 详情类词（命中则按商户名取详情）。
_DETAIL_WORDS = ("详情", "详细信息", "介绍", "了解", "怎么样", "营业时间", "几点开门", "几点关门")
# 列表语气线索（结构忠实：避免裸品类词误拦）。
_LIST_CUES = ("有哪些", "哪些", "有什么", "有没有", "推荐", "附近", "几家", "列表", "店", "都有")


def _keyword(query: str) -> str:
    """先去掉详情词，再取其中第一个通用品类词；没有品类词则返回去词后的问句。

    结构忠实：与 .so 一致先剥离详情词（"星巴克营业时间"→"星巴克"），再做品类提取
    （"有哪些咖啡"→"咖啡"）。详情词剥离集的个别边界（如「了解」）略有出入，不影响路由结构。
    """
    q = _detail_keyword(query)
    for w in _CATEGORY_WORDS:
        if w in q:
            return w
    return q


def _detail_keyword(query: str) -> str:
    """去掉所有 _DETAIL_WORDS 再 strip，得到用于取详情的商户名关键词。"""
    q = query or ""
    for w in _DETAIL_WORDS:
        q = q.replace(w, "")
    return q.strip()


def _is_generic_category(keyword: str) -> bool:
    return keyword in _CATEGORY_WORDS


def _merchant_detail(item: dict) -> str:
    """渲染单个商户详情（委托已重建的 render_merchant_detail）。"""
    return render_merchant_detail(item)


def _items(data: "dict | None") -> "list[dict]":
    return (data or {}).get("merchants") or (data or {}).get("items") or []


def answer_live_merchant_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中商户详情/列表问法时返回成稿；否则 None。"""
    session = mpsessid or MEMBER_MPSESSID
    message = message or ""

    # 详情：含详情词，且去掉后仍有商户名
    if any(w in message for w in _DETAIL_WORDS):
        name = _detail_keyword(message)
        if name:
            items = _items(fetch_merchants(session, name, limit=6))
            if items:
                return _merchant_detail(items[0])
        return None

    # 列表：通用品类词 + 列表语气
    kw = _keyword(message)
    if _is_generic_category(kw) and any(c in message for c in _LIST_CUES):
        items = _items(fetch_merchants(session, kw, limit=6))
        if items:
            return render_merchant_list(items)
    return None
