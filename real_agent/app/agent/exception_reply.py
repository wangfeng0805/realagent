"""异常/边界场景的标准话术（新版 / real_agent）。

当查询超时、查不到数据、未登录、规则冲突、不可逆操作等场景发生时，统一产出
「一句结论 + 要点列表 + 行动卡」的成稿，口吻克制、给下一步。reply_for(kind) 是入口，
graph/main 以别名 exception_reply 调用。

重建说明：本文件由新版编译产物（agent/exception_reply.*.so）重建。
- _TEXTS(9) / _DETAILS(8) / 各场景行动卡 / 客服电话 字节级还原；
- reply_for / bullets / cards / ask_card 经对拍与原 .so 一致（未知 kind 回退 no_data 文案；
  传入 options 覆盖默认卡片）。
"""

import json
from typing import Iterable

CUSTOMER_SERVICE_PHONE = "021-60707667"

# 场景常量
NOT_LOGGED_IN = "not_logged_in"
UPSTREAM_TIMEOUT = "upstream_timeout"
NO_DATA = "no_data"
STALE_DATA = "stale_data"
RULE_CONFLICT = "rule_conflict"
IRREVERSIBLE_OPERATION = "irreversible_operation"
EXIT_BLOCKED = "exit_blocked"
BENEFIT_PENDING = "benefit_pending"
UNCLEAR_INTENT = "unclear_intent"

# 每个场景的一句话结论
_TEXTS = {
    "not_logged_in": "登录一下，我就能帮您查会员等级、积分、停车权益和订单啦。",
    "upstream_timeout": "我这边暂时没查到最新结果，要不要再试一次？也可以先打开小程序的服务页面看看～",
    "no_data": "暂时没拿到最新结果，可能正在更新中。可以重新查一次，也可以帮您转人工。",
    "stale_data": "这份信息是 10 分钟前更新的，先给您做参考，要不要刷新一下？",
    "rule_conflict": "不同页面的规则好像不一致，我建议以当前页面展示为准；需要的话我帮您转人工确认。",
    "irreversible_operation": "这次兑换成功后就不能退回啦，确认要用积分兑换吗？",
    "exit_blocked": "先别着急，这笔停车订单需要现场工作人员帮您处理，线上暂时不能直接放行。",
    "benefit_pending": "权益正在同步中，通常几分钟就能看到；如果等了 30 分钟还没到，我帮您转人工处理。",
    "unclear_intent": "您说一下方向：是想查停车收费标准，还是想看看这次停车要付多少钱？",
}

# 每个场景的要点列表（(标题, 内容) 行）；not_logged_in / 无要点的场景不在此表
_DETAILS = {
    "upstream_timeout": [["目前结果", "这次没拿到最新数据"], ["下一步", "可以稍后重新查，或先打开小程序对应服务页面"], ["提示", "查询结果以小程序页面和现场为准"]],
    "no_data": [["目前结果", "这次没拿到最新结果，可能正在更新"], ["区分说明", "这不代表没有这项服务，也不代表一定没有数据"], ["下一步", "可以重新查询，或先查看停车场收费和入口信息"]],
    "stale_data": [["更新时间", "10 分钟前"], ["提示", "信息可先参考，实时变化以当前页面或现场为准"], ["下一步", "可以刷新一次"]],
    "rule_conflict": [["处理原则", "以当前页面展示为准"], ["提示", "不同页面规则不一致时，不按旧规则直接判断"], ["下一步", "可以查看页面，必要时转人工确认"]],
    "irreversible_operation": [["影响", "兑换成功后不能退回"], ["确认项", "是否使用积分兑换"], ["下一步", "确认后再继续"]],
    "benefit_pending": [["同步状态", "权益正在同步，通常几分钟到账"], ["下一步", "等几分钟重新查一次"], ["超时处理", "超过 30 分钟仍未到账就转人工"]],
    "exit_blocked": [["处理方式", "让停车场现场工作人员帮您放行"], ["客服中心电话", CUSTOMER_SERVICE_PHONE], ["先准备好", "车牌后 2-4 位、入场的停车场、支付凭证或订单截图"]],
    "unclear_intent": [["需要确认", "停车收费标准，或本次停车应缴金额"], ["下一步", "选一个方向，我再继续帮您查"]],
}


