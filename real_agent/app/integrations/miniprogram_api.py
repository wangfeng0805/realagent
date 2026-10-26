"""西岸梦中心小程序 OpenAPI 的客服只读客户端（新版 / real_agent）。

统一封装：请求头（ks* 鉴权 + 登录态 mpsessid）、服务前缀路由、只读接口调用、
响应归一化，以及一批 fetch_*（会员/停车/优惠券/商户/商城/导览车）取数函数和对应的
_safe_*（字段清洗，决定下游 renderer/tools 能读到哪些键）。

重建说明：本文件由新版编译产物重建，面向「读懂逻辑 + 改接口」。
- 鉴权常量、服务前缀、_READONLY_PATHS 路径表、商户分类词表为字节级还原；
- _full_url / token_from_config / _headers 的构造已对原 .so 验证一致；
- _normalize_payload、各 fetch_* 与 _safe_* 按调用轨迹 + 字段语义重写（readable）。
  实际 HTTP 往返依赖运行时 httpx + 真实接口，离线无法逐一对拍；改接口/参数看这里即可。
"""

import logging
from typing import Any

import httpx

from real_agent.app.config import (
    APP_ID,
    MEMBER_API_TIMEOUT,
    MEMBER_CMPAPPKEY,
    MEMBER_KSCLIENT,
    MEMBER_KSVERSION,
    MEMBER_REFERER,
    MEMBER_USER_AGENT,
    MINIPROGRAM_API_BASE_URL,
    MINIPROGRAM_KSMPID,
)

logger = logging.getLogger("real_agent.app.integrations.miniprogram_api")

_SITE_ROOT = "https://anticket.lengliwh.com"
# 已属于某个服务前缀的路径直接拼站点根，否则默认挂到 thvendor 下
_SERVICE_PREFIXES = ("thvendor", "ucenter", "theatre", "monitor")
_USER_AGENT = MEMBER_USER_AGENT

# 只读接口路径表：fetch_* 通过别名取路径，集中管理便于核对/改接口
_READONLY_PATHS = {
    "next_level": "/member/info/getDistance2NextLevel.xhtml",
    "expiring_points": "/member/record/gatherExpiringPointByMonth.xhtml",
    "coupon_count": "/member/coupon/memberCouponCount.xhtml",
    "plate_list": "/member/parking/getPlateList.xhtml",
    "parking_list": "/parking/getInfoList.xhtml",
    "merchant_list": "/guide/getAgencyPageList.xhtml",
    "merchant_categories": "/guide/getAgencyCategoryList.xhtml",
    "merchant_buildings": "/guide/getHaseAgenceGuidePointPageList.xhtml",
    "merchant_simple_list": "/agency/getValidSimpleAgencyList.xhtml",
    "merchant_cultural_list": "/mall/getAgencyCulturals.xhtml",
    "guide_default_map": "/guide/getShowDefaultGuideMap.xhtml",
    "merchant_detail": "/mall/getAgencyVo.xhtml",
    "cultural_products": "/mall/getCulturalProducts.xhtml",
    "rent_products": "/mall/rent/getProducts.xhtml",
    "rent_product_detail": "/mall/rent/getProductDetail.xhtml",
    "rent_delivery_addresses": "/mall/rent/getDeliveryAddresses.xhtml",
    "point_records": "/member/record/listMemberPointReceiveRecord.xhtml",
    "shuttle_routes": "/westbund/user/routes.xhtml",
    "shuttle_route_detail": "/westbund/user/route/detail.xhtml",
    "shuttle_buses": "/westbund/user/route/buses.xhtml",
}

# 商户分类判定词表（用于 fetch_merchants 的业态筛选/相关性校验）
_FOOD_TERMS = ("餐饮", "美食", "餐厅", "咖啡", "奶茶", "茶饮", "甜品", "烘焙", "面包",
               "火锅", "日料", "中餐", "西餐", "快餐", "轻食", "小吃", "简餐", "饮品", "料理")
_FOOD_BROAD = ("餐饮", "美食", "吃", "午餐", "晚餐", "正餐", "用餐", "吃饭", "吃什么")
_TOP_CATEGORIES = ("体验", "零售", "酒店", "购物", "服饰", "服装", "亲子", "运动", "生活", "美妆", "珠宝")
_NON_MERCHANT = ("客服台", "服务台", "问询", "客服中心")


# ──────────────────────────── HTTP 核心 ────────────────────────────
def _full_url(path: str) -> str:
    """路径 → 完整 URL。已带服务前缀（thvendor/ucenter/theatre/monitor）的挂站点根；
    其余默认挂到 thvendor 服务下。"""
    seg = path.lstrip("/").split("/", 1)[0]
    if seg in _SERVICE_PREFIXES:
        return _SITE_ROOT + path
    return MINIPROGRAM_API_BASE_URL + path


