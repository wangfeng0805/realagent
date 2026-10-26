"""底座工具：知识库检索 / 可调用接口检索 / 调用只读接口（新版 / real_agent）。

ReActAgent 在任何领域都可用的三件「底座」工具：
- search_knowledge_base(query)：RAG 召回园区静态知识；
- search_apis(query)：在接口目录里找「该调哪个只读接口」；
- call_api(path, params)：对白名单内只读接口发一次安全 GET。

重建说明：由 .so 重建（readable）。委托 rag.retriever + integrations.api_gateway（均已重建）。
"""
from typing import Any
from real_agent.app.integrations import api_gateway


def _mpsessid(config: "Any") -> str:
    try:
        return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception:
        return ""


def search_knowledge_base(query: str) -> dict:
    """RAG 召回静态知识。"""
    try:
        from real_agent.app.rag import retriever
        return {"found": True, "results": retriever.search(query)}
    except Exception:
        return {"found": False, "reason": "knowledge_unavailable"}


def search_apis(query: str) -> dict:
    """在接口目录里检索可调用的只读接口。"""
    return {"found": True, "apis": api_gateway.search_catalog(query)}


def call_api(config: "Any", path: str, params: "dict | None" = None) -> dict:
    """对白名单内只读接口发一次安全 GET（登录态来自 config）。"""
    return api_gateway.call_readonly_api(path, params or {}, _mpsessid(config))
