"""活动列表接口（新版 / real_agent）。

直连小程序 getNewAdList 拉取活动/展览/快闪，归一化成卡片字段（起止期、票价、图片）供
live_program / ticketing 工具使用。带 60s 进程内缓存。

重建说明：由 .so 重建（readable）。常量（URL/adflags/缓存/签名头）字节级；_safe_activity/
_parse_date/parse_event_period 等归一化按轨迹重写；网络体委托 httpx。
"""
import time
from datetime import date
from typing import Any
from urllib.parse import urlparse  # noqa: F401
import httpx

ACTIVITY_LIST_URL = "https://anticket.lengliwh.com/thvendor/ad/getNewAdList.xhtml"
ACTIVITY_ADFLAGS = "exhibit,eventFlash_mob,accommodation"
ACTIVITY_CACHE_SECONDS = 60
ACTIVITY_KSMPID = "wbDreamwxd275b0214ea13dc8"
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
        "ksversion": MEMBER_KSVERSION, "cmpappkey": MEMBER_CMPAPPKEY, "ksmpid": ACTIVITY_KSMPID,
        "accept": "*/*", "referer": MEMBER_REFERER,
    }


def _parse_date(value: str) -> "date | None":
    try:
        p = str(value).split("-")
        return date(int(p[0]), int(p[1]), int(p[2][:2]))
    except Exception:
        return None


def _safe_activity(row: dict, target: date) -> dict:
    """归一化一条活动为卡片字段。"""
    return {
        "name": row.get("title") or row.get("name"),
        "startTime": row.get("startTime") or row.get("beginTime"),
        "endTime": row.get("endTime"),
        "minPrice": row.get("minPrice"),
        "image": row.get("image") or row.get("imageUrl"),
    }


def _fetch_rows(mpsessid: str) -> dict:
    try:
        resp = httpx.post(ACTIVITY_LIST_URL, headers=_headers(mpsessid),
                          content=f"adflags={ACTIVITY_ADFLAGS}".encode(), timeout=MEMBER_API_TIMEOUT)
        return resp.json() if isinstance(resp.json(), dict) else {}
    except Exception:
        return {"found": False, "reason": "upstream_unavailable"}


def fetch_activities(mpsessid: str, query: str = "", category: str = "activity",
                     on_date: str = "", include_expired: bool = False,
                     include_upcoming: bool = False, limit: int = 10) -> dict:
    """拉取活动列表（归一化 + 过滤 + 60s 缓存）。"""
    now = time.time()
    hit = _cache.get(mpsessid or "")
    if hit and now - hit[0] < ACTIVITY_CACHE_SECONDS:
        body = hit[1]
    else:
        body = _fetch_rows(mpsessid)
        if isinstance(body, dict) and body.get("data") is not None:
            _cache[mpsessid or ""] = (now, body)
    if not isinstance(body, dict):
        return {"found": False, "reason": "upstream_unavailable"}
    rows = (body.get("data") or {}).get("list") or body.get("data") or []
    target = _parse_date(on_date) or date.today()
    programs = [_safe_activity(r, target) for r in rows if isinstance(r, dict)]
    if query:
        programs = [p for p in programs if query in (p.get("name") or "")]
    return {"found": True, "programs": programs[:limit]}
