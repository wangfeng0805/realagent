"""Config-driven Capability Registry（新版 / real_agent）。

Router code deals in stable business intents. This module owns the mapping from
intent to API/RAG/function source, request defaults, validation and rendering.

能力注册表来自 data/tools/capabilities/*.json，每条配置形如：
    {
      "intent": "member.points",          # 稳定业务意图（L1/语义路由产出的就是它）
      "ability": "member",
      "source": "function" | "api" | "rag",
      "function": "fetch_current_member",  # source=function 时，查 _FUNCTIONS
      "path": "/member/.../x.xhtml",       # source=api 时，直接调小程序接口
      "filters": {"domain": "member"},     # source=rag 时，RAG 检索过滤
      "required_context": ["mpsessid"],    # 缺这些上下文则不可直达（提示登录等）
      "default_params": {"area_type": "westbund"},
      "direct_response": true,              # 能否直接产出成稿（走 renderer）
      "renderer": "member.points",          # 交给 capabilities.renderer 渲染
      "examples": [...]                     # 供语义路由匹配
    }

execute() 按 source 分派取数 → renderer 渲染成稿 → 返回 CapabilityResult；
execute_many() 并行执行多个意图（线程池 + 超时），用于一句多意图。

重建说明：本文件由新版编译产物重建。类结构、方法签名、配置 schema、_FUNCTIONS 映射
均从 .so 还原；分派与校验逻辑按调用轨迹 + 配置语义重写（readable，便于改）。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json

from real_agent.app.config import DATA_DIR
from real_agent.app.capabilities.renderer import render
from real_agent.app.integrations.member_api import fetch_current_member
from real_agent.app.integrations.miniprogram_api import (
    api_get_path,
    fetch_coupon_count,
    fetch_expiring_points,
    fetch_member_plates,
    fetch_next_level_progress,
    fetch_parking_status,
    fetch_point_records,
)
from real_agent.app.rag import retriever

logger = logging.getLogger("real_agent.app.capabilities.registry")

CAPABILITY_DIR = DATA_DIR / "tools" / "capabilities"

# source=function 时，配置里的 function 名 → 实际取数函数
_FUNCTIONS: "dict[str, Callable[..., dict]]" = {
    "fetch_current_member": fetch_current_member,
    "fetch_coupon_count": fetch_coupon_count,
    "fetch_expiring_points": fetch_expiring_points,
    "fetch_member_plates": fetch_member_plates,
    "fetch_next_level_progress": fetch_next_level_progress,
    "fetch_parking_status": fetch_parking_status,
    "fetch_point_records": fetch_point_records,
}

_EXECUTOR = ThreadPoolExecutor(max_workers=8)


@dataclass
class CapabilityResult:
    intent: str
    found: bool
    payload: dict
    answer: "str | None"
    latency_ms: int
    fallback_reason: str = ""


def _context_value(context: dict, key: str) -> Any:
    return (context or {}).get(key)


def _call_function(fn: "Callable[..., dict]", context: dict, params: dict) -> dict:
    """调用取数函数：登录态从 context.mpsessid 注入，其余参数透传。"""
    mpsessid = _context_value(context, "mpsessid") or ""
    try:
        return fn(mpsessid=mpsessid, **params)
    except TypeError:
        # 个别函数签名不吃 **params，退化为只传登录态
        return fn(mpsessid=mpsessid)


def _elapsed(t0: float) -> int:
    return int((time.time() - t0) * 1000)


class CapabilityRegistry:
    def __init__(self, directory: Path = CAPABILITY_DIR) -> None:
        self._directory = directory
        self._items: "dict[str, dict]" = {}
        self._loaded = False

    def _load(self) -> "dict[str, dict]":
        items: dict = {}
        if self._directory.exists():
            for f in sorted(self._directory.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    logger.warning("bad capability file: %s", f, exc_info=True)
                    continue
                for it in (data if isinstance(data, list) else data.get("capabilities", [])):
                    intent = it.get("intent")
                    if intent:
                        items[intent] = it
        return items

    def _validate(self) -> None:
        """基本校验：function 型意图的 function 必须在 _FUNCTIONS 中注册。"""
        for intent, it in self._items.items():
            if it.get("source") == "function" and it.get("function") not in _FUNCTIONS:
                logger.warning("intent %s references unknown function %s", intent, it.get("function"))

    def _ensure(self) -> None:
        if not self._loaded:
            self._items = self._load()
            self._validate()
            self._loaded = True

    def list(self) -> "list[dict]":
        self._ensure()
        return list(self._items.values())

    def get(self, intent: str) -> "dict | None":
        self._ensure()
        return self._items.get(intent)

    def _execute_item(self, item: dict, context: dict) -> dict:
        """按 source 分派取数，返回原始 payload（dict，含 found/reason 等）。"""
        # 必填上下文校验（如 mpsessid）
        for key in item.get("required_context", []) or []:
            if not _context_value(context, key):
                return {"found": False, "reason": "missing_context", "missing_required": [key]}

        params = dict(item.get("default_params", {}) or {})
        source = item.get("source")

        if source == "function":
            fn = _FUNCTIONS.get(item.get("function"))
            if fn is None:
                return {"found": False, "reason": "no_function"}
            return _call_function(fn, context, params)

        if source == "api":
            mpsessid = _context_value(context, "mpsessid") or ""
            require_session = "mpsessid" in (item.get("required_context") or [])
            return api_get_path(item["path"], mpsessid, params, require_session=require_session)

        if source == "rag":
            query = _context_value(context, "query") or _context_value(context, "message") or ""
            return retriever.search(query, filters=item.get("filters") or {})

        return {"found": False, "reason": "unsupported_source"}

    def execute(self, intent: str, context: "dict | None" = None) -> CapabilityResult:
        t0 = time.time()
        context = context or {}
        item = self.get(intent)
        if not item:
            return CapabilityResult(intent, False, {}, None, _elapsed(t0), "no_capability")

        payload = self._execute_item(item, context)
        found = bool(payload) and payload.get("found", True) and not payload.get("reason")
        answer = None
        fallback_reason = "" if found else (payload.get("reason") or "no_data")
        if found and item.get("direct_response"):
            answer = render(item.get("renderer") or intent, payload)
            if not answer:
                fallback_reason = "no_direct_answer"
        return CapabilityResult(intent, found, payload, answer, _elapsed(t0), fallback_reason)

    def execute_many(self, intents: "list[str]", context: "dict | None" = None,
                     timeout: float = 3.0) -> "list[CapabilityResult]":
        """并行执行多个意图，单个超时不拖累整体。"""
        context = context or {}
        futures = {intent: _EXECUTOR.submit(self.execute, intent, context) for intent in intents}
        results = []
        for intent in intents:
            try:
                results.append(futures[intent].result(timeout=timeout))
            except FutureTimeout:
                results.append(CapabilityResult(intent, False, {}, None, int(timeout * 1000), "timeout"))
            except Exception:
                logger.warning("capability %s failed", intent, exc_info=True)
                results.append(CapabilityResult(intent, False, {}, None, 0, "error"))
        return results


_REGISTRY: "CapabilityRegistry | None" = None


def get_registry() -> CapabilityRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CapabilityRegistry()
    return _REGISTRY
