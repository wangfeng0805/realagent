"""会员问答直达 Agent（新版 / real_agent）。

对会员类问法（积分/等级/券/成长值/升级/生日/手机号等）走专用快路径：先用
should_route_to_member_agent 判断是否属于会员域，命中则取会员数据 + 渲染成稿，必要时
带澄清/登录引导；返回 MemberAgentResult（成稿 + 是否命中 + 是否需登录 + 命中意图）。

重建说明：由 .so 重建。
  - 常量（LOGIN_REQUIRED/MISSING_PARAMS/NO_MATCH/UPSTREAM_ERROR/UNKNOWN_VALUE、
    _ENTRY_TERMS/_PERSONAL_TERMS/_PERSONAL_PHRASES/_MEMBER_DOMAIN_PHRASES/_OTHER_DOMAIN_TERMS、
    _LEVEL_THRESHOLDS）字节级还原；
  - **should_route_to_member_agent 与 .so 对拍一致**（规则见该函数）：先用「其他域词」否决，
    再按「会员域短语 / 个人资料短语 / 个人代词×会员词同现」判定；
  - MemberAgentResult 结构、入口签名还原；
  - answer_member_request 为**结构忠实重建**：按命中的个人/会员意图取数（member_api 已字节级重建）
    并用 table_format 渲染，离线无真实数据时回落到 UNKNOWN_VALUE/登录引导；其渲染文案绑定线上
    会员接口字段，离线无法逐字对拍，故此处为装配点，路由与结构忠实于 .so。
"""
import re
from contextvars import ContextVar
from dataclasses import dataclass, field

from real_agent.app.integrations.member_api import fetch_current_member
from real_agent.app.integrations.miniprogram_api import (
    fetch_coupon_count, fetch_expiring_points, fetch_next_level_progress,
)
from real_agent.app.agent.table_format import key_value_table, markdown_table  # noqa: F401
from real_agent.app.agent.answer_format import classify, bullets, cards, ask_card  # noqa: F401

LOGIN_REQUIRED = "login_required"
MISSING_PARAMS = "missing_params"
NO_MATCH = "no_match"
UPSTREAM_ERROR = "upstream_error"
UNKNOWN_VALUE = "暂未收录"
MEMBER_MPSESSID = ""

# 会员域「入口词」：出现任一才可能属于会员域（需与个人代词同现）。
_ENTRY_TERMS = ("会员", "积分", "成长值", "权益", "优惠券", "券", "等级", "升级", "保级", "生日", "手机号")
# 个人代词：问的是「当前登录用户自己」。
_PERSONAL_TERMS = ("我", "当前", "现在", "本人", "自己")
# 个人资料短语：单独出现即属于会员个人查询。
_PERSONAL_PHRASES = ("会员信息", "会员资料", "升级进度", "到期积分", "过期积分", "积分余额", "券数量")
# 会员域规则短语：单独出现即属于会员域（规则类，不一定问自己）。
_MEMBER_DOMAIN_PHRASES = (
    "怎么升级会员", "会员怎么升级", "升级会员", "我能保级", "保级吗", "保级规则", "积分怎么获得",
    "积分怎么攒", "积分规则", "积分有什么用", "积分怎么用", "积分什么时候过期", "积分有效期",
    "优惠券为什么用不了", "优惠券可以叠加", "会员码打不开", "会员码扫不出来", "权益为什么没到账",
    "会员权益为什么没到账", "怎么注册会员", "怎么入会", "会员生日", "生日福利", "消费后为什么没积分",
    "为什么没积分", "会员等级降了", "等级降了", "优惠券什么时候到账", "券什么时候到账",
    "会员手机号可以换", "手机号可以换", "换绑手机号", "换手机号",
)
# 其他域词：出现任一则**否决**会员路由（交停车/商城等处理）。
_OTHER_DOMAIN_TERMS = ("停车", "车牌", "商城")

# should_route 实际匹配的会员域短语子集：与导出的 _MEMBER_DOMAIN_PHRASES 一致，但路由判定
# 不含「怎么入会」（.so 的路由内表未收该条；导出常量仍保留它供他处使用）。
_ROUTING_PHRASES = tuple(p for p in _MEMBER_DOMAIN_PHRASES if p != "怎么入会")

# 会员等级门槛（成长值）。
_LEVEL_THRESHOLDS = {"WeM1": 0, "WeM2": 500, "WeM3": 2000, "WeM4": 5000}

# 本轮工具调用结果（供步骤事件/日志用）。
_TOOL_RESULTS: "ContextVar" = ContextVar("member_agent_tool_results", default=[])


