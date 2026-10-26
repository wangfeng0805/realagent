"""活动工具（新版 / real_agent）。ReActAgent 工具形态，委托 integrations.activity_api。
重建说明：由 .so 重建（readable）；签名还原，取数委托已重建的 activity_api。"""
from typing import Any
from real_agent.app.integrations.activity_api import fetch_activities

MEMBER_MPSESSID = ""

def _tok(config: "Any") -> str:
    try: return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception: return ""

def get_current_activities(config: "Any", query: str = "", category: str = "activity",
                           on_date: str = "", include_expired: bool = False,
                           include_upcoming: bool = False, limit: int = 10) -> dict:
    return fetch_activities(_tok(config), query=query, category=category, on_date=on_date,
                            include_expired=include_expired, include_upcoming=include_upcoming, limit=limit)
