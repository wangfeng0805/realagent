"""对话编排核心：漏斗 + ReActAgent 装配 + 流式步骤（新版 / real_agent）。

这是整套系统的「大脑」。main.py 的 /chat、/chat/stream 两个 Controller 直接调用本模块的
chat() / chat_stream()（二者由 main 原样 re-export）。

一条消息穿过的漏斗（对 .so 调用轨迹还原的真实顺序）：

  chat(message, ...):
    1) answer_live_program_request      活动列表直达（命中即返回卡片，不进模型）
    2) _understand_timed → understand   意图理解（input_normalize + L1/L2 路由 + 门控）
    3) _from_semantic_router            高置信语义直达判定
    4) build_static_knowledge_context   RAG/静态知识上下文
       build_understanding_context      理解 → 提示词上下文
       build_policy_context(domains)    领域话术/红线
    5) _scoped_tools(domains)           按领域裁剪工具集（命中域给子集，否则全 98）
    6) get_agent → ReActAgent.run       大模型 + 工具跑一轮（必要时多步取数）
    7) sanitize_customer_reply + append_action_cards   成稿净化 + 追加行动卡
    8) 落库

  chat_stream(message, ...):  前端实际用的流式版（截图那种步骤条）
    1) answer_live_merchant_request / answer_live_program_request  直达拦截
    2) _step(识别用户意图) → _understand_timed → _step(更新)
    3) _scoped_tools → get_agent 流式运行，每次工具调用 yield 一个 _step 事件
       （步骤标签「识别用户意图/查找可调用工具/生成智能建议」来自 step_labels.py）

重建说明：本文件由新版编译产物（agent/graph.*.so）重建，面向「读懂编排」。
- 工具分组（_TOOL_GROUPS 共 18 个领域 / 子域）、_IMG_ROOTS、_step 事件结构、_scoped_tools
  的域→工具映射规模，均对 .so 验证一致；
- chat() / chat_stream() 的漏斗顺序由对 .so 的调用轨迹还原；
- ReActAgent（LangGraph create_react_agent）的 token 级循环、工具调用解析由 langgraph/langchain
  负责，本模块是装配与串联点，相关部分为 readable 重写（标注 behavioral）。
"""

import json
import logging
import sqlite3  # noqa: F401  （会话历史持久化，真实实现用）
import time
from typing import Any

# —— 理解 / 路由 / 话术（漏斗前段，均在各自模块，graph 只编排）——
from real_agent.app.agent.understanding import understand, should_route_direct
from real_agent.app.capabilities.router import deterministic_intents
from real_agent.app.agent.policies import build_policy_context
from real_agent.app.agent.static_context import build_static_knowledge_context
from real_agent.app.agent.exception_reply import exception_reply

# —— 直达处理器（命中即出稿，不进大模型）——
from real_agent.app.agent.live_program import answer_live_program_request
from real_agent.app.agent.live_merchant import answer_live_merchant_request
from real_agent.app.agent.live_member import answer_live_member_request
from real_agent.app.agent.live_activity import answer_live_activity_request
from real_agent.app.agent.live_point_mall import answer_live_point_mall_request
from real_agent.app.agent.live_operational import answer_live_operational_request
from real_agent.app.agent.member_agent import answer_member_request
from real_agent.app.agent.official_app_knowledge import answer_official_app_request
from real_agent.app.agent.official_images import answer_official_image_request

# —— 成稿后处理 ——
from real_agent.app.agent.customer_reply import sanitize_customer_reply
from real_agent.app.agent.empty_reason import is_soft_unknown
from real_agent.app.agent.action_cards import append_action_cards, trailing_action_cards
from real_agent.app.agent.step_labels import (
    tool_label, tool_detail, tool_result_summary, format_args,
    understanding_detail, safe_tool_output,
)

# —— LLM / 能力 / 落库 ——
from real_agent.app.llm.client import (
    get_llm, rotate_deepseek_key, is_retriable_key_error,
)
from real_agent.app.capabilities.registry import get_registry
from real_agent.app.repositories.qa_log import log_qa
from real_agent.app.config import DEFAULT_MODEL, DATA_DIR

