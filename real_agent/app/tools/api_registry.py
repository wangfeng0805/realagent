"""接口目录工具（新版 / real_agent）。search_apis 找接口、call_api 调只读接口。
重建说明：由 .so 重建（readable）；委托已重建的 integrations.api_gateway。"""
from typing import Any
from real_agent.app.integrations import api_gateway

def _tok(config: "Any") -> str:
    try: return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception: return ""

def search_apis(query: str) -> dict:
    return {"found": True, "apis": api_gateway.search_catalog(query)}

def call_api(path: str, params: "dict | None" = None, config: "Any" = None) -> dict:
    return api_gateway.call_readonly_api(path, params or {}, _tok(config))