# ──────────────────────────── 卡片 ────────────────────────────
def ask_card(title: str, meta: str, label: str, question: str, icon: str = "") -> dict:
    return {"title": title, "meta": meta, "action": {"label": label, "q": question}, "icon": icon}


def _card(title: str, meta: str, label: str, q: str) -> dict:
    return {"title": title, "meta": meta, "action": {"label": label, "q": q}}


def _login_card() -> dict:
    return _card("立即登录", "登录后查看个人会员信息", "立即登录", "登录西岸梦中心小程序")


def _service_page_card() -> dict:
    return _card("服务页面", "打开小程序对应服务页查看", "打开服务页面", "打开服务页面")


def _service_card() -> dict:
    return _card("人工客服", "持续查不到时协助核对", "转人工", "转人工客服")


def _current_page_card() -> dict:
    return _card("当前页面", "以页面展示规则为准", "查看页面", "查看当前页面规则")


def _confirm_redeem_card() -> dict:
    return _card("确认兑换", "兑换成功后不可退回", "确认兑换", "确认使用积分兑换")


def _cancel_card() -> dict:
    return _card("取消", "先不继续本次操作", "取消", "取消兑换")


def _onsite_card() -> dict:
    return _card("现场工作人员", "停车出场问题现场处理更快", "联系现场工作人员", "联系现场工作人员")


def _parking_card() -> dict:
    return _card("收费标准", "查看停车收费规则", "收费标准", "停车收费标准")


def _retry_card(question: str, label: str = "重新查询") -> dict:
    return {"title": "重新查询", "meta": "刚才没拿到结果，可以再试一次",
            "action": {"label": label, "q": question}}


# 传入 question 时会前置「重新查询」卡的可重试场景（stale_data 的按钮文案不同）
_RETRY_KINDS = ("upstream_timeout", "no_data", "stale_data", "benefit_pending")


# 每个场景的默认行动卡（无卡的场景不在此表）
_CARDS = {
    "not_logged_in": [_login_card()],
    "upstream_timeout": [_service_page_card()],
    "no_data": [_service_card()],
    "rule_conflict": [_current_page_card(), _service_card()],
    "irreversible_operation": [_confirm_redeem_card(), _cancel_card()],
    "exit_blocked": [_onsite_card(), _service_card()],
    "benefit_pending": [_service_card()],
    "unclear_intent": [
        _parking_card(),
        _card("当前应缴", "查看这次停车费用", "当前应缴", "我这次停车要付多少钱"),
    ],
}


def bullets(rows: "Iterable[tuple[object, object]]") -> str:
    """要点列表：每行 "- 标题：内容"。"""
    return "\n".join(f"- {k}：{v}" for k, v in rows)


def cards(items: "list[dict]") -> str:
    return "```cards\n" + json.dumps(items, ensure_ascii=False) + "\n```"


# ──────────────────────────── 入口 ────────────────────────────
def reply_for(kind: str, *, question: "str | None" = None,
              options: "list[dict] | None" = None) -> str:
    """产出某场景的标准成稿：结论 +（要点）+（行动卡）。未知 kind 回退 no_data 文案。"""
    text = _TEXTS.get(kind)
    if text is None:
        return _TEXTS["no_data"]
    parts = [text]
    details = _DETAILS.get(kind)
    if details:
        parts.append(bullets(details))
    # options 仅用于「意图不明」场景的自定义选项卡；其余场景用各自默认卡
    if kind == UNCLEAR_INTENT and options:
        card_items = list(options)
    else:
        card_items = list(_CARDS.get(kind) or [])
    # 传入 question 的可重试场景，前置一张「重新查询」卡（stale_data 用「刷新数据」按钮）
    if question and kind in _RETRY_KINDS:
        label = "刷新数据" if kind == STALE_DATA else "重新查询"
        card_items = [_retry_card(question, label)] + card_items
    if card_items:
        parts.append(cards(card_items))
    return "\n\n".join(parts)


# graph / main 以 exception_reply 之名调用
exception_reply = reply_for
