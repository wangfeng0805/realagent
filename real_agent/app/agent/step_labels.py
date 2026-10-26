"""流式步骤 / 工具调用的可读标签（新版 / real_agent）。

chat_stream 把 ReActAgent 的每一步工具调用渲染成前端步骤条时，用这里的中文标签与脱敏逻辑：
- tool_label(name) / tool_detail(name)：工具英文名 → 顾客可读的「查询会员信息」「会员信息查询」；
- format_args：把工具入参压成一句短提示（脱敏、截断）；
- understanding_detail：把理解出的领域拼成「停车 · 会员」；
- tool_result_summary：把工具返回判成 done/empty/fail 三态 + 一句话；
- _redact / safe_tool_output：日志/调试里对敏感字段脱敏。

重建说明：本文件由新版编译产物（agent/step_labels.*.so）重建。
- _TOOL_LABELS(21)/_TOOL_DETAILS(21)/_DOMAIN_LABELS(14) 及各 hint/敏感键清单字节级还原；
- tool_label/tool_detail/understanding_detail/tool_result_summary/_redact 经对拍与原 .so 一致；
- format_args/safe_tool_output 为 readable 重写（多参展示细节 behavioral，仅影响步骤条文案长短）。
"""

import json

_DOMAIN_LABELS = {
    "parking": "停车", "member": "会员", "point_mall": "积分商城", "activity": "活动",
    "merchant": "商户", "product": "商品", "facility": "设施", "knowledge": "知识",
    "navigation": "导航", "transport": "交通", "ticket": "票务", "coupon": "优惠券",
    "recommendation": "推荐", "other": "综合",
}
_EMPTY_HINTS = ("没有收录", "暂未收录", "未查到", "没有查到", "暂时没有", "not found")
_ERROR_HINTS = ("upstream_unavailable", "upstream_rejected", "unsupported_response_shape", "失败")
_LOGIN_HINTS = ("invalid_or_expired_session", "missing_session", "登录")
_PRIMARY_ARG_KEYS = ("query", "keyword", "q", "path", "endpoint", "name", "category", "member_level")
_SECRET_ARG_KEYS = ("mpsessid", "session", "token", "cookie", "secret", "key", "user_id")
_SECRET_DETAIL_KEYS = ("mpsessid", "session", "token", "cookie", "secret", "key", "authorization")

_TOOL_LABELS = {
    "get_current_member_info": "查询会员信息", "get_current_activities": "查询最新活动",
    "get_point_mall_products": "查询积分商城", "get_member_upgrade_progress": "查询升级进度",
    "get_member_expiring_points": "查询到期积分", "get_member_coupon_count": "查询优惠券",
    "get_member_bound_plates": "查询绑定车牌", "get_member_point_records": "查询积分明细",
    "get_miniprogram_parking_status": "查询实时车位", "get_free_parking_hours": "查询停车权益",
    "get_parking_map": "查询停车分布", "get_westbund_shuttle_routes": "查询接驳线路",
    "search_miniprogram_merchants": "查询商户信息", "get_miniprogram_merchant_categories": "查询商户分类",
    "get_miniprogram_merchant_buildings": "查询商户楼栋", "search_mall_products": "查询商城商品",
    "get_rent_product_detail": "查询租赁详情", "get_rent_delivery_addresses": "查询租赁地址",
    "search_knowledge_base": "查找相关知识", "search_apis": "查找可调用工具", "call_api": "调用小程序接口",
}
_TOOL_DETAILS = {
    "get_current_member_info": "会员信息查询", "get_current_activities": "实时活动查询",
    "get_point_mall_products": "积分商城查询", "get_member_upgrade_progress": "会员升级查询",
    "get_member_expiring_points": "到期积分查询", "get_member_coupon_count": "优惠券查询",
    "get_member_bound_plates": "绑定车牌查询", "get_member_point_records": "积分明细查询",
    "get_miniprogram_parking_status": "实时车位查询", "get_free_parking_hours": "停车权益查询",
    "get_parking_map": "停车分布查询", "get_westbund_shuttle_routes": "接驳线路查询",
    "search_miniprogram_merchants": "小程序商户查询", "get_miniprogram_merchant_categories": "商户分类接口",
    "get_miniprogram_merchant_buildings": "商户楼栋接口", "search_mall_products": "商城商品查询",
    "get_rent_product_detail": "租赁商品详情接口", "get_rent_delivery_addresses": "租赁地址接口",
    "search_knowledge_base": "知识库检索", "search_apis": "可用工具检索", "call_api": "小程序实时只读接口",
}


def tool_label(name: "str | None") -> str:
    return _TOOL_LABELS.get(name, "查询数据")


def tool_detail(name: "str | None") -> str:
    return _TOOL_DETAILS.get(name, "园区数据")


def _redact(value: object) -> object:
    """递归把敏感字段的值替换成 ***。"""
    if isinstance(value, dict):
        return {k: ("***" if k in _SECRET_DETAIL_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def format_args(raw_args: "str | None", limit: int = 70) -> str:
    """把工具入参压成一句短提示（脱敏 + 截断）。"""
    if not raw_args:
        return ""
    try:
        data = json.loads(raw_args)
    except Exception:
        return raw_args
    if not isinstance(data, dict):
        return str(data) if data is not None else ""
    vals = [str(v) for k, v in data.items() if k not in _SECRET_ARG_KEYS and v not in (None, "")]
    text = ", ".join(vals)
    return text if len(text) <= limit else text[:limit] + "…"


def understanding_detail(understanding: "dict | None") -> str:
    """把理解出的领域拼成「停车 · 会员」。"""
    domains = (understanding or {}).get("domains") or []
    # "other"（综合）域不展示
    return " · ".join(_DOMAIN_LABELS.get(d, d) for d in domains if d != "other")


def _count_items(payload: object) -> "int | None":
    """从返回里数出条目数（items/rows/list 任一，或本身是列表）。"""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), (dict, list)) else payload
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for key in ("items", "rows", "list", "records"):
                if isinstance(data.get(key), list):
                    return len(data[key])
    return None


def tool_result_summary(content: object) -> "tuple[str, str]":
    """把工具返回判成三态：fail / empty / done，各配一句话。"""
    reason = ""
    if isinstance(content, dict):
        reason = str(content.get("reason") or "")
    if any(h in reason for h in _ERROR_HINTS):
        return "fail", "暂时没有获取到数据"
    if any(h in reason for h in _EMPTY_HINTS):
        return "empty", "没有可用结果"
    return "done", "已获取相关信息"


def safe_tool_output(content: object, limit: int = 1200) -> str:
    """把工具返回安全序列化（脱敏 + 截断），用于调试展示。"""
    try:
        text = json.dumps(_redact(content), ensure_ascii=False, indent=2)
    except Exception:
        text = str(content)
    return text if len(text) <= limit else text[:limit] + "…"
