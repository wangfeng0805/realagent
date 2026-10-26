"""顾客回答的稳定渲染器（代码模板优先，取代 LLM 自由排版）（新版 / real_agent）。

把商户/活动等结构化结果渲染成前端可识别的卡片块：
- 活动用 ```cards（图文卡片列表）；
- 商户列表用 ```shops（前端按卡片式要点渲染，最多 8 条）；
- 商户详情用「### 名称 + 要点行」。
按钮与字段不交给模型，避免漏按钮/编造；缺字段统一「暂未收录」。

说明：本文件由新版编译产物重建。所有模板/文案字节级还原，渲染函数经随机对拍与原实现一致。
"""

import json
from typing import Any

_EMPTY = "暂未收录"
_MERCHANT_LIST_LIMIT = 8


def _clean(value: Any) -> "str | None":
    """去空白；空值返回 None。"""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _nice_location(value: str) -> str:
    """位置展示（原样保留，仅清洗空白）。"""
    return _clean(value) or _EMPTY


def _program_period(start: "str | None", end: "str | None") -> "str | None":
    """把起止日期渲染成「M月D日-M月D日」；只有开始则只给开始。"""
    def fmt(s):
        s = _clean(s)
        if not s:
            return None
        m = s.split("-")
        if len(m) >= 3:
            try:
                return f"{int(m[1])}月{int(m[2][:2])}日"
            except ValueError:
                return s
        return s
    a = fmt(start)
    if not a:
        return None  # 无开始时间则不展示时段（仅有结束时间不单独成稿）
    b = fmt(end)
    return f"{a}-{b}" if b else a


def render_program_list(items: "list[dict]", limit: int = 8) -> str:
    """活动/演出列表 → ```cards 图文卡片。"""
    cards = []
    for item in items[:limit]:
        title = _clean(item.get("name")) or "活动"
        card = {"title": title}
        meta = _program_period(item.get("startTime"), item.get("endTime"))
        if meta:
            card["meta"] = meta
        min_price = item.get("minPrice")
        if min_price:
            card["price"] = f"¥{min_price}"
        card["action"] = {"label": "了解详情", "q": f"{title} 活动详情"}
        cards.append(card)
    body = json.dumps(cards, ensure_ascii=False)
    out = f"近期可以关注的活动有 **{len(items)} 项**：\n\n```cards\n{body}\n```"
    extra = len(items) - limit
    if extra > 0:
        out += f"\n\n还有 {extra} 项，告诉我想看的类型或日期，我帮您筛选。"
    return out


def render_merchant_list(items: "list[dict]", total: "int | None" = None, limit: int = 8) -> str:
    """商户列表 → ```shops 卡片块（最多 limit 条）。"""
    shops = []
    for item in items[:limit]:
        shop = {"name": _clean(item.get("name")) or "未命名商户"}
        cat = _clean(item.get("category"))
        if cat:
            shop["category"] = cat
        loc = _clean(item.get("location"))
        if loc:
            shop["location"] = loc
        shop["hours"] = _clean(item.get("business_hours")) or "营业时间暂未收录"
        shops.append(shop)
    payload = {"total": total if total is not None else len(items), "shops": shops}
    return "```shops\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def render_merchant_detail(item: dict) -> str:
    """单个商户详情 → 「### 名称 + 要点行」。"""
    name = _clean(item.get("name")) or "该商户"
    lines = [f"### {name}"]
    cat = _clean(item.get("category"))
    if cat:
        lines.append(f"- 类型：{cat}")
    hours = _clean(item.get("business_hours"))
    if hours:
        lines.append(f"- 营业时间：{hours}")
    phone = _clean(item.get("phone"))
    if phone:
        lines.append(f"- 联系方式：{phone}")
    return "\n".join(lines)
