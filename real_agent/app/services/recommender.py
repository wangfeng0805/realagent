"""活动推荐打分（新版 / real_agent）。

两段式：recall（按日期/地点召回候选）→ rerank（按会员兴趣/行为/可用性加权排序）。
用于「这周末带孩子去哪」这类推荐问法。

重建说明：由 .so 重建（readable）。WEIGHTS/_CONTEXT_MAP/_KID_INTEREST 与 parse_context_tags/
this_weekend/_in_range 等按 .so 还原；打分公式为可读重写（权重/维度一致）。
"""
from datetime import date as _date, timedelta

# 排序权重（四个维度）
WEIGHTS = {"interest": 0.4, "behavior": 0.3, "availability": 0.2, "context": 0.1}

# 同伴语境 → 语境标签
_CONTEXT_MAP = {
    "孩子": "亲子", "小孩": "亲子", "家人": "家庭", "朋友": "社交", "对象": "情侣",
}
# 带娃友好的兴趣标签
_KID_INTEREST = (
    "亲子", "手作", "互动", "科普", "动物", "自然", "绘本", "儿童", "游乐",
    "音乐", "展览", "市集", "户外", "运动", "益智",
)


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def parse_context_tags(text: str) -> "set[str]":
    """从同伴描述解析语境标签（孩子→亲子 等）。"""
    tags: "set[str]" = set()
    for k, v in _CONTEXT_MAP.items():
        if k in (text or ""):
            tags.add(v)
    return tags


def this_weekend(today: "_date | None" = None) -> "list[str]":
    """返回本周末（周六、周日）的 ISO 日期。"""
    d = today or _date.today()
    sat = d + timedelta(days=(5 - d.weekday()) % 7)
    sun = sat + timedelta(days=1)
    return [sat.isoformat(), sun.isoformat()]


def _in_range(day: str, rng: str) -> bool:
    """day 是否落在 rng（"start~end" 或单日）内。"""
    if not rng:
        return True
    if "~" in rng:
        a, b = rng.split("~", 1)
        return a.strip() <= day <= b.strip()
    return day == rng.strip()


def recall(events: "list[dict]", target_dates: "list[str]",
           location: "str | None" = None) -> "list[dict]":
    """按目标日期（和可选地点）召回候选活动。"""
    out = []
    for e in events:
        day = e.get("day") or ""
        if target_dates and day and not any(_in_range(day, d) for d in target_dates):
            continue
        if location and location not in (e.get("location") or ""):
            continue
        out.append(e)
    return out


def filter_for_companions(events: "list[dict]", context_tags: "set[str]") -> "list[dict]":
    """带娃语境下，过滤到亲子友好的活动。"""
    if "亲子" not in context_tags:
        return events
    return [e for e in events if set(e.get("tags") or []) & set(_KID_INTEREST)] or events


def _interest(event: dict, profile: dict) -> float:
    interests = set(profile.get("interests") or [])
    tags = set(event.get("tags") or [])
    return _clamp(len(interests & tags) / max(1, len(tags)))


def _behavior(event: dict, behavior: dict) -> float:
    visited = set(behavior.get("visited") or [])
    tags = set(event.get("tags") or [])
    return _clamp(len(visited & tags) / max(1, len(tags)))


def _avail(event: dict) -> float:
    return 1.0 if event.get("day") else 0.5


def _reasons(event: dict, f: dict, profile: dict) -> "list[str]":
    reasons = []
    if f.get("interest", 0) > 0:
        reasons.append("符合你的兴趣")
    if f.get("behavior", 0) > 0:
        reasons.append("和你去过的类似")
    if event.get("day"):
        reasons.append("周末有场次")
    return reasons


def rerank(candidates: "list[dict]", profile: dict, behavior: dict, top_n: int = 5) -> "list[dict]":
    """按四维加权打分排序，取前 top_n，附推荐理由。"""
    scored = []
    for e in candidates:
        f = {"interest": _interest(e, profile), "behavior": _behavior(e, behavior),
             "availability": _avail(e), "context": 0.5}
        score = sum(WEIGHTS[k] * f[k] for k in WEIGHTS)
        scored.append({**e, "score": round(score, 4), "reasons": _reasons(e, f, profile)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]