@dataclass
class MemberAgentResult:
    reply: "str | None" = None       # 渲染好的成稿（未命中为 None）
    handled: bool = False            # 是否由会员快路径处理
    need_login: bool = False         # 是否需要先登录
    intents: "list[str]" = field(default_factory=list)


def is_multi_intent(message: str) -> bool:
    """是否多意图（委托 understanding，与 parking_agent 同源）。"""
    from real_agent.app.agent.understanding import is_multi_intent as _imi
    return _imi(message)


def should_route_to_member_agent(message: str) -> bool:
    """是否路由到会员 Agent（与 .so 对拍）。

    规则（短路顺序）：
    1. 命中任一「其他域词」（停车/车牌/商城）→ 直接否决 False（哪怕同时含会员域短语）；
    2. 命中任一「会员域规则短语」→ True；
    3. 命中任一「个人资料短语」→ True；
    4. 同时含「个人代词」与「会员入口词」→ True；
    5. 否则 False。
    """
    q = message or ""
    if any(t in q for t in _OTHER_DOMAIN_TERMS):
        return False
    if any(p in q for p in _ROUTING_PHRASES):
        return True
    if any(p in q for p in _PERSONAL_PHRASES):
        return True
    if any(t in q for t in _PERSONAL_TERMS) and any(e in q for e in _ENTRY_TERMS):
        return True
    return False


# ───────────────────── 取数 / 工具（readable 装配点）─────────────────────
def _session(mpsessid: "str | None") -> str:
    return mpsessid or MEMBER_MPSESSID


def _number(value: "object") -> str:
    """数值转展示字符串（与 .so 一致：直接 str(value)）。"""
    return str(value)


def _norm(text: "object") -> str:
    return str(text or "").strip()


def _record_tool_result(name: str, result: "object") -> None:
    try:
        _TOOL_RESULTS.get().append({"tool": name, "result": result})
    except Exception:
        pass


def _fetch_current_member(session: str) -> dict:
    data = fetch_current_member(session)
    _record_tool_result("member_info", data)
    return data or {}


def _current_member(session: str) -> "tuple[dict | None, str | None]":
    """取当前会员资料。返回 (member, reason)；未登录/异常时 member=None 并给 reason。"""
    data = _fetch_current_member(session)
    if data.get("found"):
        return data, None
    return None, classify(data.get("reason"))


def _wem_level(member: dict) -> "tuple[str, str] | None":
    """从会员资料取等级 (code, label)；读规范化后的 member_level_name 字段。"""
    level = member.get("member_level_name")
    if not level:
        return None
    return level, level


def _level_label(member: dict) -> str:
    lv = _wem_level(member)
    return lv[1] if lv else UNKNOWN_VALUE


def _reason_reply(reason: "str | None") -> MemberAgentResult:
    """把失败原因映射为带登录/错误引导的结果。"""
    if reason == "login_required":
        return MemberAgentResult(reply="登录后我就能帮您查会员积分、等级和权益啦。",
                                 handled=True, need_login=True, intents=["member.login"])
    if reason == "upstream_error":
        return MemberAgentResult(reply="会员系统暂时无法访问，请稍后再试。",
                                 handled=True, intents=["member.error"])
    return MemberAgentResult(reply="暂时没查到您的会员信息，确认登录后再试试？",
                             handled=True, intents=["member.no_match"])


def _overview(member: dict) -> str:
    """会员总览成稿（结构忠实：读 member_api 规范化字段）。"""
    rows = [
        ("昵称", member.get("display_name") or UNKNOWN_VALUE),
        ("等级", _level_label(member)),
        ("积分", _number(member.get("points") or UNKNOWN_VALUE)),
        ("成长值", _number(member.get("effective_growth_value") or UNKNOWN_VALUE)),
        ("有效期", member.get("membership_end_time") or UNKNOWN_VALUE),
    ]
    return key_value_table(rows)


# ───────────────────────────── 主入口 ─────────────────────────────
def answer_member_request(message: str, mpsessid: "str | None") -> MemberAgentResult:
    """会员类问法快路径；未命中返回 handled=False，交回 graph。

    结构忠实重建：命中会员域后取当前会员资料；取到则渲染总览/积分/等级，取不到按原因
    回落登录/错误/未收录。细分意图（券/成长值/生日/规则等）的逐字文案依赖线上接口字段，
    为装配点。
    """
    if not should_route_to_member_agent(message):
        return MemberAgentResult(handled=False)

    session = _session(mpsessid)
    member, reason = _current_member(session)
    if member is None:
        return _reason_reply(reason)

    return MemberAgentResult(reply=_overview(member), handled=True, intents=["member.overview"])
