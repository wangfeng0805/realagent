"""活动/项目列表的确定性直达回答（新版 / real_agent）。

拦截「有哪些活动 / 今天有什么演出 / 周末有什么展览」这类**列表**型问法，直接调
ticketing_list_programs 取真实活动并渲染成卡片，不经大模型。具体某个活动的**详情**
（怎么购票/场次/票价等）不在这里拦截，交给 Agent 用 ticketing 工具查。

说明：本文件由新版编译产物重建。词表（_ACTIVITY_WORDS/_LIST_CUES/_DETAIL_WORDS）字节级
还原；_wanted_date 与拦截逻辑按调用轨迹重写。
"""

from datetime import date, timedelta

from real_agent.app.tools.ticketing import ticketing_list_programs
from real_agent.app.agent.response_formatter import render_program_list

MEMBER_MPSESSID = ""

# 详情类词：命中则不走列表直达（交给 Agent 查具体活动）
_DETAIL_WORDS = (
    "详情", "介绍", "了解", "参与方式", "怎么购票", "如何购票", "怎么买票", "购票",
    "门票", "场次", "票种", "票价", "怎么参与", "如何参与", "怎么预约",
)
# 活动类词
_ACTIVITY_WORDS = (
    "活动", "演出", "展览", "快闪", "演唱会", "话剧", "音乐会", "剧目", "节目",
)
# 列表意图线索
_LIST_CUES = (
    "有哪些", "哪些", "有什么", "什么活动", "有没有", "最近", "近期", "今天", "今日",
    "明天", "周末", "本周", "这周", "推荐", "列表",
)


def _wanted_date(q: str) -> str:
    """从问法解析目标日期（ISO）。今天/今日→today，明天→tomorrow，其余（周末/本周等）→""。"""
    if "今天" in q or "今日" in q:
        return date.today().isoformat()
    if "明天" in q:
        return (date.today() + timedelta(days=1)).isoformat()
    return ""


def _is_list_intent(q: str) -> bool:
    """列表意图：含活动词 + 列表线索，且不是问具体活动详情。"""
    if any(w in q for w in _DETAIL_WORDS):
        return False
    return any(w in q for w in _ACTIVITY_WORDS) and any(c in q for c in _LIST_CUES)


def answer_live_program_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中活动列表问法时返回渲染好的卡片；否则返回 None 交回 Agent。"""
    if not _is_list_intent(message):
        return None

    want_date = _wanted_date(message)
    config = {"configurable": {"mpsessid": mpsessid or MEMBER_MPSESSID}}
    result = ticketing_list_programs(config, date=want_date)

    programs = (result or {}).get("programs") or (result or {}).get("items") or []
    if not programs:
        return None  # 没取到真实活动 → 交回 Agent，不编造

    return render_program_list(programs)