# —— 98 个业务工具（按模块分组导入；下方再按领域编成 _TOOL_GROUPS）——
from real_agent.app.tools.parking import *          # noqa: F401,F403
from real_agent.app.tools.member import *           # noqa: F401,F403
from real_agent.app.tools.ticketing import *        # noqa: F401,F403
from real_agent.app.tools.shopping import *         # noqa: F401,F403
from real_agent.app.tools.reservation import *      # noqa: F401,F403
from real_agent.app.tools.merchant_venue import *   # noqa: F401,F403
from real_agent.app.tools.content_common import *   # noqa: F401,F403
from real_agent.app.tools.knowledge import *        # noqa: F401,F403  (search_knowledge_base/search_apis/call_api)
from real_agent.app.tools.miniprogram import *      # noqa: F401,F403

logger = logging.getLogger("real_agent.app.agent.graph")

# ──────────────────────────── 常量 ────────────────────────────
# 本地图片根（成稿里引用 /knowledge-images/、/app-images/、/img/ 时的落盘位置）
_IMG_ROOTS = {
    "/knowledge-images/": DATA_DIR / "rag" / "images",
    "/app-images/": DATA_DIR / "rag" / "app_images",
    "/img/": DATA_DIR.parent / "web" / "img",
}

# 会话内已记住的会员事实（避免同一会话反复查会员接口）
_MEMBER_FACTS_BY_SESSION: "dict[str, dict]" = {}
# 已构建的 ReActAgent 缓存（按 model_id + 工具范围）
_agents: "dict[Any, Any]" = {}

# ── 工具分组：领域/子域 → 该域可用的工具集合 ──
# （变量名与分组规模对 .so 还原；此处用名字占位，实际为上面 import 进来的工具函数对象）
_PARKING_TOOLS = _dedup = None  # 见 _build_tool_groups()


def _tool(name: str):
    """按名取已导入的工具函数对象（import * 后在模块命名空间里）。"""
    return globals().get(name)


def _group(*names):
    return [t for t in (_tool(n) for n in names) if t is not None]


# 领域工具组（名称清单对 .so 还原；parking 9、member.points 6、member.profile 10 …）
_PARKING_TOOLS = _group(
    "parking_query_fee", "parking_list_lots", "parking_list_plates", "parking_lot_detail",
    "parking_coupons", "parking_available_coupons", "parking_discounts",
    "parking_payment_records", "parking_order_status",
)
_MEMBER_PROFILE = _group(
    "get_current_member_info", "member_get_personal_info", "member_list_certificates",
    "member_get_growth_detail", "member_level_benefits", "member_level_rules",
    "member_bind_status", "member_realname_status", "member_contact", "member_qrcode",
)
_MEMBER_POINTS = _group(
    "get_current_member_info", "get_member_upgrade_progress", "get_member_expiring_points",
    "member_point_detail", "member_mzx_points", "member_year_end_expiring_points",
)
_MEMBER_COUPON = _group(
    "get_member_coupon_count", "member_coupons_by_status", "member_coupon_others",
    "member_receivable_coupons", "member_coupon_detail",
)
_TICKETING_CATALOG = _group(
    "ticketing_list_programs", "ticketing_program_detail", "ticketing_program_categories",
    "ticketing_program_init", "ticketing_stadiums", "ticketing_stadium_detail",
    "ticketing_show_dates", "ticketing_show_schedules", "ticketing_schedules_by_date",
    "ticketing_ticket_types",
)
_TICKETING_ORDER = _group(
    "ticketing_list_show_orders", "ticketing_valid_tickets", "ticketing_list_seat_orders",
    "ticketing_seat_order_detail", "ticketing_order_extra", "ticketing_show_discounts",
    "ticketing_seat_discounts",
)
_TICKETING_INVOICE = _group(
    "ticketing_invoice_list", "ticketing_invoice_pdf", "ticketing_invoice_by_out_no",
    "ticketing_invoice_titles",
)
_RESERVATION = _group(
    "reservation_program_types", "reservation_search_programs", "reservation_program_detail",
    "reservation_periods", "reservation_order_detail", "reservation_list_orders",
    "reservation_can_reserve",
)
_SHOPPING_CATALOG = _group(
    "shopping_point_product_types", "shopping_point_products", "shopping_point_product_detail",
    "shopping_point_can_buy", "shopping_cultural_product_types", "shopping_cultural_products",
    "shopping_cultural_product_detail", "shopping_cultural_can_buy", "shopping_rent_products",
    "shopping_rent_product_detail", "shopping_provinces", "shopping_cities", "shopping_counties",
)
_SHOPPING_ORDER = _group(
    "shopping_order_list", "shopping_order_detail", "shopping_ems", "shopping_mall_discounts",
    "shopping_point_discounts", "shopping_rent_orders", "shopping_rent_order_detail",
)
_SHOPPING_ADDRESS = _group(
    "shopping_addresses", "shopping_address_detail", "shopping_freight_common",
    "shopping_freight_mall", "shopping_cultural_delivery_addresses",
    "shopping_point_delivery_addresses", "shopping_rent_delivery_addresses",
)
_MERCHANT_VENUE = _group(
    "merchant_detail", "merchant_guide_points", "search_miniprogram_merchants",
    "venue_list", "venue_detail", "facility_list", "facility_detail",
)
_CONTENT_COMMON = _group(
    "content_announcements", "content_announcement_detail", "content_dynamic_promotions",
    "content_guide", "content_faq",
)
_FLOOR_TOOLS = _group("search_knowledge_base", "search_apis", "call_api")


