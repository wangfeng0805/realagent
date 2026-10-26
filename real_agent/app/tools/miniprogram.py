"""小程序只读工具（新版 / real_agent）。

会员卡包/积分/车牌/车位/商户/商城/租赁/接驳等小程序侧只读能力，暴露两类形态：
- fetch_*(mpsessid, ...)：底层取数（供能力层/直达处理器直接调）；
- get_*/search_*(config, ...)：ReActAgent 工具形态（从 config 取登录态再调 fetch_*）。

重建说明：由 .so 重建（readable）。函数名/签名对 .so 还原；fetch_* 委托已重建的
integrations.miniprogram_api。
"""
from typing import Any
from real_agent.app.integrations.miniprogram_api import (
    fetch_coupon_count, fetch_expiring_points, fetch_member_plates, fetch_next_level_progress,
    fetch_point_records, fetch_parking_status, fetch_merchants, fetch_merchant_categories,
    fetch_merchant_buildings, fetch_mall_products, fetch_rent_product_detail,
    fetch_rent_delivery_addresses, fetch_shuttle_routes,
)

# 重新导出底层 fetch_*（供能力层/直达处理器使用）
__all__ = [n for n in dir() if n.startswith("fetch_")] + [
    "get_member_coupon_count", "get_member_expiring_points", "get_member_bound_plates",
    "get_member_upgrade_progress", "get_member_point_records", "get_miniprogram_parking_status",
    "search_miniprogram_merchants", "get_miniprogram_merchant_categories",
    "get_miniprogram_merchant_buildings", "search_mall_products", "get_rent_product_detail",
    "get_rent_delivery_addresses", "get_westbund_shuttle_routes",
]


def _tok(config: "Any") -> str:
    try:
        return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception:
        return ""


def get_member_coupon_count(config: "Any") -> dict:
    return fetch_coupon_count(_tok(config))


def get_member_expiring_points(config: "Any") -> dict:
    return fetch_expiring_points(_tok(config))


def get_member_bound_plates(config: "Any") -> dict:
    return fetch_member_plates(_tok(config))


def get_member_upgrade_progress(config: "Any") -> dict:
    return fetch_next_level_progress(_tok(config))


def get_member_point_records(config: "Any", direction: str = "decrease", limit: int = 10) -> dict:
    return fetch_point_records(_tok(config), direction=direction, limit=limit)


def get_miniprogram_parking_status(config: "Any", park_type: str = "", area_type: str = "westbund",
                                   only_with_spaces: bool = False, only_open: bool = False,
                                   charging_station: "bool | None" = None) -> dict:
    return fetch_parking_status(_tok(config), park_type=park_type, area_type=area_type,
                                only_with_spaces=only_with_spaces, only_open=only_open,
                                charging_station=charging_station)


def search_miniprogram_merchants(config: "Any", query: str = "", category: str = "", limit: int = 10) -> dict:
    return fetch_merchants(_tok(config), query=query, category=category, limit=limit)


def get_miniprogram_merchant_categories(config: "Any") -> dict:
    return fetch_merchant_categories(_tok(config))


def get_miniprogram_merchant_buildings(config: "Any", category: str = "",
                                       guide_map_id: "int | None" = None, limit: int = 20) -> dict:
    return fetch_merchant_buildings(_tok(config), category=category, guide_map_id=guide_map_id, limit=limit)


def search_mall_products(config: "Any", query: str = "", kind: str = "", limit: int = 10) -> dict:
    return fetch_mall_products(_tok(config), query=query, kind=kind, limit=limit)


def get_rent_product_detail(config: "Any", rent_product_code: str = "") -> dict:
    return fetch_rent_product_detail(_tok(config), rent_product_code=rent_product_code)


def get_rent_delivery_addresses(config: "Any", rent_product_id: "int | str | None" = None,
                                platform: str = "APP") -> dict:
    return fetch_rent_delivery_addresses(_tok(config), rent_product_id=rent_product_id, platform=platform)


def get_westbund_shuttle_routes(config: "Any", route_id: "int | None" = None,
                                include_buses: bool = False) -> dict:
    return fetch_shuttle_routes(_tok(config), route_id=route_id, include_buses=include_buses)
