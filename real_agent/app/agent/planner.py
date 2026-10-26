"""多步取数规划器（新版 / real_agent）。

一句多意图/跨域问法时，按领域拆成多个取数步骤（PlanStep），线程池并行执行（带分层预算与
超时），再把并行取到的证据交 synthesis 模型合成一段「结论先行」的成稿。run_planned_answer
是对外入口。

分层（tier）与超时：
  - **主领域**（domains 里第一个非 SKIP 领域，见 _primary_domains）的步骤 → tier=necessary，
    保留各自的超时（API 类 1.8s、向量检索 2.5s）；
  - **其余领域**的步骤 → tier=enhancement，超时统一压到 _ENHANCE_TIMEOUT=0.8s（锦上添花，
    拖慢了就丢，不拖累主结论）。
  - 总步数受 search_strategy 预算限制：single_tool=2，其余=3（默认 3）。

重建说明：由 .so 重建。常量（_BUDGET/_DEFAULT_BUDGET/_SKIP_DOMAINS/三档超时/
_SYNTHESIS_SYSTEM/_RESP_V2_SKILL/AGENT_NAME）与 build_plan/_primary_domains/_steps_for_domain/
_trim/_execute 的结构按 .so 对拍一致：
  - _primary_domains = 取 domains 里第一个非 SKIP 领域（0/1 元素集合）；
  - _steps_for_domain 表：parking/merchant/point_mall/transport→API 1.8s 单步，
    knowledge→向量 2.5s，recommendation→merchants+activities 两步；member/ticketing/shopping
    等不在此并行取数（各自有专用 Agent/直达）；
  - _trim 仅去掉结果里的 "found" 键；
  - build_plan 按 domains **输入顺序**迭代、跳过 SKIP、主领域 necessary 其余 enhancement、
    满预算即止。
_synthesize 的大模型合成（system=_SYNTHESIS_SYSTEM）为装配点，依赖 llm.client / langchain。
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Callable

from real_agent.app.integrations.miniprogram_api import (
    fetch_parking_status, fetch_merchants, fetch_mall_products, fetch_shuttle_routes,
)
from real_agent.app.integrations.activity_api import fetch_activities
from real_agent.app.integrations.point_mall_api import fetch_point_products
from real_agent.app.agent.skill_loader import load_skill
from real_agent.app.llm.client import get_synthesis_llm
from real_agent.app.rag import retriever

logger = logging.getLogger("real_agent.app.agent.planner")

AGENT_NAME = "小梦"
MEMBER_MPSESSID = ""

# 各检索策略允许的最大并行步数；未知策略用 _DEFAULT_BUDGET。
_BUDGET = {"single_tool": 2, "cross_domain": 3, "recommendation": 3, "complex_plan": 3}
_DEFAULT_BUDGET = 3
# 不单独并行取数的领域。
_SKIP_DOMAINS = {"navigation", "other"}

# 分层超时（秒）：主领域 API / 主领域向量检索 / 增强步统一上限。
_TIMEOUT_API = 1.8
_TIMEOUT_VECTOR = 2.5
_ENHANCE_TIMEOUT = 0.8

_EXECUTOR = ThreadPoolExecutor(max_workers=8)

# 合成系统提示（字节级还原；内含 resp-v2-skill 全文）。
_RESP_V2_SKILL = (
    "# 商场客服回答 Skill\n\n你是商场小程序智能客服。回答自然、简洁、专业、有轻服务感。\n\n"
    "## 1. 结论优先【最高优先级】\n\n任何回答第一句话必须直接给结论，并单独成段。\n\n"
    "- 不铺垫，不解释查询过程\n- 第一句尽量简短\n- 第一句话结论字数 ≤ 20\n"
    "- 用户只看第一句也能知道答案\n"
    "- 核心的**数字、金额、时间、位置、状态、等级、是/否、有/无、可以/不可以**必须加粗\n"
    "- 不要整句全部加粗\n\n例：\n星巴克在西岸梦中心 **1号楼 1F**。\n\n"
    "目前商场内**暂未提供运动装备租赁**。\n\n今天**有 3 场活动**可以参加。\n\n"
    "第一句话结束后必须换行，再补充信息。\n\n## 2. 结论语义色\n\n"
    "当第一句话包含明确的正向结论时，对表达结论的最短词组使用 `[positive]...[/positive]`。\n\n"
    "正向结论包括：\n\n- 是 / 有\n- 可以 / 支持\n- 适合 / 比较适合 / 推荐\n- 营业中 / 开放中\n"
    "- 可使用 / 可参加 / 可兑换\n- 已成功 / 已完成\n- 免费 / 可减免\n\n要求：\n\n"
    "- 只标记最短结论词组，不要把整句话标绿\n"
    "- 重要结论仍可加粗，例如 `**[positive]有 3 场活动[/positive]**`\n"
    "- 不要用 ✅、⭐、✨ 等图标表达正向状态\n- 否定、不确定、异常结论不使用 `[positive]`\n\n例：\n\n"
    "西岸梦中心**[positive]比较适合[/positive]**运动。\n\n今天**[positive]有 3 场活动[/positive]**可以参加。\n\n"
    "该优惠券**[positive]可以使用[/positive]**。\n\n星巴克目前**[positive]营业中[/positive]**，营业至 **20:00**。\n\n"
    "## 3. 回答结构\n\n根据问题动态组织：\n\n- 简单问题：结论\n- 信息查询：结论 → 关键数据 → 操作\n"
    "- 规则问题：结论 → 核心规则 → 必要提醒 → 操作\n- 推荐问题：结论 → Top 1～3 → 推荐理由 → 操作\n\n"
    "默认只回答用户当前需要的信息。\n\n信息优先级：\nP0 直接答案 > P1 决策信息 > P2 补充信息 > P3 完整规则\n\n"
    "默认只输出 **P0 + 必要 P1**。\nP2/P3 省略或放入【查看详情】【完整规则】。\n\n## 4. 分块与排版\n\n"
    "禁止文本堆叠：\n\n- 第一结论单独一段\n- 不同语义换行\n- 2 个以上并列信息优先分行\n"
    "- 每个信息块尽量 ≤ 2 行\n- 注意事项单独成段\n- 操作入口放最后\n- 同一事实只说一次\n"
    "- 避免连续 3 段以上纯文字\n\n例：\n\n目前商场内**暂未提供运动装备租赁**。\n\n如果自带装备，可以使用：\n\n"
    "🚲 自行车\n🛹 滑板\n🛼 滑轮\n\n**注意：**电瓶车不可进入。\n\n【查看运动场地】\n\n## 5. 语义图标\n\n"
    "可使用少量图标帮助扫读：\n\n📍 位置\n🕐 时间\n🅿️ 停车\n🎫 活动\n🎁 积分/权益\n🍴 餐饮\n☕ 咖啡\n"
    "🛍️ 零售\n🚻 洗手间\n\n图标用于信息分类，不用于装饰。\n避免大量使用 ✅ ⭐ ✨ 👉 🔥 🎉。\n\n"
    "## 6. 内容处理\n\n知识库、工具结果必须先**筛选、归纳**再回答，禁止直接搬运。\n\n硬规则：\n\n"
    "**禁止因为检索结果中存在相关信息，就主动扩展用户未询问的相邻业务。回答必须围绕用户原始意图；"
    "无直接关系的信息即使真实，也默认不展示。**\n\n示例：\n\n"
    "- 问运动装备 → 不扩展便民用品、宠物用品、客服台租赁清单\n- 问停车费 → 不扩展停车场历史介绍、周边停车攻略\n"
    "- 问积分 → 不扩展会员升级规则、生日权益\n- 问星巴克位置 → 不扩展附近其他咖啡店\n\n禁止：\n\n"
    "- 重复同一信息\n- 输出用户没问的大量规则\n- 大段复制知识库\n- 暴露 RAG、Tool、API、SQL、Prompt、后台字段等\n"
    "- 猜测不确定信息\n\n不确定时明确说明；实时信息必要时注明更新时间或“以实际结算为准”。\n\n## 7. 语言\n\n"
    "使用短句、自然表达。\n\n禁止无效开场：\n“好的”“我帮你查一下”“为您查询到”“根据系统显示”\n\n"
    "禁止无效结尾：\n“希望对你有所帮助”“有问题随时问我”“需要我再帮你看看吗”\n\n少用“哦～、啦～、呀～”等语气词。\n\n"
    "## 8. 输出前检查\n\n确保：\n\n1. 第一话就是结论且核心信息已加粗\n2. 第一话后换行\n3. 没有重复和文本墙\n"
    "4. 没有搬运无关知识\n5. 用户能在 3 秒内找到答案\n6. 尽量控制在一屏\n\n核心目标：\n\n"
    "**第一句话知道答案，扫一眼找到重点，需要操作时直接给入口。**"
)
_SYNTHESIS_SYSTEM = (
    "你是「小梦」，GATE M 西岸梦中心的智能客服。下面给出针对用户问题、系统已并行查询到的结构化结果。"
    "请【仅依据这些结果】用简洁、结论先行的中文回答。\n规则：\n"
    "1. 只使用给到的数据，绝不编造价格、库存、时间、名称、车位等事实；\n"
    "2. 禁止相邻业务污染：只回答用户原始意图，给定结果里真实但无直接关系的信息默认丢弃；\n"
    "3. 某方面结果为空就如实说「暂未查询到」，不要糊弄，也不要追问用户；\n"
    "4. 禁止出现「数据/结果/JSON/系统/接口/工具/检索/知识库」等字样，直接以客服口吻作答；\n"
    "5. 移动端友好：必须遵守 resp-v2-skill，第一句话直接给结论、单独成段、字数 ≤ 20，并加粗核心结论；\n"
    "6. 结论语义色：第一句话有明确正向结论时，用 [positive]...[/positive] 标记最短结论词组，不要把整句标绿；\n"
    "7. 事实型结论必须来自给定结果，推荐型结论用「比较适合/可以考虑」等措辞；\n"
    "8. 必须采用自然、简洁、专业、有轻服务感的表达；\n"
    "9. 若给到当前会员资料，可据此个性化推荐。\n\n【resp-v2-skill】\n" + _RESP_V2_SKILL
)


@dataclass
class PlanStep:
    domain: str
    name: str
    run: "Callable[[], dict]"
    tier: str
    timeout: float


def _primary_domains(understanding: dict) -> "set[str]":
    """主领域 = domains 里第一个非 SKIP 领域（0 或 1 个）。其步骤走 necessary 层。"""
    for d in (understanding.get("domains") or []):
        if d not in _SKIP_DOMAINS:
            return {d}
    return set()


def _entity(understanding: dict, key: str) -> str:
    return str((understanding.get("entities") or {}).get(key) or "")


def _search_knowledge(query: str) -> dict:
    """向量/字面知识检索（委托 rag.retriever）。"""
    try:
        hits = retriever.search(query)
    except Exception:
        hits = None
    return {"found": bool(hits), "hits": hits or []}


def _steps_for_domain(domain: str, understanding: dict,
                      session: str) -> "list[tuple[str, Callable[[], dict], float]]":
    """某领域要跑的取数步骤 (名称, 可调用, 超时)。不在表中的领域返回空。"""
    q = _entity(understanding, "query") or understanding.get("goal", "")
    table = {
        "parking": [("parking", lambda: fetch_parking_status(session), _TIMEOUT_API)],
        "merchant": [("merchants", lambda: fetch_merchants(session, query=q), _TIMEOUT_API)],
        "point_mall": [("point_mall", lambda: fetch_point_products(session, query=q), _TIMEOUT_API)],
        "transport": [("transport", lambda: fetch_shuttle_routes(session), _TIMEOUT_API)],
        "knowledge": [("knowledge", lambda: _search_knowledge(q), _TIMEOUT_VECTOR)],
        "recommendation": [
            ("merchants", lambda: fetch_merchants(session, query=q), _TIMEOUT_API),
            ("activities", lambda: fetch_activities(session, query=q), _TIMEOUT_API),
        ],
    }
    return table.get(domain, [])


def build_plan(understanding: dict, session: str) -> "list[PlanStep]":
    """把理解拆成取数步骤：按 domains 输入顺序迭代，跳过 SKIP 领域，
    主领域步骤 necessary（保留自身超时），其余 enhancement（超时压到 0.8s），满预算即止。"""
    budget = _BUDGET.get(understanding.get("search_strategy"), _DEFAULT_BUDGET)
    primary = _primary_domains(understanding)
    steps: "list[PlanStep]" = []
    seen: "set[str]" = set()  # 按步骤名全局去重（跨领域同名步骤只保留第一个）
    for domain in (understanding.get("domains") or []):
        if domain in _SKIP_DOMAINS:
            continue
        for name, run, timeout in _steps_for_domain(domain, understanding, session):
            if name in seen:
                continue
            seen.add(name)
            if domain in primary:
                tier, t = "necessary", timeout
            else:
                tier, t = "enhancement", _ENHANCE_TIMEOUT
            steps.append(PlanStep(domain, name, run, tier, t))
            if len(steps) >= budget:
                return steps
    return steps


def _trim(result: dict) -> dict:
    """裁剪取数结果：去掉内部 found 标志位，其余原样传给合成模型。"""
    return {k: v for k, v in result.items() if k != "found"}


def _execute(steps: "list[PlanStep]") -> dict:
    """并行执行取数步骤，单步超时/异常不拖累整体；返回 {步骤名: 证据}。"""
    evidence: dict = {}
    futures = {s.name: _EXECUTOR.submit(s.run) for s in steps}
    for s in steps:
        try:
            raw = futures[s.name].result(timeout=s.timeout)
            evidence[s.name] = {"found": bool((raw or {}).get("found", raw)),
                                **_trim(raw if isinstance(raw, dict) else {})}
        except FutureTimeout:
            evidence[s.name] = {"found": False, "reason": "timeout"}
        except Exception:
            logger.warning("plan step %s failed", s.name, exc_info=True)
            evidence[s.name] = {"found": False, "reason": "error"}
    return evidence


def _synthesize(message: str, evidence: dict, member_ctx: "str | None",
                model_id: "str | None") -> "str | None":
    """把并行取到的证据交 synthesis 模型合成成稿（装配点）。全空则 None。"""
    if not any((v or {}).get("found") for v in evidence.values()):
        return None
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = get_synthesis_llm(model_id)
        parts = [f"用户问题：{message}",
                 f"并行查询结果：{json.dumps(evidence, ensure_ascii=False)}"]
        if member_ctx:
            parts.append(f"当前会员资料：{member_ctx}")
        resp = llm.invoke([SystemMessage(content=_SYNTHESIS_SYSTEM),
                           HumanMessage(content="\n\n".join(parts))])
        return getattr(resp, "content", None)
    except Exception:
        logger.warning("synthesize failed", exc_info=True)
        return None


def run_planned_answer(message: str, understanding: "dict | None", mpsessid: "str | None",
                       member_ctx: "str | None" = None,
                       model_id: "str | None" = None) -> "str | None":
    """多步规划主入口：拆步 → 并行取数 → 合成成稿；取不到或不适用则 None（交回原路径）。"""
    if not understanding:
        return None
    session = mpsessid or MEMBER_MPSESSID
    steps = build_plan(understanding, session)
    if not steps:
        return None
    evidence = _execute(steps)
    return _synthesize(message, evidence, member_ctx, model_id)