def _dedup_tools(*groups):
    """合并多组工具并按身份去重（同一工具在多域复用时只保留一个）。"""
    seen, out = set(), []
    for g in groups:
        for t in g or []:
            if id(t) not in seen:
                seen.add(id(t))
                out.append(t)
    return out


# 18 个领域/子域 → 工具集（父域含子域全集 + 通用底座工具）
_TOOL_GROUPS = {
    "parking": _dedup_tools(_PARKING_TOOLS, _FLOOR_TOOLS),
    "member": _dedup_tools(_MEMBER_PROFILE, _MEMBER_POINTS, _MEMBER_COUPON, _FLOOR_TOOLS),
    "member.profile": _dedup_tools(_MEMBER_PROFILE, _FLOOR_TOOLS),
    "member.points": _dedup_tools(_MEMBER_POINTS, _FLOOR_TOOLS),
    "member.coupon": _dedup_tools(_MEMBER_COUPON, _FLOOR_TOOLS),
    "ticketing": _dedup_tools(_TICKETING_CATALOG, _TICKETING_ORDER, _TICKETING_INVOICE, _FLOOR_TOOLS),
    "ticketing.catalog": _dedup_tools(_TICKETING_CATALOG, _FLOOR_TOOLS),
    "ticketing.order": _dedup_tools(_TICKETING_ORDER, _FLOOR_TOOLS),
    "ticketing.invoice": _dedup_tools(_TICKETING_INVOICE, _FLOOR_TOOLS),
    "reservation": _dedup_tools(_RESERVATION, _FLOOR_TOOLS),
    "shopping": _dedup_tools(_SHOPPING_CATALOG, _SHOPPING_ORDER, _SHOPPING_ADDRESS, _FLOOR_TOOLS),
    "shopping.catalog": _dedup_tools(_SHOPPING_CATALOG, _FLOOR_TOOLS),
    "shopping.order": _dedup_tools(_SHOPPING_ORDER, _FLOOR_TOOLS),
    "shopping.address": _dedup_tools(_SHOPPING_ADDRESS, _FLOOR_TOOLS),
    "merchant_venue": _dedup_tools(_MERCHANT_VENUE, _FLOOR_TOOLS),
    "content_common": _dedup_tools(_CONTENT_COMMON, _FLOOR_TOOLS),
    "knowledge": _dedup_tools(_FLOOR_TOOLS),
    "transport": _dedup_tools(_PARKING_TOOLS, _FLOOR_TOOLS),
}

# 全量工具（未命中领域或跨域过多时的兜底）
_ALL_TOOLS = _dedup_tools(*_TOOL_GROUPS.values())


# ──────────────────────────── 工具裁剪 ────────────────────────────
def _scoped_tools(domains: "list[str] | None") -> "tuple[list, str]":
    """按理解出的领域裁剪工具集：

    - 命中一个或多个已知领域 → 取这些领域工具的并集，scope 标签为 "域1,域2"；
    - 领域为空 / 含未知领域（如 navigation）→ 回退全量 98 工具，scope="all"。
    """
    if not domains:
        return _ALL_TOOLS, "all"
    picked, labels = [], []
    for d in domains:
        group = _TOOL_GROUPS.get(d)
        if group is None:
            return _ALL_TOOLS, "all"      # 有一个域不认识就给全量，避免漏工具
        picked.append(group)
        labels.append(d)
    return _dedup_tools(*picked), ",".join(labels)


