"""园区演示域工具（新版 / real_agent）。

景点/活动/路线/实时状态等演示数据工具（非小程序实时接口），数据来自 repositories.db
（内置种子 SQLite）。供推荐/行程类问法使用。

重建说明：由 .so 重建（readable）；签名还原，取数委托 repositories.db 与 services.recommender。
"""
from datetime import date, timedelta  # noqa: F401
from real_agent.app.repositories import db
from real_agent.app.services import recommender

def _mock_disabled(name: str) -> dict:
    return {"found": False, "reason": "mock_disabled", "tool": name}

def _resolve_dates(when: str) -> "list[str]":
    return recommender.this_weekend() if ("周末" in (when or "")) else []

def search_attractions(query: str = "") -> dict:
    return {"found": True, "attractions": db.search_attractions(query)}

def search_events(query: str = "", date: str = "") -> dict:
    return {"found": True, "events": db.search_events(query, date)}

def check_ticket_availability(attraction: str = "", date: str = "") -> dict:
    return {"found": True, "sessions": db.check_sessions(attraction, date)}

def find_facility(query: str) -> dict:
    pois = db.find_pois(query)
    return {"found": bool(pois), "facilities": pois}

def get_realtime_status() -> dict:
    return {"found": True, "realtime": db.get_realtime()}

def recommend_route(theme: str = "") -> dict:
    return {"found": True, "routes": db.get_routes(theme)}

def recommend_events(when: str = "本周末", companions: str = "", member: str = "") -> dict:
    events = db.all_events()
    tags = recommender.parse_context_tags(companions)
    dates = _resolve_dates(when) or recommender.this_weekend()
    cands = recommender.recall(events, dates)
    cands = recommender.filter_for_companions(cands, tags)
    profile = db.find_member(member) or {}
    behavior = db.get_user_behavior(member) if member else {}
    return {"found": True, "events": recommender.rerank(cands, profile, behavior)}
