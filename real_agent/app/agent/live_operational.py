"""运营实时直达 live_operational（新版 / real_agent）。

拦截「实时车位 / 现在还有车位吗」「接驳车 / 导览车」这类运营实时问法：取实时数据渲染，
取不到回落 UNKNOWN_REPLY；不命中返回 None 交回 graph。

注意：停车**收费/规则**这类静态问法不在这里（交 static_context / parking_agent）；这里只拦
需要实时数据的「当前车位」和「导览车班次」。

重建说明：由 .so 重建。常量 UNKNOWN_REPLY 字节级；取数委托 miniprogram_api，渲染委托
markdown_table。触发关键词集与成稿文案为**结构忠实重建**（偏保守，避免误拦静态停车问法）；
实时渲染绑定线上字段，离线无数据时回落 UNKNOWN_REPLY。
"""
from real_agent.app.integrations.miniprogram_api import fetch_parking_status, fetch_shuttle_routes
from real_agent.app.agent.table_format import markdown_table

MEMBER_MPSESSID = ""
UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"

# 实时车位触发：需「实时/现在/剩余」等时效词 + 车位。
_PARKING_LIVE_CUES = ("实时车位", "现在车位", "车位实时", "实时停车位")
# 导览/接驳车触发。
_SHUTTLE_CUES = ("接驳车", "导览车", "西岸导览车", "接驳")


def _lots(data: "dict | None") -> "list[dict]":
    return (data or {}).get("lots") or (data or {}).get("items") or []


def _routes(data: "dict | None") -> "list[dict]":
    return (data or {}).get("routes") or (data or {}).get("items") or []


def _parking_reply(items: "list[dict]") -> str:
    """实时车位渲染（结构忠实；字段绑定线上接口）。"""
    if not items:
        return UNKNOWN_REPLY
    rows = [(it.get("name") or it.get("area") or "—",
             str(it.get("free") if it.get("free") is not None else "—"),
             str(it.get("total") if it.get("total") is not None else "—")) for it in items]
    return "当前实时车位如下：\n\n" + markdown_table(["区域", "空位", "总数"], rows)


def _shuttle_reply(routes: "list[dict]") -> str:
    """导览/接驳车渲染（结构忠实；字段绑定线上接口）。"""
    if not routes:
        return UNKNOWN_REPLY
    rows = [(r.get("name") or "—",
             f"{r.get('start', '')}—{r.get('end', '')}".strip("—"),
             r.get("hours") or r.get("time") or "—",
             r.get("days") or "—",
             r.get("stops") or "—",
             r.get("note") or r.get("interval") or "—") for r in routes]
    return ("当前有效的西岸导览车信息如下：\n\n"
            + markdown_table(["路线", "起点—终点", "运营时间", "运营日期", "站点", "车辆/提示"], rows))


def answer_live_operational_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中实时车位/导览车问法时返回成稿；否则 None。"""
    q = message or ""
    session = mpsessid or MEMBER_MPSESSID
    if any(c in q for c in _PARKING_LIVE_CUES):
        return _parking_reply(_lots(fetch_parking_status(session)))
    if any(c in q for c in _SHUTTLE_CUES):
        return _shuttle_reply(_routes(fetch_shuttle_routes(session)))
    return None
