"""空结果 / 未知信息的统一口径（代码层枚举 + 固定文案映射）。

上游工具/接口以 reason 码表达失败类型，这里统一归类并映射成顾客可见文案，
避免把未登录、接口故障都笼统说成“没有收录”。

说明：本文件由编译产物重建，枚举与文案表字节级还原，函数经随机对拍与原实现一致。
"""

NOT_COLLECTED = "not_collected"
NO_MATCH = "no_match"
LOGIN_REQUIRED = "login_required"
UPSTREAM_ERROR = "upstream_error"
MISSING_PARAMS = "missing_params"

UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"
NO_MATCH_REPLY = "暂未找到符合条件的结果。"

_REPLIES = {'not_collected': '当前小梦还没有收录相关的信息哦~', 'no_match': '暂未找到符合条件的结果。', 'login_required': '登录状态已失效或尚未登录，请登录「西岸梦中心」小程序后再查询。', 'upstream_error': '当前查询暂时失败，请稍后再试。', 'missing_params': '还需要确认：{detail}。'}

_REASON_MAP = {'missing_context': 'missing_params', 'missing_session': 'login_required', 'invalid_or_expired_session': 'login_required', 'upstream_unavailable': 'upstream_error', 'upstream_rejected': 'upstream_error', 'unsupported_response_shape': 'upstream_error', 'endpoint_not_allowed': 'not_collected', 'empty_member': 'not_collected', 'invalid_product_type': 'missing_params', 'invalid_filter': 'missing_params', 'invalid_query': 'missing_params', 'invalid_date': 'missing_params', 'invalid_route_id': 'missing_params'}

_TERMINAL = {'login_required', 'upstream_error', 'missing_params'}

_SOFT_UNKNOWN_TEXTS = {'暂未找到符合条件的结果。', '当前小梦还没有收录相关的信息哦~'}


def classify(reason: "str | None") -> str:
    if not reason:
        return NOT_COLLECTED
    return _REASON_MAP.get(reason, NOT_COLLECTED)


def reply_for(category: str, detail: "str | None" = None) -> str:
    template = _REPLIES.get(category, UNKNOWN_REPLY)
    if category == MISSING_PARAMS:
        return template.format(detail=detail or "还缺少必要信息")
    return template


def result_reply(result: "dict | None", *, default: str = "not_collected", detail: "str | None" = None) -> str:
    data = result or {}
    reason = data.get("reason", default)
    category = classify(reason)
    if category == MISSING_PARAMS:
        detail = data.get("missing_required") or detail
    return reply_for(category, detail)


def is_terminal(category: str) -> bool:
    return category in _TERMINAL


def is_soft_unknown(text: "str | None") -> bool:
    return bool(text) and text in _SOFT_UNKNOWN_TEXTS