# ──────────────────────────── 运行配置 / 步骤事件 ────────────────────────────
def _run_config(session_id: str, user_id: "str | None", mpsessid: "str | None",
                knowledge_context: "str | None" = None,
                understanding_context: "str | None" = None,
                policy_context: "str | None" = None) -> dict:
    """组装 LangGraph 的 RunnableConfig：会话线程 + 登录态 + 注入的上下文。"""
    return {
        "configurable": {
            "thread_id": session_id,
            "session_id": session_id,
            "user_id": user_id,
            "mpsessid": mpsessid,
            "knowledge_context": knowledge_context,
            "understanding_context": understanding_context,
            "policy_context": policy_context,
        }
    }


def _step(index: int, label: str, status: str = "running", ms: "int | None" = None,
          detail: str = "", tool: str = "", args: str = "", more: "dict | None" = None) -> dict:
    """构造一个流式步骤事件（前端渲染成步骤条的一行）。"""
    step: dict = {"i": index, "label": label, "status": status}
    if ms is not None:
        step["ms"] = ms
    if detail:
        step["detail"] = detail
    if tool:
        step["tool"] = tool
    if args:
        step["args"] = args
    if more:
        step.update(more)
    return {"step": step}


def _understand_timed(message: str, model_id: "str | None") -> "dict | None":
    """带计时地跑 understand()，便于在步骤事件里展示耗时。"""
    t0 = time.time()
    und = understand(message, model_id)
    _understand_timed.last_ms = int((time.time() - t0) * 1000)  # type: ignore
    return und


def _from_semantic_router(understanding: "dict | None") -> bool:
    """这份理解是否来自本地语义路由（而非大模型解析）。"""
    return bool((understanding or {}).get("router", {}).get("source") == "semantic_router")


def _domains_of(understanding: "dict | None") -> "list[str]":
    return list((understanding or {}).get("domains") or [])


# ──────────────────────────── ReActAgent 装配 ────────────────────────────
def get_agent(model_id: "str | None" = None, dev: bool = False,
              tool_scope: str = "all", tools: "list | None" = None):
    """构建（并缓存）一个 LangGraph ReAct Agent：LLM + 工具 + 系统提示。

    behavioral：真实实现用 langgraph.prebuilt.create_react_agent(get_llm(...), tools, ...)，
    绑定 prompts.SYSTEM_PROMPT 与会话记忆；此处给出装配点，token 级推理循环交给 langgraph。
    """
    key = (model_id or DEFAULT_MODEL, tool_scope, dev)
    agent = _agents.get(key)
    if agent is None:
        llm = get_llm(model_id, enable_thinking=False)
        bound_tools = tools if tools is not None else _ALL_TOOLS
        agent = _create_react_agent(llm, bound_tools, dev=dev)
        _agents[key] = agent
    return agent


def _create_react_agent(llm, tools, dev: bool = False):
    """返回一个可 .invoke(state, config) 的 ReAct Agent。

    线上真实实现用 langgraph.prebuilt.create_react_agent（token 级循环 + 记忆）。
    但本仓库的工具是「普通函数（首参 config）」，不是 langchain BaseTool，create_react_agent
    不能直接吃；为便于**本地调试**，这里内置一个最小 ReAct 循环 `_MinimalReactAgent`：
    只依赖 langchain-core（无需 langgraph），把工具按签名生成 function schema 绑定给 LLM，
    模型决定调工具 → 本地执行（注入 config/mpsessid）→ 回灌结果 → 直到不再调工具或达上限。
    行为上等价于一轮 ReAct，足够单步看「LLM↔工具」往返；与线上 langgraph 版非字节级一致。
    """
    return _MinimalReactAgent(llm, tools, dev=dev)


# 注解字符串 → JSON schema 类型（粗映射，够工具参数用）
def _json_type(annotation: "object") -> str:
    s = str(annotation).lower()
    if "int" in s:
        return "integer"
    if "float" in s or "number" in s:
        return "number"
    if "bool" in s:
        return "boolean"
    if "dict" in s or "mapping" in s:
        return "object"
    if "list" in s or "tuple" in s or "seq" in s:
        return "array"
    return "string"


