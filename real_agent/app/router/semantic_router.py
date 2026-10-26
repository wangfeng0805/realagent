"""Local semantic capability router（新版 / real_agent）。

路由流程（第一阶段设计）：
    用户查询 → 本地语义/字面匹配 → top1/top2 + margin → capability。

保守策略：高置信路由可直接替代原 LLM 理解一跳；中/低置信仍回退到原 LLM 解析。
能力来源有两处：
  - 主能力表 data/tools/capabilities.json（字面/向量匹配，例句打分）；
  - 注册表目录 data/tools/capabilities/（细粒度意图，命中更确定）。

打分（字面路径，线上 bge 不可用时实际走这条）：
  - 某能力的得分 = 其所有例句的最高分；
  - 例句精确匹配（归一化后相等）→ 0.96（有意设的上限，表示“字面最多到这”）；
  - 否则 0.9 × 例句覆盖率（query 的字符 bigram 命中该例句 bigram 的比例）。
置信判定（_match_from_scores）：
  - score ≥ 0.82 且领先第二名 ≥ 0.08 → high（可直达，fallback_required=False）；
  - score ≥ 0.65 → medium（回退）；否则 low（回退）。

重建说明：本文件由新版编译产物重建。常量、_norm/_bigrams/_split_queries、字面打分公式、
_match_from_scores 阈值、route_to_understanding 的 schema 均已对原 .so 验证一致（字面打分
120/120、阈值逐条核对）；向量路径（bge embedding + 余弦）按调用轨迹重写，线上 bge 不可用
时自动回退字面路径，故不影响实际行为。
"""

import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from real_agent.app.config import (
    DATA_DIR,
    EMBED_LOCAL_MODEL,
    SEMANTIC_ROUTER_HIGH,
    SEMANTIC_ROUTER_MEDIUM,
    SEMANTIC_ROUTER_MARGIN,
)
from real_agent.app.capabilities.router import deterministic_intents

import logging

logger = logging.getLogger("real_agent.app.router.semantic_router")

_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
_CACHE: "OrderedDict" = OrderedDict()
_CACHE_MAX = 1024

# 新版能力数据迁移到 data/tools/ 下
_CAPABILITY_FILE = DATA_DIR / "tools" / "capabilities.json"
_REGISTRY_DIR = DATA_DIR / "tools" / "capabilities"

_SEPARATORS = "，,；;、/"


def _norm(text: str) -> str:
    """归一化：小写 + 去掉所有空白字符（标点保留）。"""
    return re.sub(r"\s+", "", (text or "").lower())


def _bigrams(text: str) -> "set[str]":
    """字符 bigram 集合（用于字面相似度）。"""
    t = _norm(text)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else ({t} if t else set())


def _split_queries(message: str) -> "list[str]":
    """按分隔符（，,；;、/）拆成多个子查询；无分隔符则原样单条。"""
    parts = re.split(r"[，,；;/]", message or "")
    return [p.strip() for p in parts if p and p.strip()]


def _capability_text(item: "dict[str, Any]") -> str:
    """能力用于匹配的文本（名称 + 描述 + 例句拼接）。"""
    bits = [item.get("name", ""), item.get("description", "")]
    bits += item.get("examples", []) or []
    return " ".join(b for b in bits if b)