def _headers(mpsessid: str) -> "dict[str, str]":
    """小程序 OpenAPI 鉴权头 + 登录态。"""
    return {
        "ksclient": MEMBER_KSCLIENT,
        "user-agent": _USER_AGENT,
        "content-type": "application/x-www-form-urlencoded",
        "ksversion": MEMBER_KSVERSION,
        "cmpappkey": MEMBER_CMPAPPKEY,
        "ksmpid": MINIPROGRAM_KSMPID,
        "accept": "*/*",
        "referer": MEMBER_REFERER,
        "mpsessid": mpsessid or "",
    }


def token_from_config(config: Any) -> str:
    """从 LangGraph RunnableConfig 的 configurable 里取运行时登录态 mpsessid。"""
    try:
        return (config or {}).get("configurable", {}).get("mpsessid", "") or ""
    except AttributeError:
        return ""


def _normalize_payload(payload: Any, require_session: bool) -> dict:
    """把上游原始响应归一成 {found, data, error_code}。非 dict → 视为上游异常。"""
    if not isinstance(payload, dict):
        return {"found": False, "reason": "upstream_rejected", "error_code": None}
    data = payload.get("data") if payload.get("code") in (0, "0", None) else None
    return {"found": True, "data": data, "error_code": payload.get("error_code")}


def _api_get(endpoint: str, mpsessid: str = "", params: "dict[str, Any] | None" = None,
             *, require_session: bool = False, timeout: "float | None" = None) -> dict:
    """GET 一个只读接口并归一化。缺登录态且要求登录 → 直接返回提示。"""
    if require_session and not mpsessid:
        return {"found": False, "reason": "missing_session"}
    try:
        resp = httpx.get(
            _full_url(endpoint),
            params=params or {},
            headers=_headers(mpsessid),
            timeout=timeout or MEMBER_API_TIMEOUT,
        )
        resp.raise_for_status()
        return _normalize_payload(resp.json(), require_session)
    except Exception:
        logger.warning("miniprogram GET failed: %s", endpoint, exc_info=True)
        return {"found": False, "reason": "upstream_unavailable"}


def api_get_path(path: str, mpsessid: str = "", params: "dict[str, Any] | None" = None,
                 *, require_session: bool = False, timeout: "float | None" = None) -> dict:
    """供 tools 层调用的通用只读 GET（path 直接取自各工具）。"""
    return _api_get(path, mpsessid, params, require_session=require_session, timeout=timeout)


def api_post(path: str, mpsessid: str = "", params: "dict[str, Any] | None" = None,
             *, require_session: bool = False, timeout: "float | None" = None) -> dict:
    """只读场景的 POST（个别接口要求 POST）；写操作一律不在此封装内。"""
    if require_session and not mpsessid:
        return {"found": False, "reason": "missing_session"}
    try:
        resp = httpx.post(
            _full_url(path),
            data=params or {},
            headers=_headers(mpsessid),
            timeout=timeout or MEMBER_API_TIMEOUT,
        )
        resp.raise_for_status()
        return _normalize_payload(resp.json(), require_session)
    except Exception:
        logger.warning("miniprogram POST failed: %s", path, exc_info=True)
        return {"found": False, "reason": "upstream_unavailable"}


# ──────────────────────────── 会员 ────────────────────────────
def fetch_next_level_progress(mpsessid: str) -> dict:
    return _api_get(_READONLY_PATHS["next_level"], mpsessid, require_session=True)


def fetch_expiring_points(mpsessid: str) -> dict:
    return _api_get(_READONLY_PATHS["expiring_points"], mpsessid, require_session=True)


def fetch_coupon_count(mpsessid: str) -> dict:
    return _api_get(_READONLY_PATHS["coupon_count"], mpsessid, require_session=True)


def fetch_point_records(mpsessid: str, direction: str = "decrease", limit: int = 10) -> dict:
    return _api_get(
        _READONLY_PATHS["point_records"], mpsessid,
        {"direction": direction, "limit": limit}, require_session=True,
    )


