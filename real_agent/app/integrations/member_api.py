"""西岸梦中心会员信息读取（新版 / real_agent）。

直连小程序后端的 getMemberInfo 接口，拿到当前登录用户（由 mpsessid 标识）的会员资料，
归一化成稳定的内部字段（_safe_member），供 capabilities.registry 的 member.* 能力取数、
再交 capabilities.renderer 渲染。带 30s 进程内缓存，降低重复查询压力。

重建说明：本文件由新版编译产物（member_api.*.so）重建。
- 所有常量（接口地址 / 小程序签名头 / 超时 / 缓存秒数）字节级还原；
- _clean_mobile / _put / _safe_member 三个纯函数经随机对拍与原 .so 一致（键映射、
  输出顺序、跳过规则全部核对）；
- fetch_current_member 的请求构造（POST 空体 + 9 个固定头）、响应分支（missing_session /
  upstream_unavailable / invalid_or_expired_session / empty_member / found）与缓存语义，
  均通过对原 .so 注入桩 httpx 捕获真实出站请求 + 穷举响应形状还原，行为一致。
"""

import hashlib  # noqa: F401  （原实现引入，签名预留；当前请求头为固定值，未参与计算）
import threading
import time
from typing import Any

import httpx

# ──────────────────────────── 接口 / 签名常量（字节级还原）────────────────────────────
MEMBER_INFO_URL = "https://anticket.lengliwh.com/thvendor/member/info/getMemberInfo.xhtml"
MEMBER_API_TIMEOUT = 15.0
MEMBER_CACHE_SECONDS = 30

# 小程序侧固定请求头（抓包还原；非机密业务标识，随版本更新）
MEMBER_KSCLIENT = "DZ97916675"
MEMBER_KSVERSION = "66314b202608031502"
MEMBER_KSMPID = "wbDreamwxd275b0214ea13dc8"
MEMBER_CMPAPPKEY = "xamzx1"
MEMBER_REFERER = "https://servicewechat.com/undefined/devtools/page-frame.html"
MEMBER_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1 "
    "wechatdevtools/2.02.2607161 MicroMessenger/8.0.5 Language/zh_CN webview/"
)

# 进程内缓存：mpsessid -> (写入时间戳, member dict)
_member_cache: "dict[str, tuple[float, dict]]" = {}
_cache_lock = threading.Lock()


# ──────────────────────────── 纯函数（已对 .so 验证一致）────────────────────────────
def _clean_mobile(value: Any) -> "str | None":
    """手机号清洗：仅去首尾空白（保留内部空格/连字符），空值返回 None。"""
    if not value:
        return None
    s = str(value).strip()
    return s or None


def _put(target: dict, key: str, value: Any) -> None:
    """写入字段，但跳过 None 与精确空字符串（''）；0 / False / [] 等照常写入。"""
    if value is None or value == "":
        return
    target[key] = value


def _safe_member(data: dict) -> dict:
    """把接口 data 段归一化成内部会员字段（只认下列源键，顺序固定）。"""
    out: dict = {}
    _put(out, "display_name", data.get("name"))
    _put(out, "member_id", data.get("memberId"))
    _put(out, "card_no", data.get("cardNo"))
    _put(out, "member_level_name", data.get("memberLevelName"))
    _put(out, "points", data.get("point"))
    _put(out, "effective_growth_value", data.get("effectiveGrowthValue"))
    _put(out, "membership_end_time", data.get("endTime"))
    mobile = _clean_mobile(data.get("mobile"))
    _put(out, "mobile", mobile)
    _put(out, "mobile_masked", mobile)
    return out


# ──────────────────────────── 请求头 ────────────────────────────
def _headers(mpsessid: str) -> "dict[str, str]":
    """构造 getMemberInfo 的固定请求头（顺序还原）。登录态经 mpsessid 头透传。"""
    return {
        "ksclient": MEMBER_KSCLIENT,
        "mpsessid": mpsessid,
        "user-agent": MEMBER_USER_AGENT,
        "content-type": "application/x-www-form-urlencoded",
        "ksversion": MEMBER_KSVERSION,
        "cmpappkey": MEMBER_CMPAPPKEY,
        "ksmpid": MEMBER_KSMPID,
        "accept": "*/*",
        "referer": MEMBER_REFERER,
    }


# ──────────────────────────── 对外取数 ────────────────────────────
def fetch_current_member(mpsessid: str) -> dict:
    """读取当前登录会员信息。

    返回统一结构：
      - 成功：{"found": True, "member": {...}, "source": "westbund_member_api", "cached": bool}
      - 无登录态：{"found": False, "reason": "missing_session", "message": ...}
      - 接口不可达：{"found": False, "reason": "upstream_unavailable", "message": ...}
      - 登录失效（无 data 段）：{"found": False, "reason": "invalid_or_expired_session",
                                "error_code": ..., "message": ...}
      - 有 data 但无可用业务字段：{"found": False, "reason": "empty_member", "message": ...}
    """
    if not mpsessid:
        return {
            "found": False,
            "reason": "missing_session",
            "message": "当前请求未携带小程序登录会话，无法读取会员信息。",
        }

    now = time.time()
    with _cache_lock:
        hit = _member_cache.get(mpsessid)
        if hit is not None and (now - hit[0]) < MEMBER_CACHE_SECONDS:
            return {
                "found": True,
                "member": hit[1],
                "source": "westbund_member_api",
                "cached": True,
            }

    try:
        resp = httpx.post(
            MEMBER_INFO_URL,
            headers=_headers(mpsessid),
            content=b"",
            timeout=MEMBER_API_TIMEOUT,
        )
        body = resp.json()
    except Exception:
        return {
            "found": False,
            "reason": "upstream_unavailable",
            "message": "会员系统暂时无法访问，请稍后再试。",
        }

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        # 后端登录失效时通常不返回 data 段
        return {
            "found": False,
            "reason": "invalid_or_expired_session",
            # 原实现从 data 段的错误码字段读取；登录失效时 data 缺失，故实测恒为 None
            "error_code": data.get("errorCode") if isinstance(data, dict) else None,
            "message": "小程序登录会话可能已失效，请重新登录后再试。",
        }

    member = _safe_member(data)
    if not member:
        return {
            "found": False,
            "reason": "empty_member",
            "message": "会员接口未返回可用的会员业务信息。",
        }

    with _cache_lock:
        _member_cache[mpsessid] = (now, member)
    return {
        "found": True,
        "member": member,
        "source": "westbund_member_api",
        "cached": False,
    }
