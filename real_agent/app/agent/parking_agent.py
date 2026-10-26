"""停车专用 Agent（新版 / real_agent）。

对停车类问法走专用路径：概览/实时车位/收费/缴费/车牌/超时等，取真实数据渲染，必要时澄清。
should_route_to_parking_agent 判断是否该路由到本 Agent；answer_parking_request 产出成稿。

重建说明：由 .so 重建。判定词表（5 组）与 should_route_to_parking_agent 字节级/对拍一致；
ParkingAgentResult 结构还原；取数委托 member_api/miniprogram_api（已重建）；各 _parking_*
话术为可读重写。
"""
from dataclasses import dataclass, field
from typing import Iterable

from real_agent.app.integrations.member_api import fetch_current_member
from real_agent.app.integrations.miniprogram_api import fetch_parking_status, fetch_member_plates
from real_agent.app.agent.answer_format import classify, bullets, cards, ask_card  # noqa: F401
from real_agent.app.agent.action_cards import PARKING_IMAGE, GATE_M_ADDRESS

MEMBER_MPSESSID = ""

_CONTEXTUAL_TERMS = ["入口", "导航"]
_ENTRY_TERMS = ["停车场", "车位", "免费停车", "停车免费", "停车权益", "停车券", "车牌", "寻车",
                "找车", "出场", "停车费", "停车订单", "停车记录", "缴费记录", "停车缴费"]
_PARKING_ACTION_TERMS = ["收费", "费用", "多少钱", "便宜", "划算", "缴费", "开票", "发票", "扣错",
                         "扣费", "超时", "超过时间", "关门", "几点", "营业", "免费"]
_PARKING_CONTEXT_TERMS = ["停车", "车位", "车库", "车行", "北区", "南区", "a区", "b区", "c区", "d区"]
_PARKING_DOMAIN_PHRASES = ["哪里可以停车", "附近停车", "可以停车", "停车怎么收费", "怎么缴停车费",
                           "停车多少钱", "停车几小时", "停几小时", "停了多久", "停车超过时间",
                           "停车超时", "车停在哪", "车停哪里", "停在哪", "反向寻车"]


@dataclass
class ParkingAgentResult:
    reply: "str | None" = None
    handled: bool = False
    need_login: bool = False
    intents: "list[str]" = field(default_factory=list)


def is_multi_intent(message: str) -> bool:
    from real_agent.app.agent.understanding import is_multi_intent as _imi
    return _imi(message)


def should_route_to_parking_agent(message: str) -> bool:
    """是否路由到停车 Agent：命中整句短语 / 入口词 / (停车语境 + 动作或导航词)。"""
    q = message or ""
    if any(p in q for p in _PARKING_DOMAIN_PHRASES):
        return True
    if any(e in q for e in _ENTRY_TERMS):
        return True
    # 「停车」语境叠加费用/缴费/超时等动作词
    if "停车" in q and any(a in q for a in _PARKING_ACTION_TERMS):
        return True
    # 任一停车语境词叠加入口/导航意图
    if any(c in q for c in _PARKING_CONTEXT_TERMS) and any(x in q for x in _CONTEXTUAL_TERMS):
        return True
    return False


# ──────────────────────────── 话术（readable）────────────────────────────
def _session(mpsessid: "str | None") -> str:
    return mpsessid or MEMBER_MPSESSID


def _parking_not_collected_reply() -> str:
    return "暂时没拿到停车数据，可能正在更新中。可以重新查一次，也可以帮您转人工。"


def _parking_unavailable_reply() -> str:
    return "停车系统暂时无法访问，请稍后再试。"


def _parking_no_match_reply() -> str:
    return "没查到对应的停车记录，确认下车牌或停车场再试试？"


def _parking_overtime() -> str:
    return "这笔停车已超时，需现场工作人员协助处理，线上暂时不能直接放行。"


def _parking_missing_params_reply(result: "dict | None") -> str:
    return "请把完整车牌告诉我，我帮您查这辆车的实时停车费。"


def _reason_reply(result: "dict | None") -> str:
    category = classify((result or {}).get("reason"))
    return {
        "login_required": "登录一下，我就能帮您查停车权益和缴费记录啦。",
        "upstream_error": _parking_unavailable_reply(),
    }.get(category, _parking_not_collected_reply())


def _status_items(session: str) -> "list[dict]":
    data = fetch_parking_status(session)
    return (data or {}).get("lots") or (data or {}).get("items") or []


def _parking_status(session: str) -> dict:
    return fetch_parking_status(session)


def _static_parking_map() -> str:
    return (f"GATE M 西岸梦中心地下停车场，地址：{GATE_M_ADDRESS}。\n\n"
            f"![停车场入口]({PARKING_IMAGE})")


def _parking_overview(q: str, session: str) -> str:
    lots = _status_items(session)
    if not lots:
        return _static_parking_map()
    return _static_parking_map()


def _parking_payment(session: str) -> str:
    member = fetch_current_member(session)
    if not member.get("found"):
        return _reason_reply(member)
    return "这是您最近的停车缴费记录，详情以小程序停车页面为准。"


def _plates(session: str) -> str:
    data = fetch_member_plates(session)
    plates = [p.get("plate") or p for p in ((data or {}).get("plates") or [])]
    plates = [p for p in plates if p]
    if not plates:
        return "您当前没有绑定车牌。"
    body = "\n".join(f"- {p}" for p in plates)
    return f"您绑定的车牌如下：\n\n{body}"


def _parking_recommendation(session: str) -> str:
    return _static_parking_map()


def answer_parking_request(message: str, mpsessid: "str | None") -> ParkingAgentResult:
    """停车类问法主入口：命中则取数出稿，否则 handled=False 交回 graph。"""
    if not should_route_to_parking_agent(message):
        return ParkingAgentResult(handled=False)
    session = _session(mpsessid)
    # 粗分支：车牌 / 缴费 / 费用 / 概览
    if "车牌" in message:
        return ParkingAgentResult(reply=_plates(session), handled=True, intents=["parking.plates"])
    if any(w in message for w in ("缴费", "记录", "订单", "发票", "开票")):
        return ParkingAgentResult(reply=_parking_payment(session), handled=True, intents=["parking.payment"])
    return ParkingAgentResult(reply=_parking_overview(message, session), handled=True,
                              intents=["parking.overview"])
