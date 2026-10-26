"""积分商城工具（新版 / real_agent）。委托 integrations.point_mall_api。
重建说明：由 .so 重建（readable）；签名还原，取数委托已重建的 point_mall_api。"""
from typing import Any
from real_agent.app.integrations.point_mall_api import fetch_point_products

MEMBER_MPSESSID = ""

def _tok(config: "Any") -> str:
    try: return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception: return ""

def get_point_mall_products(config: "Any", query: str = "", product_type_code: str = "",
                            include_unavailable: bool = False, limit: int = 10) -> dict:
    return fetch_point_products(_tok(config), query=query, product_type_code=product_type_code,
                                include_unavailable=include_unavailable, limit=limit)