def _tool_spec(fn) -> dict:
    """把一个普通工具函数按签名转成 OpenAI function schema（排除 config 参数）。"""
    import inspect
    sig = inspect.signature(fn)
    props, required = {}, []
    for name, p in sig.parameters.items():
        if name == "config" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        props[name] = {"type": _json_type(p.annotation)}
        if p.default is inspect._empty:
            required.append(name)
    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": (inspect.getdoc(fn) or fn.__name__).split("\n")[0][:300],
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


class _MinimalReactAgent:
    """最小 ReAct 循环（仅依赖 langchain-core；用于本地调试，无需 langgraph）。"""

    def __init__(self, llm, tools, dev: bool = False):
        self.llm = llm
        self.dev = dev
        self._tools = {getattr(t, "__name__", repr(t)): t for t in (tools or []) if callable(t)}
        self._specs = []
        for t in self._tools.values():
            try:
                self._specs.append(_tool_spec(t))
            except Exception:
                pass
        try:
            from real_agent.app.config import AGENT_MAX_TOOL_CALLS
            self._max_rounds = AGENT_MAX_TOOL_CALLS or 5
        except Exception:
            self._max_rounds = 5

    def _system(self, config: dict) -> str:
        from real_agent.app.agent.prompts import SYSTEM_PROMPT
        conf = (config or {}).get("configurable", {})
        parts = [SYSTEM_PROMPT]
        for key in ("understanding_context", "knowledge_context", "policy_context"):
            if conf.get(key):
                parts.append(conf[key])
        return "\n\n".join(parts)

    def _call_tool(self, name: str, args: dict, config: dict):
        import inspect
        fn = self._tools.get(name)
        if fn is None:
            return f"[未知工具 {name}]"
        kwargs = dict(args or {})
        if "config" in inspect.signature(fn).parameters:
            kwargs["config"] = config
        try:
            return fn(**kwargs)
        except Exception as e:  # 工具报错回灌给模型，让它自己决定下一步
            return {"error": f"{type(e).__name__}: {e}"}

    def invoke(self, state: dict, config: "dict | None" = None) -> dict:
        from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
        config = config or {}
        user = ""
        for role, content in (state or {}).get("messages", []):
            if role in ("user", "human"):
                user = content
        messages = [SystemMessage(content=self._system(config)), HumanMessage(content=user)]
        bound = self.llm.bind_tools(self._specs) if self._specs else self.llm
        for _ in range(self._max_rounds):
            ai = bound.invoke(messages)
            messages.append(ai)
            calls = getattr(ai, "tool_calls", None) or []
            if not calls:
                break
            for tc in calls:
                result = self._call_tool(tc.get("name"), tc.get("args", {}), config)
                messages.append(ToolMessage(content=str(result), tool_call_id=tc.get("id", "")))
        return {"messages": messages}

    # 简易流式：不做 token 级增量，跑完后把最终文本一次性产出（够本地看链路）
    def stream(self, state, config=None, **kw):
        out = self.invoke(state, config)
        yield out


# ──────────────────────────── 成稿后处理工具 ────────────────────────────
def _is_blank_agent_reply(text: "str | None") -> bool:
    return not (text or "").strip()


def _truncate(text: str, limit: int = 600) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…"


def _local_image_exists(url: str) -> bool:
    """成稿里引用的本地图片是否真实存在（防止吐出坏图链接）。"""
    for prefix, root in _IMG_ROOTS.items():
        if url.startswith(prefix):
            rel = url[len(prefix):].split("?", 1)[0]
            return (root / rel).is_file()
    return True  # 非本地图片（外链）不校验


def _strip_missing_local_images(text: str) -> str:
    """删掉成稿里指向不存在本地图片的 Markdown 图片语法。"""
    import re
    def repl(m):
        return "" if not _local_image_exists(m.group(1)) else m.group(0)
    return re.sub(r"!\[[^\]]*\]\((/[^)]+)\)", repl, text or "")


def _postprocess(answer: str, message: str, domains: "list[str] | None") -> str:
    """成稿统一后处理：净化话术 → 去坏图 → 追加行动卡。"""
    answer = sanitize_customer_reply(answer or "")
    answer = _strip_missing_local_images(answer)
    answer = append_action_cards(answer, message, domains)
    return answer


