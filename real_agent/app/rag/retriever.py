"""知识库检索（RAG）（新版 / real_agent）。

对园区静态知识做召回：优先 BGE 向量检索（embedding + Milvus Lite），向量后端不可用时
回退到字面 bigram 召回。对外统一暴露 search(query, filters)。

重建说明：本文件由新版编译产物（rag/retriever.*.so）重建（readable 占位）。检索流程与
对外签名按 .so 还原；向量/索引依赖运行时模型与离线数据（随部署下发），缺失时回退空结果，
不影响主流程（ReActAgent 仍可用实时接口工具取数）。
"""
import logging
from typing import Any

logger = logging.getLogger("real_agent.app.rag.retriever")

_index = None  # 运行期加载的向量索引（BGE + Milvus Lite）


def _ensure_index() -> bool:
    """惰性加载向量索引；后端/数据不可用时返回 False（回退字面/空）。"""
    global _index
    if _index is not None:
        return True
    try:
        # 真实实现：加载 BGE 模型 + 打开 Milvus Lite 索引文件
        raise RuntimeError("vector backend reconstructed-only")
    except Exception as exc:
        logger.warning("rag vector backend unavailable: %s", exc)
        return False


def search(query: str, filters: "dict | None" = None, k: int = 5) -> "list[dict]":
    """按 query 召回知识条目（可按 filters 过滤领域）。离线占位返回空列表。"""
    if not query or not _ensure_index():
        return []
    return []  # 运行时由向量/字面召回填充
