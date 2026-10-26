"""Deterministic renderers for capability fast-path answers（新版 / real_agent）。

把 capability 取到的原始 payload 渲染成顾客可见的中文成稿（结论先行 + 轻服务口吻）。
registry.execute() 在 direct_response=true 时调用 render(intent, payload)；渲染不出来
（返回 None 或未知兜底）则上层回退到大模型链路。

payload 形状：会员类取 payload["member"]；多数列表类取 payload["data"] 下的
items/rows/lots 等；缺字段统一显示 UNKNOWN_VALUE（"暂未收录"/"待确认"）。

重建说明：本文件由新版编译产物重建，面向「读懂逻辑 + 改模板」。
- 所有输出模板（成稿文案）为字节级还原；
- render() 的 intent→渲染器 分派表为还原的真实映射；
- member.info / member.points 两个渲染器已对原 .so 验证一致；
- 其余渲染器按「模板 + 调用轨迹里读取的字段」重写（readable），因各自依赖具体接口
  payload 形状、离线无法逐一对拍，细节字段若与实际接口不符，照模板对一下即可。
"""

from typing import Any

UNKNOWN_VALUE = "暂未收录"
_UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"


# ──────────────────────────── 通用小工具 ────────────────────────────
def _number(value: object) -> str:
    """数字友好展示：1200.0 → "1200"，非数字原样转字符串。"""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value) if value is not None else UNKNOWN_VALUE