# ──────────────────────────── 直达快路径 ────────────────────────────
def _deterministic_reply(message: str, mpsessid: "str | None") -> "str | None":
    """确定性直达：按顺序试各 live_* 处理器，命中即返回成稿（不进大模型）。"""
    for handler in (
        answer_live_merchant_request, answer_live_program_request,
        answer_live_member_request, answer_live_activity_request,
        answer_live_point_mall_request, answer_live_operational_request,
        answer_official_app_request if False else None,  # 官方 App 走单独分支
    ):
        if handler is None:
            continue
        try:
            out = handler(message, mpsessid)
        except TypeError:
            out = handler(message)
        if out:
            return out
    return None


def _capability_fast_reply(message: str, session_id: str,
                           mpsessid: "str | None") -> "tuple[str | None, dict]":
    """能力快路径：理解高置信直达时，由 registry 取数 + renderer 渲染成稿。

    返回 (成稿或 None, 调试信息)。behavioral：细节取决于 understand/registry 的直达判定。
    """
    und = understand(message)
    if not (und and should_route_direct(und) and _from_semantic_router(und)):
        return None, {"reason": "not_direct"}
    intents = [t.get("type") for t in (und.get("tasks") or []) if t.get("type")]
    if not intents:
        return None, {"reason": "no_intent"}
    registry = get_registry()
    results = registry.execute_many(intents, {"mpsessid": mpsessid, "message": message})
    parts = [r.answer for r in results if getattr(r, "answer", None)]
    if not parts:
        return None, {"reason": "no_answer"}
    return "\n\n".join(parts), {"intents": intents}


# ──────────────────────────── 入口：一问一答 ────────────────────────────
def chat(message: str, session_id: str = "default", model_id: "str | None" = None,
         user_id: "str | None" = None, mpsessid: "str | None" = None,
         dev: bool = True) -> str:
    """非流式问答。返回最终成稿字符串。顺序见模块 docstring。"""
    t0 = time.time()
    answer = ""
    reasoning = ""
    try:
        # 1) 活动列表直达
        quick = answer_live_program_request(message, mpsessid)
        if quick:
            answer = quick
            return answer

        # 2) 理解
        understanding = _understand_timed(message, model_id)
        domains = _domains_of(understanding)

        # 3) 高置信语义直达（命中则能力层出稿，不进大模型）
        if _from_semantic_router(understanding):
            fast, _dbg = _capability_fast_reply(message, session_id, mpsessid)
            if fast:
                answer = _postprocess(fast, message, domains)
                return answer

        # 4) 组装上下文
        knowledge_ctx = build_static_knowledge_context(message)
        understanding_ctx = build_understanding_context(understanding)
        policy_ctx = build_policy_context(domains)

        # 5) 裁剪工具
        tools, scope = _scoped_tools(domains)

        # 6) ReActAgent 跑一轮
        agent = get_agent(model_id, dev=dev, tool_scope=scope, tools=tools)
        config = _run_config(session_id, user_id, mpsessid,
                             knowledge_ctx, understanding_ctx, policy_ctx)
        result = _run_agent_sync(agent, message, config)
        answer = result.get("answer") or ""
        reasoning = result.get("reasoning", "")

        if _is_blank_agent_reply(answer) or is_soft_unknown(answer):
            answer = exception_reply("unknown")

        # 7) 后处理
        answer = _postprocess(answer, message, domains)
        return answer
    except Exception as exc:
        if is_retriable_key_error(exc) and rotate_deepseek_key():
            logger.warning("retry chat after key rotation")
            return chat(message, session_id, model_id, user_id, mpsessid, dev)
        logger.warning("chat failed", exc_info=True)
        answer = exception_reply("unknown")
        return answer
    finally:
        # 8) 落库
        try:
            log_qa(ip=None, session_id=session_id, model=model_id, dev=dev,
                   question=message, answer=answer, reasoning=reasoning,
                   elapsed_ms=int((time.time() - t0) * 1000))
        except Exception:
            logger.warning("log_qa failed", exc_info=True)


def _run_agent_sync(agent, message: str, config: dict) -> dict:
    """behavioral：调 ReActAgent.invoke，取出最终 AI 消息文本与思维轨迹。"""
    state = {"messages": [("user", message)]}
    out = agent.invoke(state, config)
    msgs = (out or {}).get("messages", [])
    final = msgs[-1] if msgs else None
    text = getattr(final, "content", "") if final is not None else ""
    return {"answer": text, "reasoning": ""}