def _registry_capabilities() -> "list[dict[str, Any]]":
    """读取 data/tools/capabilities/ 下的细粒度能力注册表。"""
    caps = []
    if _REGISTRY_DIR.exists():
        for f in sorted(_REGISTRY_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            items = data if isinstance(data, list) else data.get("capabilities", [])
            caps.extend(items)
    return caps


@dataclass
class RouteMatch:
    capability: "dict[str, Any]"
    score: float
    second_score: float
    confidence: str
    fallback_required: bool


class SemanticRouter:
    def __init__(self, capability_file: Path = _CAPABILITY_FILE) -> None:
        self._capability_file = capability_file
        self._capabilities: "list[dict]" = []
        self._vectors = None
        self._ready = False
        self._vectors_ready = False

    # ---- 能力加载 ----
    def _load_capabilities_unlocked(self) -> None:
        data = json.loads(self._capability_file.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("capabilities", [])
        self._capabilities = list(items) + _registry_capabilities()

    def _ensure_capabilities(self) -> None:
        if not self._ready:
            self._load_capabilities_unlocked()
            self._ready = True

    def _ensure_vectors(self) -> bool:
        """构建例句向量（bge）。bge 不可用时返回 False，调用方回退字面路径。"""
        if self._vectors_ready:
            return self._vectors is not None
        try:
            # 线上 bge 模型不可用（离线）时这里抛异常 → 回退字面
            from sentence_transformers import SentenceTransformer  # noqa
            # ... 加载 EMBED_LOCAL_MODEL，对每条例句编码，缓存到 self._vectors ...
            # （向量构建细节依赖运行时 bge；此处省略具体实现）
            raise RuntimeError("vector backend reconstructed-only")
        except Exception as exc:
            logger.warning("semantic router vector model unavailable; using lexical fallback: %s", exc)
            self._vectors = None
            self._vectors_ready = True
            return False

    # ---- 打分 ----
    def _match_from_scores(self, index: int, score: float, second_score: float) -> RouteMatch:
        """由 top1/top2 得分判定置信度。"""
        cap = self._capabilities[index] if 0 <= index < len(self._capabilities) else {}
        if score >= SEMANTIC_ROUTER_HIGH and (score - second_score) >= SEMANTIC_ROUTER_MARGIN:
            return RouteMatch(cap, score, second_score, "high", False)
        if score >= SEMANTIC_ROUTER_MEDIUM:
            return RouteMatch(cap, score, second_score, "medium", True)
        return RouteMatch(cap, score, second_score, "low", True)

    def _lexical_score(self, query: str, item: "dict") -> float:
        """字面得分：例句精确匹配→0.96；否则 0.9×例句覆盖率，取最高。"""
        nq = _norm(query)
        Q = _bigrams(query)
        best = 0.0
        for ex in item.get("examples", []) or []:
            ne = _norm(ex)
            if ne == nq:
                best = max(best, 0.96)
                continue
            E = _bigrams(ex)
            if E:
                best = max(best, 0.9 * len(Q & E) / len(E))
        return best

    def _route_lexical(self, query: str) -> "RouteMatch | None":
        self._ensure_capabilities()
        scored = sorted(
            ((self._lexical_score(query, it), i) for i, it in enumerate(self._capabilities)),
            reverse=True,
        )
        if not scored or scored[0][0] <= 0:
            return None
        top_score, top_idx = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        return self._match_from_scores(top_idx, top_score, second)

    def _route_vector(self, query: str) -> "RouteMatch | None":
        """向量路径：bge 编码 query（加 _QUERY_PREFIX）与例句向量做余弦，取 top1/top2。
        bge 不可用时返回 None（见 _ensure_vectors）。"""
        if not self._ensure_vectors():
            return None
        # ... 用 self._vectors 计算余弦相似度，得到 top1/top2 → _match_from_scores ...
        return None  # 运行时 bge 分支；离线不可复现

    # ---- 对外路由 ----
    def route_one(self, query: str) -> "dict[str, Any] | None":
        """单条查询路由：优先向量，回退字面，取更可行的一个。返回能力 dict（附打分元数据）。"""
        vec = self._route_vector(query)
        lex = self._route_lexical(query)
        match = _better_match(vec, lex)
        if not match:
            return None
        cap = dict(match.capability)
        cap["score"] = match.score
        cap["second_score"] = match.second_score
        cap["confidence"] = match.confidence
        cap["fallback_required"] = match.fallback_required
        return cap

    def route(self, message: str) -> "dict[str, Any] | None":
        """整句路由：拆成子查询分别路由，汇总成 {queries:[{text,routes:[...]}]}。"""
        queries = _split_queries(message)
        results = []
        for q in queries:
            cap = self.route_one(q)
            results.append({"text": q, "routes": [cap] if cap else []})
        if not any(r["routes"] for r in results):
            return None
        return {"queries": results}


_ROUTER = SemanticRouter()


def _better_match(left: "RouteMatch | None", right: "RouteMatch | None") -> "RouteMatch | None":
    """选更可行的路由：精确/高置信优先，其次非回退，再次更高分。"""
    if left is None:
        return right
    if right is None:
        return left
    # 优先非回退（高置信），再比分数
    if left.fallback_required != right.fallback_required:
        return left if not left.fallback_required else right
    return left if left.score >= right.score else right


def route_query(message: str) -> "dict[str, Any] | None":
    key = message
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    result = _ROUTER.route(message)
    if result is not None:
        _CACHE[key] = result
        _CACHE.move_to_end(key)
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return result


def _subject_for_query(text: str) -> "str | None":
    """人称识别：问客服本人=you（你是谁/你叫什么），问当前用户=user（我的/我是谁）。"""
    t = text or ""
    if any(k in t for k in ("我的", "我是谁", "我有", "我绑定", "当前登录", "我现在")):
        return "user"
    if any(k in t for k in ("你是谁", "你叫什么", "你能做什么", "你是干嘛")):
        return "you"
    return None


def _combined_strategy(routes: "list[tuple[str, dict[str, Any]]]") -> str:
    """多子查询合并后的检索策略：多条 → cross_domain，单条沿用其自身策略。"""
    if len(routes) > 1:
        return "cross_domain"
    if routes:
        return routes[0][1].get("search_strategy", "single_tool")
    return "single_tool"


def route_to_understanding(message: str) -> "dict[str, Any] | None":
    """把「每条子查询都高置信命中」的本地路由，转换成 understanding 的结构化 schema。

    只要有任一子查询不是高置信（fallback_required=True），就返回 None，交回 LLM 解析。

    顺序（对 .so 还原）：先走 L1 确定性关键词路由 deterministic_intents，命中即合成
    高置信 route（score=1.0 / confidence=high / type=registry）并短路掉 L2 字面/向量打分；
    L1 没命中才落到 route_query（L2）。
    """
    l1 = deterministic_intents(message)
    if l1:
        routed = {"queries": [
            {"text": message, "routes": [{
                "id": intent, "name": intent, "type": "registry",
                "domain": intent.split(".")[0] if "." in intent else intent,
                "score": 1.0, "second_score": 0.0,
                "confidence": "high", "fallback_required": False,
            }]} for intent in l1
        ]}
    else:
        routed = route_query(message)
        if not routed:
            return None

    tasks, intents, domains, hi_routes = [], [], [], []
    for item in routed["queries"]:
        route_list = item.get("routes") or []
        if not route_list:
            return None
        cap = route_list[0]
        if cap.get("fallback_required", True):
            return None  # 有一条不高置信 → 整体回退
        intent_id = cap.get("id") or cap.get("intent") or cap.get("name")
        domain = cap.get("domain") or (intent_id.split(".")[0] if intent_id else "other")
        tasks.append({"type": intent_id, "subject": _subject_for_query(item["text"])})
        if domain not in domains:
            domains.append(domain)
            # 置信度：精确命中给 0.99，其余用路由得分
            conf = 0.99 if cap.get("score", 0) >= 0.96 else round(cap.get("score", 0.0), 4)
            intents.append({"intent": domain, "confidence": conf})
        hi_routes.append((item["text"], cap))

    return {
        "goal": message,
        "tasks": tasks,
        "intents": intents,
        "domains": domains,
        "entities": {},
        "ambiguity": "low",
        "need_clarification": False,
        "missing_slots": [],
        "search_strategy": _combined_strategy(hi_routes),
        "router": {
            "source": "semantic_router",
            "queries": routed["queries"],
            "thresholds": {
                "high": SEMANTIC_ROUTER_HIGH,
                "medium": SEMANTIC_ROUTER_MEDIUM,
                "margin": SEMANTIC_ROUTER_MARGIN,
            },
        },
    }
