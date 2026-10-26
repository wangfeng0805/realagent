"""工具结果的「未取到」话术分类（新版 / real_agent）。

把工具返回的 reason 归成三类（未采集 / 上游异常 / 需登录），再由 reason_reply 选对应话术。
与 action_cards 共用 ask_card/bullets/cards/suggest 的卡片编码。

重建说明：由 .so 重建；classify/reason_reply 及常量经对拍与原 .so 一致。
"""
import json
from typing import Iterable

UNKNOWN_VALUE = "暂未收录"
MISSING_PARAMS = "missing_params"
NOT_COLLECTED = "not_collected"

# reason 归类（精确匹配 reason code，非子串）
_LOGIN_CODES = {"invalid_or_expired_session", "missing_session"}
_ERROR_CODES = {"upstream_unavailable", "upstream_rejected", "unsupported_response_shape"}


def classify(reason: "str | None") -> str:
    """把 reason 归成 login_required / upstream_error / not_collected 三类（精确匹配）。"""
    if reason in _LOGIN_CODES:
        return "login_required"
    if reason in _ERROR_CODES:
        return "upstream_error"
    return "not_collected"


def reason_reply(result: "dict | None", replies: "dict[str, str]") -> str:
    """按 result 的 reason 归类后，从 replies 里取对应话术（缺省回退 not_collected）。"""
    reason = (result or {}).get("reason") if isinstance(result, dict) else None
    category = classify(reason)
    return replies.get(category, replies.get(NOT_COLLECTED, ""))


# ──────────────────────────── 卡片编码（与 action_cards 一致）────────────────────────────
def ask_card(title: str, meta: str, label: str, question: str, icon: str = "") -> dict:
    return {"title": title, "meta": meta, "action": {"label": label, "q": question}, "icon": icon}


def bullets(rows: "Iterable[tuple[object, object]]") -> str:
    return "\n".join(f"- {k}：{v}" for k, v in rows)


def cards(items: "list[dict]") -> str:
    return "```cards\n" + json.dumps(items, ensure_ascii=False) + "\n```"


def suggest(items: "list[dict]") -> str:
    return "```suggest\n" + json.dumps(items, ensure_ascii=False) + "\n```"
