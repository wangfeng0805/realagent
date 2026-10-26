"""积分商城直达 live_point_mall（新版 / real_agent）。

拦截「积分商城有什么 / 能兑换什么 / 可以兑换什么」这类积分商城**实时商品**问法：取实时可兑换
商品渲染；需登录时回落登录引导；不命中返回 None 交回 graph。

重建说明：由 .so 重建。常量 UNKNOWN_REPLY / LOGIN_REQUIRED 字节级；取数委托
point_mall_api / miniprogram_api，渲染委托 key_value_table / markdown_table。触发关键词集与
成稿文案为**结构忠实重建**（偏保守）；商品渲染绑定线上字段，离线无数据时回落 None/登录引导。
"""
import re  # noqa: F401

from real_agent.app.integrations.point_mall_api import fetch_point_products
from real_agent.app.agent.table_format import key_value_table, markdown_table

LOGIN_REQUIRED = "login_required"
MEMBER_MPSESSID = ""
UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"

# 触发：积分商城实时商品问法（偏保守，避免拦到「积分规则/积分怎么用」等走 member_agent 的问法）。
_MALL_CUES = ("积分商城", "能兑换什么", "可以兑换什么", "能换什么礼品", "有什么可以兑换", "商城有什么")


def _product_keyword(query: str) -> str:
    """去掉列表语气后的商品关键词。"""
    q = query or ""
    for w in ("有哪些", "有什么", "有没有", "可以兑换", "能兑换", "兑换", "积分商城"):
        q = q.replace(w, "")
    return q.strip()


def _products(data: "dict | None") -> "list[dict]":
    return (data or {}).get("redeemable") or (data or {}).get("products") or (data or {}).get("items") or []


def _product_detail(item: dict) -> str:
    rows = [("名称", item.get("name") or UNKNOWN_REPLY),
            ("所需积分", str(item.get("points") if item.get("points") is not None else UNKNOWN_REPLY))]
    return key_value_table(rows)


def reply_for(reason: "str | None") -> "str | None":
    if reason == LOGIN_REQUIRED:
        return "登录后就能帮您查积分商城可兑换的商品啦。"
    return None


def answer_live_point_mall_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中积分商城实时商品问法时返回成稿；否则 None。"""
    q = message or ""
    if not any(c in q for c in _MALL_CUES):
        return None
    session = mpsessid or MEMBER_MPSESSID
    data = fetch_point_products(session, query=_product_keyword(q))
    reason = (data or {}).get("reason")
    if reason:
        return reply_for(reason)
    items = _products(data)
    if not items:
        return None
    rows = [(it.get("name") or "—", str(it.get("points") if it.get("points") is not None else "—"))
            for it in items]
    return "积分商城当前可兑换：\n\n" + markdown_table(["商品", "所需积分"], rows)