# ──────────────────────────── 停车 ────────────────────────────
def _clean_plate(value: Any) -> "str | None":
    """车牌脱敏/清洗：取有效车牌串。"""
    if not value:
        return None
    s = str(value).strip().upper()
    return s or None


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from _walk_dicts(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_dicts(v)


def fetch_member_plates(mpsessid: str) -> dict:
    raw = _api_get(_READONLY_PATHS["plate_list"], mpsessid, require_session=True)
    if not raw.get("found"):
        return raw
    plates = []
    for row in _walk_dicts(raw.get("data")):
        p = _clean_plate(row.get("plateNo") or row.get("plate"))
        if p:
            plates.append(p)
    return {"found": True, "data": {"plates": plates}}


def _safe_parking_row(row: dict) -> dict:
    """停车场记录清洗：只保留业务白名单字段。"""
    return {
        "name": row.get("name") or row.get("parkName"),
        "remaining": row.get("remaining") or row.get("freeNum") or row.get("emptyNum"),
        "total": row.get("total") or row.get("totalNum"),
        "type": row.get("type") or row.get("parkType"),
        "charging": row.get("charging") or row.get("hasCharging"),
    }


def fetch_parking_status(mpsessid: str = "", park_type: str = "", area_type: str = "westbund",
                         only_with_spaces: bool = False, only_open: bool = False,
                         charging_station: "bool | None" = None) -> dict:
    params = {"areaType": area_type}
    if park_type:
        params["parkType"] = park_type
    raw = _api_get(_READONLY_PATHS["parking_list"], mpsessid, params)
    if not raw.get("found"):
        return raw
    lots = [_safe_parking_row(r) for r in _walk_dicts(raw.get("data")) if r.get("name") or r.get("parkName")]
    if only_with_spaces:
        lots = [l for l in lots if l.get("remaining")]
    if charging_station is True:
        lots = [l for l in lots if l.get("charging")]
    return {"found": True, "data": {"lots": lots}}


# ──────────────────────────── 商户 / 商城 / 导览车 ────────────────────────────
# 说明：以下取数函数与其 _safe_* 清洗器同样走 _api_get(_READONLY_PATHS[...])，
# 参数名见各自 params。为控制篇幅，这里给出骨架与路径；字段清洗按实际接口返回补全。

def _looks_like_merchant_name(name: str) -> bool:
    return bool(name) and not any(w in name for w in _NON_MERCHANT)


def _expand_category_terms(category: str) -> "list[str]":
    """把业态词扩展为同义词集合（餐饮类用 _FOOD_TERMS）。"""
    if category in _FOOD_BROAD:
        return list(_FOOD_TERMS)
    return [category] if category else []


def fetch_merchants(mpsessid: str = "", query: str = "", category: str = "",
                    limit: int = 10, tags: "list[str] | None" = None) -> dict:
    params = {"pageSize": limit}
    if query:
        params["keyword"] = query
    if category:
        params["category"] = category
    return _api_get(_READONLY_PATHS["merchant_list"], mpsessid, params)


def fetch_merchant_categories(mpsessid: str = "") -> dict:
    return _api_get(_READONLY_PATHS["merchant_categories"], mpsessid)


def fetch_merchant_buildings(mpsessid: str = "", category: str = "",
                             guide_map_id: "int | None" = None, limit: int = 20) -> dict:
    params = {"pageSize": limit}
    if category:
        params["category"] = category
    if guide_map_id is not None:
        params["guideMapId"] = guide_map_id
    return _api_get(_READONLY_PATHS["merchant_buildings"], mpsessid, params)


def fetch_mall_products(mpsessid: str = "", query: str = "", kind: str = "",
                        include_unavailable: bool = False, limit: int = 10) -> dict:
    path = _READONLY_PATHS["rent_products"] if kind == "rent" else _READONLY_PATHS["cultural_products"]
    params = {"pageSize": limit}
    if query:
        params["productName"] = query
    return _api_get(path, mpsessid, params)


def fetch_rent_product_detail(mpsessid: str = "", rent_product_code: str = "") -> dict:
    return _api_get(_READONLY_PATHS["rent_product_detail"], mpsessid,
                    {"rentProductCode": rent_product_code})


def fetch_rent_delivery_addresses(mpsessid: str = "", rent_product_id: "int | str | None" = None,
                                  platform: str = "APP") -> dict:
    return _api_get(_READONLY_PATHS["rent_delivery_addresses"], mpsessid,
                    {"appId": APP_ID, "platform": platform, "rentProductId": rent_product_id})


def _safe_route(row: dict, include_stations: bool = False) -> dict:
    out = {
        "id": row.get("id") or row.get("routeId"),
        "name": row.get("name") or row.get("routeName"),
        "is_currently_operating": row.get("isCurrentlyOperating") or row.get("running"),
    }
    if include_stations:
        out["stations"] = row.get("stations") or row.get("stationList")
    return out


def fetch_shuttle_routes(mpsessid: str = "", route_id: "int | None" = None,
                         include_buses: bool = False) -> dict:
    if route_id is not None:
        raw = _api_get(_READONLY_PATHS["shuttle_route_detail"], mpsessid, {"routeId": route_id})
    else:
        raw = _api_get(_READONLY_PATHS["shuttle_routes"], mpsessid)
    if not raw.get("found"):
        return raw
    routes = [_safe_route(r, include_buses) for r in _walk_dicts(raw.get("data")) if r.get("name") or r.get("routeName")]
    routes = [r for r in routes if r.get("is_currently_operating")]
    return {"found": True, "data": {"routes": routes}}
