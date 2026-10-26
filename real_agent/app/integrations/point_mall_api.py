"""积分商城接口（新版 / real_agent）。

直连 getPointProducts 拉取积分可兑换商品，归一化成商品/SKU 字段，供 point_mall 工具使用。
带 30s 缓存。

重建说明：由 .so 重建（readable）。常量字节级；_safe_product/_safe_sku/_parse_datetime 等
归一化按轨迹重写；网络体委托 httpx。
"""
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse  # noqa: F401
import httpx

POINT_MALL_URL = "https://anticket.lengliwh.com/thvendor/mall/getPointProducts.xhtml"
POINT_MALL_APP_ID = "wxd275b0214ea13dc8"
POINT_MALL_CACHE_SECONDS = 30
POINT_MALL_KSMPID = "wbDreamwxd275b0214ea13dc8"
MEMBER_API_TIMEOUT = 15.0
MEMBER_KSCLIENT = "DZ97916675"
MEMBER_KSVERSION = "66314b202608031502"
MEMBER_CMPAPPKEY = "xamzx1"
MEMBER_REFERER = "https://servicewechat.com/undefined/devtools/page-frame.html"
MEMBER_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1 "
    "wechatdevtools/2.02.2607161 MicroMessenger/8.0.5 Language/zh_CN webview/"
)
_cache: "dict[str, tuple[float, dict]]" = {}


def _headers(mpsessid: str) -> "dict[str, str]":
    return {
        "ksclient": MEMBER_KSCLIENT, "mpsessid": mpsessid or "",
        "user-agent": MEMBER_USER_AGENT, "content-type": "application/x-www-form-urlencoded",
        "ksversion": MEMBER_KSVERSION, "cmpappkey": MEMBER_CMPAPPKEY, "ksmpid": POINT_MALL_KSMPID,
        "accept": "*/*", "referer": MEMBER_REFERER,
    }


def _parse_datetime(value: Any) -> "datetime | None":
    try:
        return datetime.fromisoformat(str(value).replace("/", "-")[:19])
    except Exception:
        return None


def _safe_sku(row: dict) -> dict:
    return {"name": row.get("skuName") or row.get("name"), "points": row.get("point") or row.get("points"),
            "stock": row.get("stock")}


def _safe_product(row: dict, now: datetime) -> dict:
    return {
        "name": row.get("productName") or row.get("name"),
        "points": row.get("point") or row.get("points"),
        "image": row.get("image") or row.get("imageUrl"),
        "skus": [_safe_sku(s) for s in (row.get("skus") or []) if isinstance(s, dict)],
    }


def _fetch_rows(mpsessid: str, product_type_code: str) -> dict:
    try:
        body = f"appId={POINT_MALL_APP_ID}"
        if product_type_code:
            body += f"&productTypeCode={product_type_code}"
        resp = httpx.post(POINT_MALL_URL, headers=_headers(mpsessid),
                          content=body.encode(), timeout=MEMBER_API_TIMEOUT)
        return resp.json() if isinstance(resp.json(), dict) else {}
    except Exception:
        return {"found": False, "reason": "upstream_unavailable"}


def fetch_point_products(mpsessid: str, query: str = "", product_type_code: str = "",
                         include_unavailable: bool = False, limit: int = 10) -> dict:
    """拉取积分商城商品（归一化 + 过滤 + 30s 缓存）。"""
    now = time.time()
    key = f"{mpsessid or ''}|{product_type_code}"
    hit = _cache.get(key)
    if hit and now - hit[0] < POINT_MALL_CACHE_SECONDS:
        body = hit[1]
    else:
        body = _fetch_rows(mpsessid, product_type_code)
        if isinstance(body, dict) and body.get("data") is not None:
            _cache[key] = (now, body)
    if not isinstance(body, dict):
        return {"found": False, "reason": "upstream_unavailable"}
    rows = (body.get("data") or {}).get("list") or body.get("data") or []
    dt = datetime.now()
    products = [_safe_product(r, dt) for r in rows if isinstance(r, dict)]
    if query:
        products = [p for p in products if query in (p.get("name") or "")]
    return {"found": True, "products": products[:limit]}