# ──────────────────────────── 入口：流式 ────────────────────────────
def chat_stream(message: str, session_id: str = "default", model_id: "str | None" = None,
                user_id: "str | None" = None, mpsessid: "str | None" = None,
                dev: bool = True, dev_show_think: bool = False,
                dev_show_raw_think: bool = False):
    """流式问答（SSE 生成器）。逐步 yield 步骤事件 + 增量文本。顺序见模块 docstring。"""
    # 1) 直达拦截（商户、活动）
    for handler in (answer_live_merchant_request, answer_live_program_request):
        quick = handler(message, mpsessid)
        if quick:
            yield _sse({"type": "final", "reply": quick})
            return

    # 2) 步骤：识别用户意图
    t0 = time.time()
    yield _sse(_step(1, "识别用户意图", status="running"))
    understanding = _understand_timed(message, model_id)
    domains = _domains_of(understanding)
    yield _sse(_step(1, "识别用户意图", status="done",
                     ms=getattr(_understand_timed, "last_ms", 0),
                     detail=understanding_detail(understanding)))

    # 3) 步骤：查找可调用工具 + 裁剪
    tools, scope = _scoped_tools(domains)
    yield _sse(_step(2, "查找可调用工具", status="running", detail=scope))

    # 4) ReActAgent 流式运行：每次工具调用 / 生成增量都转成事件
    knowledge_ctx = build_static_knowledge_context(message)
    understanding_ctx = build_understanding_context(understanding)
    policy_ctx = build_policy_context(domains)
    agent = get_agent(model_id, dev=dev, tool_scope=scope, tools=tools)
    config = _run_config(session_id, user_id, mpsessid,
                         knowledge_ctx, understanding_ctx, policy_ctx)

    answer = ""
    try:
        for ev in _run_agent_stream(agent, message, config,
                                    show_think=dev_show_think, show_raw_think=dev_show_raw_think):
            if ev.get("type") == "token":
                answer += ev.get("text", "")
            yield _sse(ev)
    except Exception:
        logger.warning("chat_stream failed", exc_info=True)
        yield _sse({"type": "final", "reply": exception_reply("unknown")})
        return

    # 5) 步骤：生成智能建议 + 最终成稿
    yield _sse(_step(3, "生成智能建议", status="done",
                     ms=int((time.time() - t0) * 1000)))
    answer = _postprocess(answer, message, domains)
    yield _sse({"type": "final", "reply": answer})
    try:
        log_qa(ip=None, session_id=session_id, model=model_id, dev=dev,
               question=message, answer=answer,
               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception:
        logger.warning("log_qa failed", exc_info=True)


def _run_agent_stream(agent, message: str, config: dict, *,
                      show_think: bool = False, show_raw_think: bool = False):
    """behavioral：把 ReActAgent.stream 的每一步（工具调用 / token）转成前端事件。"""
    state = {"messages": [("user", message)]}
    idx = 2
    for chunk in agent.stream(state, config, stream_mode="updates"):
        # 工具调用步骤
        for node, payload in (chunk or {}).items():
            tool_calls = _extract_tool_calls(payload)
            for tc in tool_calls:
                name = tc.get("name", "")
                yield _step(idx, tool_label(name), status="done",
                            tool=name, args=format_args(json.dumps(tc.get("args", {}), ensure_ascii=False)),
                            detail=tool_detail(name))["step"] | {"type": "step"}
            text = _extract_text(payload)
            if text:
                yield {"type": "token", "text": text}


def _extract_tool_calls(payload):
    msgs = (payload or {}).get("messages", []) if isinstance(payload, dict) else []
    calls = []
    for m in msgs:
        for tc in getattr(m, "tool_calls", None) or []:
            calls.append(tc)
    return calls


def _extract_text(payload):
    msgs = (payload or {}).get("messages", []) if isinstance(payload, dict) else []
    for m in reversed(msgs):
        c = getattr(m, "content", None)
        if isinstance(c, str) and c.strip():
            return c
    return ""


# ──────────────────────────── 上下文构造（委托 / 占位）────────────────────────────
def build_understanding_context(understanding: "dict | None") -> "str | None":
    """把理解结果压成一段提示词上下文，注入系统消息，帮助大模型聚焦。"""
    if not understanding:
        return None
    goal = understanding.get("goal") or ""
    domains = "、".join(understanding.get("domains") or [])
    return f"[用户目标] {goal}\n[涉及领域] {domains}" if (goal or domains) else None


def _sse(event: dict) -> str:
    """SSE data 帧编码。"""
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