def _walk_dicts(value: Any):
    """递归遍历嵌套结构里的所有 dict（用于从不规则 payload 里捞记录）。"""
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from _walk_dicts(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_dicts(v)


def _safe_count(value: Any) -> int:
    """从 int / 数字字符串 / 列表 推断数量。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return len(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _rows(value: Any) -> "list[dict]":
    """从 payload 的 data 里取出记录列表（items/rows/list/records 任一）。"""
    data = value.get("data") if isinstance(value, dict) else value
    if isinstance(data, dict):
        for key in ("items", "rows", "list", "records", "lots", "plates"):
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)] or data[key]
        # 没有明显列表键时，退化为遍历
        return [d for d in _walk_dicts(data)]
    if isinstance(data, list):
        return data
    return []


def _item_name(row: dict) -> str:
    for key in ("name", "couponName", "productName", "title", "programName"):
        if row.get(key):
            return str(row[key])
    return UNKNOWN_VALUE


def _validity(row: dict) -> str:
    """有效期区间："开始 至 结束"，字段名多来源兼容。"""
    start = row.get("startTime") or row.get("beginTime") or row.get("validStartTime")
    end = row.get("endTime") or row.get("expireTime") or row.get("validEndTime")
    if start and end:
        return f"{start} 至 {end}"
    return UNKNOWN_VALUE


# ──────────────────────────── 会员 ────────────────────────────
def _member(payload: dict) -> dict:
    """从 payload 里取会员数据：优先 payload["member"]，否则 payload["data"]。"""
    if isinstance(payload, dict):
        if isinstance(payload.get("member"), dict):
            return payload["member"]
        if isinstance(payload.get("data"), dict):
            return payload["data"]
    return {}


def _render_member_info(payload: dict) -> "str | None":
    m = _member(payload)
    if not m:
        return None
    level = m.get("member_level_name") or m.get("member_level_code") or UNKNOWN_VALUE
    points = m.get("points")
    growth = m.get("effective_growth_value")
    valid = m.get("membership_end_time") or UNKNOWN_VALUE
    return (
        "您的会员信息如下：\n\n"
        "| 项目 | 信息 |\n| --- | --- |\n"
        f"| 会员等级 | {level} |\n"
        f"| 当前积分 | {_number(points)} 积分 |\n"
        f"| 有效成长值 | {_number(growth)} |\n"
        f"| 会员有效期至 | {valid} |"
    )


def _render_points(payload: dict) -> "str | None":
    m = _member(payload)
    if not m or m.get("points") is None:
        return None
    return f"您当前有 **{_number(m.get('points'))} 积分**。"


def _render_mzx_points(payload: dict) -> "str | None":
    m = _member(payload)
    pts = m.get("mzx_points") if m else None
    if pts is None:
        return None
    return f"您的梦中心积分为 **{_number(pts)} 积分**。"


def _render_expiring(payload: dict) -> "str | None":
    """本月即将到期积分：两列表格（与 .so 一致，字段取不到按原值显示）。"""
    if not _found(payload):
        return None
    d = _member(payload)
    pts = d.get("expiring_points_this_month")
    return ("| 项目 | 信息 |\n| --- | --- |\n"
            f"| 本月即将到期积分 | {pts} 积分 |")


def _render_year_end_expiring(payload: dict) -> "str | None":
    if not _found(payload):
        return None
    d = _member(payload)
    pts = d.get("year_end_expiring_points", d.get("remain", 0))
    return (
        f"年底前可能清零的积分约 **{_number(pts)} 积分**。\n\n"
        "具体清零批次以小程序积分明细为准哦。"
    )


def _render_upgrade(payload: dict) -> "str | None":
    if not _found(payload):
        return None
    d = payload.get("data") if isinstance(payload, dict) else None
    d = d if isinstance(d, dict) else (_member(payload) or {})
    nxt = d.get("next_level") or d.get("nextLevelName")
    need = d.get("need_growth") or d.get("distance")
    cur = d.get("current_growth") or d.get("effective_growth_value")
    if not (nxt or need):
        return "暂时没有查到升级进度。"
    return (
        "您的升级进度如下：\n\n"
        "| 项目 | 信息 |\n| --- | --- |\n"
        f"| 下一等级 | {nxt or UNKNOWN_VALUE} |\n"
        f"| 还需成长值 | {_number(need)} |\n"
        f"| 当前成长值 | {_number(cur)} |"
    )


def _render_growth(payload: dict) -> "str | None":
    """最近成长值明细：表格「时间 | 成长值 | 说明」（与 .so 一致）。"""
    if not _found(payload):
        return None
    rows = _rows(payload)
    if not rows:
        return "暂时没有查到成长值明细。\n\n成长值以小程序会员页面为准哦。"
    body = ["| 时间 | 成长值 | 说明 |", "| --- | --- | --- |"]
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        body.append(f"| {row.get('time') or UNKNOWN_VALUE} "
                    f"| {_number(row.get('growth') or row.get('value') or row.get('points'))} "
                    f"| {row.get('desc') or row.get('remark') or UNKNOWN_VALUE} |")
    return "最近成长值明细如下：\n\n" + "\n".join(body)


def _render_point_detail(payload: dict) -> "str | None":
    """最近积分明细：表格「时间 | 积分 | 说明」（与 .so 一致）。"""
    if not _found(payload):
        return None
    rows = _rows(payload)
    if not rows:
        return "暂时没有查到最近的积分明细。\n\n以小程序积分明细页面刷新结果为准哦。"
    body = ["| 时间 | 积分 | 说明 |", "| --- | --- | --- |"]
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        body.append(f"| {row.get('time') or row.get('createTime') or UNKNOWN_VALUE} "
                    f"| {_number(row.get('points') or row.get('change'))} "
                    f"| {row.get('desc') or row.get('name') or row.get('title') or UNKNOWN_VALUE} |")
    return "最近积分明细如下：\n\n" + "\n".join(body)


# ──────────────────────────── 优惠券 ────────────────────────────
def _render_coupon_count(payload: dict) -> "str | None":
    if not _found(payload):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    d = data if isinstance(data, dict) else {}
    cnt = d.get("coupon_count")
    if cnt is None:
        cnt = d.get("count")
    # 与 .so 一致：单行「您当前有 **N 张可用券**。」（N 取不到按 0）
    return f"您当前有 **{_safe_count(cnt)} 张可用券**。"


def _render_coupon_list(payload: dict, title: str, empty_text: str) -> str:
    """优惠券/停车券列表：markdown 表格「券名称 | 有效期」（与 .so 一致）。"""
    if not _found(payload):
        return ""  # → render() 回落 UNKNOWN_REPLY
    rows = _rows(payload)
    if not rows:
        return empty_text
    body = ["| 券名称 | 有效期 |", "| --- | --- |"]
    for row in rows[:20]:
        body.append(f"| {_item_name(row)} | {_validity(row)} |")
    return f"{title} **{len(rows)} 张**：\n\n" + "\n".join(body)


# ──────────────────────────── 停车 ────────────────────────────
def _render_parking_status(payload: dict, info_only: bool = False) -> "str | None":
    """停车位/停车场信息：6 列表格（与 .so 一致，availability 与 info 同结构）。"""
    if not _found(payload):
        return None
    head = "当前可确认的停车场信息如下：" if info_only else "当前可确认的停车位信息如下："
    lines = [head, "",
             "| 停车场 | 位置 | 总车位 | 剩余车位 | 营业时间 | 充电桩 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in _rows(payload)[:12]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('name') or UNKNOWN_VALUE} | {row.get('location') or UNKNOWN_VALUE} "
            f"| {_number(row.get('total'))} | {_number(row.get('free') or row.get('remaining'))} "
            f"| {row.get('hours') or UNKNOWN_VALUE} | {row.get('charge') or UNKNOWN_VALUE} |"
        )
    return "\n".join(lines)


def _render_plates(payload: dict) -> "str | None":
    if not _found(payload):
        return None
    rows = _rows(payload)
    plates = [r.get("plate") or r.get("plateNo") or (r if isinstance(r, str) else None) for r in rows]
    plates = [p for p in plates if p]
    if not plates:
        return "您当前没有查询到已绑定的车牌。"
    body = "\n".join(f"- {p}" for p in plates)
    return f"您绑定的车牌如下：\n\n{body}"


def _render_fee(payload: dict) -> "str | None":
    data = payload.get("data") if isinstance(payload, dict) else None
    d = data if isinstance(data, dict) else {}
    if not _found(payload):
        return None
    amount = d.get("fee") or d.get("amount") or d.get("payAmount")
    if amount is None:
        return "暂时没有查到这笔停车费。\n\n请确认车牌和停车场后，以停车缴费页为准哦。"
    duration = d.get("duration") or UNKNOWN_VALUE
    return (
        "这笔停车费我帮您查到了：\n\n"
        "| 项目 | 信息 |\n| --- | --- |\n"
        f"| 当前应付金额 | {_number(amount)} 元 |\n"
        f"| 停车时长 | {duration} |\n\n"
        "最终金额以停车缴费页和出口结算为准哦。"
    )


# ──────────────────────────── 分派 ────────────────────────────
def render(intent: str, payload: dict) -> "str | None":
    """按 intent 选择渲染器；渲染不出来返回未知兜底句（上层据此回退）。"""
    out = None
    if intent == "member.info":
        out = _render_member_info(payload)
    elif intent == "member.points":
        out = _render_points(payload)
    elif intent == "member.mzx_points":
        out = _render_mzx_points(payload)
    elif intent == "member.point_detail":
        out = _render_point_detail(payload)
    elif intent == "member.expiring_points":
        out = _render_expiring(payload)
    elif intent == "member.year_end_expiring_points":
        out = _render_year_end_expiring(payload)
    elif intent == "member.upgrade_progress":
        out = _render_upgrade(payload)
    elif intent == "member.growth_detail":
        out = _render_growth(payload)
    elif intent == "coupon.count":
        out = _render_coupon_count(payload)
    elif intent == "coupon.owned":
        out = _render_coupon_list(payload, "您当前已领取的优惠券有", "暂时没有查到已领取的优惠券。\n\n以小程序卡包页面刷新结果为准哦。")
    elif intent == "coupon.receivable":
        out = _render_coupon_list(payload, "当前可领取的优惠券有", "暂时没有查到可领取的优惠券。\n\n以小程序卡包页面刷新结果为准哦。")
    elif intent == "parking.coupons":
        out = _render_coupon_list(payload, "您的停车券有", "暂时没有查到可用停车券。\n\n以小程序卡包页面刷新结果为准哦。")
    elif intent == "parking.available_coupons":
        out = _render_coupon_list(payload, "当前", "暂时没有查到可用停车券。\n\n以小程序卡包页面刷新结果为准哦。")
    elif intent == "parking.coupon_promotions":
        out = _render_coupon_list(payload, "当前停车券活动有", "暂时没有查到停车券活动。\n\n以小程序卡包页面刷新结果为准哦。")
    elif intent == "parking.discounts":
        out = _render_coupon_list(payload, "当前可确认的停车优惠有", "暂时没有查到可用停车优惠。\n\n以小程序卡包页面刷新结果为准哦。")
    elif intent == "parking.availability":
        out = _render_parking_status(payload, info_only=False)
    elif intent == "parking.info":
        out = _render_parking_status(payload, info_only=True)
    elif intent == "parking.plates":
        out = _render_plates(payload)
    elif intent == "parking.fee":
        out = _render_fee(payload)
    else:
        # 未实现/走大模型的意图（member.levels / coupon.detail / knowledge.*）→ None
        return None

    # 已实现的数据型意图：渲染器拿不到数据时统一回落未知兜底句（与 .so 一致，非 None）。
    return out if out else _UNKNOWN_REPLY


def _found(payload: dict) -> bool:
    """payload 是否表示「查到了」（有 found 标志或实际 data/member）。空 payload → False。"""
    if not isinstance(payload, dict) or not payload:
        return False
    if payload.get("found"):
        return True
    return bool(payload.get("member") or payload.get("data"))
