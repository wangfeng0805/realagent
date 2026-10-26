"""会员实时直达 live_member（新版 / real_agent）。

会员**个人**实时问法（我的积分 / 积分余额 / 我的成长值 / 到期积分 / 我有几张券 / 我的车牌 /
我的会员信息）的快路径：取当前会员资料并渲染；未登录/取不到时回落登录引导或 UNKNOWN_REPLY；
不命中返回 None，交回 graph（随后还有 member_agent 处理更广的会员域问法）。

重建说明：由 .so 重建。常量 UNKNOWN_REPLY 字节级；纯函数 _number（str(value)）/_wem_level
（读规范化字段 member_level_name，返回 (级别, 级别)，无则 None）与 .so 对拍一致。取数委托
member_api / miniprogram_api（已重建），渲染委托 table_format。触发短语集与成稿文案为
**结构忠实重建**（偏保守）；个人资料渲染绑定线上会员字段，离线无数据时回落登录/UNKNOWN。
"""
import re  # noqa: F401

from real_agent.app.integrations.member_api import fetch_current_member
from real_agent.app.integrations.miniprogram_api import (
    fetch_coupon_count, fetch_expiring_points, fetch_next_level_progress, fetch_member_plates,
)
from real_agent.app.agent.table_format import key_value_table, markdown_table  # noqa: F401
from real_agent.app.agent.answer_format import classify  # noqa: F401

MEMBER_MPSESSID = ""
UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"

# 个人实时触发短语（结构忠实；与 .so 实测命中集一致，偏保守）。
_LIVE_PHRASES = ("我的积分", "积分余额", "我的成长值", "到期积分", "过期积分",
                 "我的车牌", "我有几张券", "我的会员信息")


def _session(mpsessid: "str | None") -> str:
    return mpsessid or MEMBER_MPSESSID


def _number(value: "object") -> str:
    """数值转展示串（与 .so 一致：str(value)）。"""
    return str(value)


def _wem_level(member: dict) -> "tuple[str, str] | None":
    """取会员等级 (级别, 级别)；读规范化字段 member_level_name，无则 None。"""
    level = member.get("member_level_name")
    if not level:
        return None
    return level, level


def _current_member(session: str) -> "tuple[dict | None, str | None]":
    data = fetch_current_member(session) or {}
    if data.get("found"):
        return data, None
    return None, classify(data.get("reason"))


def _failure(result: dict) -> str:
    """把失败原因映射为登录引导/错误提示。"""
    reason = classify((result or {}).get("reason"))
    return {
        "login_required": "登录后我就能帮您查会员积分、等级和车牌啦。",
        "upstream_error": "会员系统暂时无法访问，请稍后再试。",
    }.get(reason, UNKNOWN_REPLY)


def _member_benefits(member: dict) -> str:
    """会员个人资料成稿（结构忠实；读 member_api 规范化字段）。"""
    lv = _wem_level(member)
    rows = [
        ("昵称", member.get("display_name") or UNKNOWN_REPLY),
        ("等级", lv[1] if lv else UNKNOWN_REPLY),
        ("积分", _number(member.get("points") if member.get("points") is not None else UNKNOWN_REPLY)),
        ("成长值", _number(member.get("effective_growth_value")
                        if member.get("effective_growth_value") is not None else UNKNOWN_REPLY)),
        ("有效期", member.get("membership_end_time") or UNKNOWN_REPLY),
    ]
    return key_value_table(rows)


def result_reply(member: dict) -> str:
    return _member_benefits(member)


def answer_live_member_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中会员个人实时问法时返回成稿；否则 None。"""
    q = message or ""
    if not any(p in q for p in _LIVE_PHRASES):
        return None
    session = _session(mpsessid)
    data = fetch_current_member(session) or {}
    if not data.get("found"):
        return _failure(data)
    return _member_benefits(data)
