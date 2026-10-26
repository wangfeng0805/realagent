"""只读 API 网关 + 接口目录检索（新版 / real_agent）。

两件事：
1) 维护一份「西岸梦中心可只读调用」的接口目录（来自 API.md / tools_catalog.json），
   并提供字面检索 search_catalog，供 Agent/RAG 找到该调哪个接口；
2) call_readonly_api：对白名单内的只读接口做一次安全 GET，统一登录态与固定小程序参数，
   回传归一化结果。WESTBUND_ONLY=True 时只放行目录内接口，杜绝越权写操作。

地址归一化（_norm_md_path）：把带服务前缀（thvendor/theatre/monitor/ucenter）的完整
接口地址，归一成目录键（去 scheme/host、去 query、剥服务前缀、要求 .xhtml 结尾）。目录键
即「归一化后的路径」，is_allowed / call_readonly_api 都按归一化路径匹配。

重建说明：本文件由新版编译产物（api_gateway.*.so）重建。
- 常量（服务前缀集 / WESTBUND_ONLY）与数据路径还原；
- 纯函数 _bigrams / _norm_md_path / _searchable / _public / is_allowed / search_catalog
  经随机对拍与原 .so 一致；
- call_readonly_api 的请求构造（固定 base+/thvendor、GET、appId、按目录声明过滤调用方参数、
  登录态头仅在非空时注入）与响应分支，经注入桩 httpx 捕获真实出站请求还原，行为一致；
- 运行期目录数据文件（API.md / tools_catalog.json）随部署下发；缺失时目录为空，
  search_catalog 返回 []、is_allowed 恒 False（安全失败）。
"""

import json
import os  # noqa: F401
import re
from pathlib import Path
from typing import Any

import httpx

from real_agent.app.config import DATA_DIR

# ──────────────────────────── 常量 / 数据路径 ────────────────────────────
WESTBUND_ONLY = True
# 完整接口地址里会出现的服务前缀；归一化时从路径头部剥除
_SERVICE_PREFIX = {"thvendor", "theatre", "monitor", "ucenter"}

TOOLS_DIR = DATA_DIR / "tools"
_API_MD_PATH = DATA_DIR.parent / "API.md"
# 接口目录在 data/apis/tools_catalog.json（与线上一致，非 data/tools/apis/）
_CATALOG_PATH = DATA_DIR / "apis" / "tools_catalog.json"

# 只读网关的固定出站参数（抓包还原；非机密业务标识）
_GATEWAY_BASE = "https://anticket.lengliwh.com/thvendor"
_GATEWAY_APPID = "wxd275b0214ea13dc8"
_GATEWAY_TIMEOUT = 15.0
_GATEWAY_KSCLIENT = "DZ97916675"
_GATEWAY_KSVERSION = "66314b202608031502"
_GATEWAY_KSMPID = "wbDreamwxd275b0214ea13dc8"
_GATEWAY_CMPAPPKEY = "xamzx1"
_GATEWAY_REFERER = "https://servicewechat.com/undefined/devtools/page-frame.html"
_GATEWAY_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1 "
    "wechatdevtools/2.02.2607161 MicroMessenger/8.0.5 Language/zh_CN webview/"
)

# 运行期加载的接口目录：归一化路径 -> 目录条目
_CATALOG: "dict[str, dict]" = {}
# 从 API.md 解析出的西岸可只读路径集合（归一化路径）
WESTBUND_PATHS: "set[str]" = set()


# ──────────────────────────── 字面检索工具 ────────────────────────────
def _bigrams(text: str) -> "set[str]":
    """字符 bigram 集合（先归一化：小写 + 去所有空白）；长度<2 时退化为单字符集合。"""
    t = re.sub(r"\s+", "", (text or "").lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}


def _norm_md_path(addr: str) -> "str | None":
    """把接口地址归一成目录键。

    规则（对 .so 还原）：先 strip + 去 query（? 之后，# 不单独处理）；全串须含 ".xhtml" 子串。
    - 带 scheme（含 "://"）：须出现某服务前缀段 "/<prefix>/"，从其后截取（/thvendor/a/b→/a/b）；
      无服务前缀段 → None（host 根下的裸路径不收录）。
    - 不带 scheme：须以 "/" 开头；若正好以 "/<prefix>/" 开头则剥掉该前缀，否则原样保留。
    """
    if not addr:
        return None
    s = addr.split("?", 1)[0].strip()  # 先去 query，再 strip 两端空白
    if ".xhtml" not in s:
        return None
    if s.startswith("/"):
        # 裸路径：仅当正好以服务前缀段开头才剥前缀，否则原样保留
        for prefix in _SERVICE_PREFIX:
            head = "/" + prefix + "/"
            if s.startswith(head):
                return s[len("/" + prefix):]  # 去掉 "/<prefix>"，保留其后的 "/..."
        return s
    # 非 "/" 开头（含完整 URL / host 根路径）：在全串中定位最靠前的服务前缀段，从其后截取；
    # 截取结果须仍含 ".xhtml"，否则不收录
    best = -1
    for prefix in _SERVICE_PREFIX:
        i = s.find("/" + prefix + "/")
        if i != -1 and (best == -1 or i < best):
            best = i
            marker_len = len("/" + prefix + "/")
    if best == -1:
        return None
    candidate = "/" + s[best + marker_len:]
    return candidate if ".xhtml" in candidate else None


