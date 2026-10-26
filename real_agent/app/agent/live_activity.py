"""活动直达 live_activity（新版 / real_agent）。

拦截活动/演出/展览/快闪类问法：
  - **列表/排期**：按今天 / 明天 / 周末 / 近期取真实活动并按日期渲染；
  - **详情**：问法里点名某个活动（用 _norm_title + _is_subsequence 做标题模糊匹配）→ 渲染该活动详情。
不命中返回 None，交回 graph。

与 live_program 的分工：live_program 侧重「有哪些活动」的宽列表；live_activity 侧重带日期/
排期维度与具体活动的模糊匹配。两者都不命中才进 ReAct。

重建说明：由 .so 重建。常量 _WEEKDAYS 字节级；纯函数 _is_subsequence / _norm_title /
_weekend_dates / _date_label / _activity_keyword 与 .so 对拍一致。取数委托 activity_api，渲染
委托 markdown_table；成稿文案绑定线上活动字段，离线无数据时回落为空提示/None，属装配点。
触发关键词集为**结构忠实重建**（偏保守）。
"""
import json  # noqa: F401
import re
from datetime import date, timedelta

from real_agent.app.integrations.activity_api import fetch_activities
from real_agent.app.agent.table_format import markdown_table  # noqa: F401

MEMBER_MPSESSID = ""
_WEEKDAYS = "一二三四五六日"

# 活动域词（命中其一才可能走活动直达）。
_ACTIVITY_WORDS = ("活动", "演出", "展览", "快闪")
# 日期线索。
_TODAY_CUES = ("今天", "今日")
_TOMORROW_CUES = ("明天", "明日")
_WEEKEND_CUES = ("周末", "本周末", "这周末")
# 详情线索（用于触发详情分支）。
_DETAIL_WORDS = ("详情", "介绍", "了解", "怎么参与", "怎么购票", "门票", "场次", "票价")
# _activity_keyword 实际剥离的词（与 .so 一致：去详情类词，但保留「场次」）。
_KW_STRIP = ("详情", "介绍", "了解", "怎么参与", "怎么购票", "门票", "票价")
_WS = re.compile(r"[\s·・]")


def _is_subsequence(short: str, long: str) -> bool:
    """short 是否为 long 的子序列（字符按序出现，可不连续）。"""
    it = iter(long or "")
    return all(ch in it for ch in (short or ""))


def _norm_title(text: "object") -> str:
    """标题归一：小写 + 去空白 + 去中点，用于模糊匹配。"""
    return _WS.sub("", str(text or "").lower())


def _weekend_dates(today: date) -> "list[date]":
    """本周（周一~周日）的周六、周日。周日时周六为昨天。"""
    sat = today + timedelta(days=5 - today.weekday())
    return [sat, sat + timedelta(days=1)]


def _date_label(value: date) -> str:
    return f"{value.month}月{value.day}日（周{_WEEKDAYS[value.weekday()]}）"


def _activity_keyword(query: str) -> str:
    """去掉详情词后的活动标题关键词。"""
    q = query or ""
    for w in _KW_STRIP:
        q = q.replace(w, "")
    return q.strip()


def _wanted_dates(q: str) -> "list[date]":
    today = date.today()
    if any(c in q for c in _TODAY_CUES):
        return [today]
    if any(c in q for c in _TOMORROW_CUES):
        return [today + timedelta(days=1)]
    if any(c in q for c in _WEEKEND_CUES):
        return _weekend_dates(today)
    return []


def _items(data: "dict | None") -> "list[dict]":
    return (data or {}).get("activities") or (data or {}).get("items") or []


def _build_activity_card(item: dict, *, detail: bool = False) -> dict:
    """把一条活动整理成渲染用结构（readable 装配点）。"""
    return {
        "title": item.get("title") or item.get("name") or "未命名活动",
        "start": item.get("startTime") or item.get("start_time") or "",
        "end": item.get("endTime") or item.get("end_time") or "",
        "detail": detail,
    }


def _activity_cards(items: "list[dict]") -> str:
    cards = [_build_activity_card(it) for it in items]
    rows = [(c["title"], c["start"] or "—") for c in cards]
    return markdown_table(["活动", "开始时间"], rows)


def _activity_detail(item: dict) -> str:
    c = _build_activity_card(item, detail=True)
    return f"### {c['title']}\n- 时间：{c['start'] or '以现场为准'}"


def _schedule(items_by_date: "list[tuple[date, list[dict]]]") -> str:
    blocks = []
    for d, items in items_by_date:
        if not items:
            continue
        blocks.append(f"**{_date_label(d)}**\n" + _activity_cards(items))
    if not blocks:
        return ("今天暂时没有查询到正在进行的活动～您可以问我近期即将开始的活动，"
                "或者演出展览、观光住宿等其他信息。")
    return "\n\n".join(blocks)


def answer_live_activity_request(message: str, mpsessid: "str | None") -> "str | None":
    """命中活动列表/排期/详情问法时返回成稿；否则 None。"""
    q = message or ""
    if not any(w in q for w in _ACTIVITY_WORDS):
        return None
    session = mpsessid or MEMBER_MPSESSID

    # 详情：点名了具体活动（去词后还剩标题，且与某活动标题模糊匹配）
    if any(w in q for w in _DETAIL_WORDS):
        kw = _norm_title(_activity_keyword(q))
        items = _items(fetch_activities(session, query=kw))
        for it in items:
            if kw and _is_subsequence(kw, _norm_title(it.get("title") or it.get("name"))):
                return _activity_detail(it)
        return None

    # 列表/排期
    wanted = _wanted_dates(q)
    data = fetch_activities(session, query="")
    items = _items(data)
    if wanted:
        by_date = [(d, [it for it in items if (it.get("startTime") or "").startswith(d.isoformat())])
                   for d in wanted]
        return _schedule(by_date)
    if not items:
        return None
    return _activity_cards(items)