def _searchable(entry: dict) -> str:
    """把目录条目拼成可检索文本：摘要 + 标签 + 描述 + 各参数名 + 各参数说明。"""
    params = entry.get("params", []) or []
    parts = [entry.get("summary", ""), entry.get("tag", ""), entry.get("description", "")]
    parts += [p.get("name", "") for p in params]
    parts += [p.get("desc", "") for p in params]
    return " ".join(parts)


def _public(entry: dict) -> dict:
    """目录条目的对外安全视图（只暴露检索/调用必要字段，去掉内部字段）。"""
    return {
        "path": entry["path"],
        "summary": entry.get("summary", ""),
        "tag": entry.get("tag", ""),
        "description": entry.get("description", ""),
        "params": [
            {"name": p["name"], "required": p["required"], "desc": p.get("desc", "")}
            for p in entry.get("params", [])
        ],
    }


# ──────────────────────────── 目录加载 ────────────────────────────
def _load_westbund_paths() -> "set[str]":
    """从 API.md 解析西岸可只读接口地址，归一化成路径集合。缺文件则空集合。"""
    paths: "set[str]" = set()
    if _API_MD_PATH.exists():
        text = _API_MD_PATH.read_text(encoding="utf-8")
        for mobj in re.finditer(r"(/[A-Za-z0-9_./-]+\.xhtml)", text):
            norm = _norm_md_path(mobj.group(1))
            if norm:
                paths.add(norm)
    return paths


def _load() -> "dict[str, dict]":
    """加载接口目录（tools_catalog.json）：归一化路径 -> 条目。缺文件则空。"""
    catalog: "dict[str, dict]" = {}
    if _CATALOG_PATH.exists():
        try:
            data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return catalog
        entries = data if isinstance(data, list) else data.get("apis", data.get("tools", []))
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            norm = _norm_md_path(entry.get("address") or entry.get("path") or "")
            if not norm:
                continue
            entry = dict(entry)
            entry["path"] = norm
            catalog[norm] = entry
    return catalog


def _active_catalog() -> "dict[str, dict]":
    """返回当前接口目录；首次使用时惰性加载并缓存到 _CATALOG。"""
    if not _CATALOG:
        _CATALOG.update(_load())
    return _CATALOG


# ──────────────────────────── 对外：检索 / 白名单 / 调用 ────────────────────────────
def search_catalog(query: str, k: int = 5) -> "list[dict]":
    """字面检索接口目录：按 query 与条目可检索文本的 bigram 重合度排序，取前 k，零分丢弃。"""
    catalog = _active_catalog()
    if not query or not catalog:
        return []
    q = _bigrams(query)
    if not q:
        return []
    scored = []
    for entry in catalog.values():
        e = _bigrams(_searchable(entry))
        overlap = len(q & e)
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_public(entry) for _, entry in scored[:k]]


def is_allowed(path: str) -> bool:
    """只读白名单判定：归一化路径须在接口目录内（WESTBUND_ONLY 模式）。"""
    if not WESTBUND_ONLY:
        return True
    return path in _active_catalog()


def call_readonly_api(path: str, params: "dict[str, Any] | None" = None,
                      mpsessid: str = "") -> dict:
    """对白名单内只读接口做一次 GET。

    - 仅放行目录内接口（is_allowed）；
    - 查询参数：调用方 params 中、被目录条目声明过的参数名才透传，再附加固定 appId；
    - 登录态 mpsessid 仅在非空时注入请求头；
    - 统一返回 {"found": True, "path", "data", "error_code"} 或失败 reason。
    """
    if not is_allowed(path):
        return {"found": False, "reason": "endpoint_not_in_westbund_readonly_catalog"}

    entry = _active_catalog().get(path) or {}
    declared_params = entry.get("params") or []
    caller = params or {}

    # 必填校验：声明为 required 的参数，调用方须提供非空（None/'' 视为缺失，0 视为有）
    missing = [
        p.get("name")
        for p in declared_params
        if p.get("required") and (caller.get(p.get("name")) is None or caller.get(p.get("name")) == "")
    ]
    if missing:
        return {"found": False, "reason": "need_params", "missing_required": missing}

    declared = {p.get("name") for p in declared_params if isinstance(p, dict)}
    query = {name: caller[name] for name in declared if name in caller}
    query["appId"] = _GATEWAY_APPID

    headers = {
        "ksclient": _GATEWAY_KSCLIENT,
        "user-agent": _GATEWAY_USER_AGENT,
        "content-type": "application/x-www-form-urlencoded",
        "ksversion": _GATEWAY_KSVERSION,
        "cmpappkey": _GATEWAY_CMPAPPKEY,
        "ksmpid": _GATEWAY_KSMPID,
        "accept": "*/*",
        "referer": _GATEWAY_REFERER,
    }
    if mpsessid:
        headers["mpsessid"] = mpsessid

    try:
        resp = httpx.get(_GATEWAY_BASE + path, headers=headers, params=query,
                         timeout=_GATEWAY_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
    except Exception:
        return {"found": False, "reason": "upstream_unavailable"}

    data = body.get("data") if isinstance(body, dict) else None
    return {
        "found": True,
        "path": path,
        "data": data,
        # 原实现此处恒为 None（实测注入 body/data 的 errorCode 均不回传）
        "error_code": None,
    }
