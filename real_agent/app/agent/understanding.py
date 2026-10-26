"""查询语义解析层（Query Understanding）。

在路由/工具选择之前，用一次低温 LLM 调用把用户的自然语言解析成结构化理解：
目标、候选意图（多标签+置信度）、领域、实体、歧义程度、缺失槽位、检索策略。

用途（见 graph.py 集成）：
1. 门控确定性直达路由：只有「单一高置信意图 + 低歧义 + 无需澄清」才允许直达，
   避免模糊/跨域问题被关键词链抢答成单一意图。
2. 为 Agent 注入理解结果：模糊/跨域问题改为「多领域并行检索后综合」，而不是
   查一个工具没结果就回答“不知道”。

解析失败时返回 None，上层回退到原有行为（尝试直达 + Agent），保证鲁棒性。

说明：本文件由编译产物重建。_SYSTEM 与各文案字节级还原；5 个纯函数
（_parse_json / _task_count / _top_confidence / should_route_direct /
build_understanding_context）已与原实现对拍一致；understand() 的 LLM/缓存
主体按调用轨迹重写。
"""

import json
import re
from collections import OrderedDict

# langchain_core 仅在「本地路由没命中、回退大模型解析」时才用到，
# 故改为惰性 import（见 understand 内），让本地路由/确定性路径无需安装 langchain 即可运行。

from real_agent.app.config import ENABLE_SEMANTIC_ROUTER
from real_agent.app.llm.client import get_understanding_llm
from real_agent.app.router.semantic_router import route_to_understanding

_CACHE: "OrderedDict" = OrderedDict()
_CACHE_MAX = 512

DOMAINS = ('parking', 'member', 'member.profile', 'member.points', 'member.coupon', 'ticketing', 'ticketing.catalog', 'ticketing.order', 'ticketing.invoice', 'reservation', 'shopping', 'shopping.catalog', 'shopping.order', 'shopping.address', 'merchant_venue', 'content_common', 'knowledge', 'transport', 'navigation', 'recommendation', 'other')

_SYSTEM = '你是西岸梦中心智能客服的「查询语义解析器」。只输出 JSON，不要任何解释或多余文字。\n把用户这一句话解析为结构化理解，严格使用如下 schema：\n{\n  "goal": "用一句话概括用户真实目标",\n  "tasks": [{"type": "<子问题类型>", "subject": "you|user|null"}],  // 拆出所有独立子问题，见下\n  "intents": [{"intent": "<领域名>", "confidence": 0.0}],  // 按置信度降序，可多个\n  "domains": ["<领域名>"],            // 需要检索的领域，可多个\n  "entities": {"audience": null, "category": null, "location": null, "time": null, "budget": null, "name": null},\n  "ambiguity": "low|medium|high",     // 表达是否模糊/多解\n  "need_clarification": false,        // 是否必须向用户追问才能作答\n  "missing_slots": [],                // 缺失且无法从上下文/搜索补全的关键信息\n  "search_strategy": "deterministic|single_tool|cross_domain|clarify"\n}\n领域名只能取：parking, member, member.profile, member.points, member.coupon, ticketing, ticketing.catalog, ticketing.order, ticketing.invoice, reservation, shopping, shopping.catalog, shopping.order, shopping.address, merchant_venue, content_common, knowledge, transport, navigation, recommendation, other。\n- member/ticketing/shopping 为重域：能判断更细意图时，优先给对应子域（如 member.points、ticketing.catalog、shopping.address），判不准再给父域。\n- 活动/演出/展览/演唱会/话剧/音乐会/剧目/节目/项目/活动日历/排期/场次，以及「有哪些活动」「最近有什么演出」「今天有什么活动」「有哪些活动分类」等，一律归 ticketing.catalog（票务目录）；没有单独的 activity/event 域，不要臆造枚举外的领域名，也不要错放到 content_common/recommendation。\n任务拆分（tasks）原则：\n- 一句话包含多个独立问题时，必须逐个拆进 tasks（如“我有多少积分，我是谁”拆成两个 task），不得只保留第一个；单一问题则 tasks 只有一项。\n- 区分人称：subject=you 表示问客服本人（“你是谁/你叫什么/你能做什么”）；subject=user 表示问当前登录用户自己（“我是谁/我的账号/我的等级·积分·成长值·有效期”）；与人称无关的问题 subject=null。\n- 注意“你是谁”问客服身份，而“我是谁”问当前用户信息，二者可能同时出现在一句话里，必须分别成为 task。\n判定原则：\n- 明确、单一、参数完整的问题（如“我的积分是多少”“XX店在几楼”“停车场几点关门”）：ambiguity=low，单一 domain，intents 顶置信 >=0.9，search_strategy=deterministic。\n- 模糊或开放（如“有什么好玩的”“适合孩子吗”“怎么更划算”“附近有什么”）：ambiguity=medium/high，domains 给出所有相关领域，search_strategy=cross_domain，need_clarification=false（应先搜索再综合，不要急着追问）。\n- 只有当缺少无法推断、且无法通过搜索补全的关键条件时（如“我的券为什么用不了”缺券信息），才 need_clarification=true、search_strategy=clarify。\n- 缺少可默认补全的参数（如停车费缺时长）不算 need_clarification：先给规则再提示补充。'


def _parse_json(text: str) -> "dict | None":
    """从模型输出里解析 JSON：先去掉 ```json 代码围栏，再直接 loads；
    失败时用正则抽取第一个 {...} 再 loads。全部失败返回 None。"""
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def understand(message: str, model_id: "str | None" = None) -> "dict | None":
    """返回结构化语义理解；任何异常都返回 None 让上层回退到原有行为。

    对相同问题做有界缓存（LRU），避免重复问题反复付一次解析 LLM 往返。
    仅缓存成功结果，失败(None)不缓存，以免瞬时故障被“钉死”。
    开启语义路由时，先用本地高置信路由直接产出理解，命中即返回，省掉 LLM 往返。
    """
    key = (message, model_id or "")
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached

    if ENABLE_SEMANTIC_ROUTER:
        routed = route_to_understanding(message)
        if routed:
            _CACHE[key] = routed
            _CACHE.move_to_end(key)
            if len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
            return routed

    try:
        from langchain_core.messages import HumanMessage, SystemMessage  # 惰性：仅大模型回退分支需要
        llm = get_understanding_llm(model_id)
        resp = llm.invoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=message)]
        )
        data = _parse_json(resp.content)
    except Exception:
        return None

    if not data:
        return None

    # 补齐缺省字段，保证下游取值安全。
    data.setdefault("tasks", [])
    data.setdefault("intents", [])
    data.setdefault("domains", [])
    data.setdefault("entities", {})
    data.setdefault("ambiguity", "low")
    data.setdefault("need_clarification", False)
    data.setdefault("missing_slots", [])

    _CACHE[key] = data
    _CACHE.move_to_end(key)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return data


def _task_count(understanding: "dict | None") -> int:
    if not understanding:
        return 0
    tasks = understanding.get("tasks") or []
    return sum(1 for t in tasks if isinstance(t, dict) and t.get("type"))


def _top_confidence(understanding: "dict") -> float:
    intents = understanding.get("intents") or []
    values = [
        float(it.get("confidence", 0.0))
        for it in intents
        if isinstance(it, dict)
    ]
    return max(values) if values else 0.0


def should_route_direct(understanding: "dict | None") -> bool:
    """是否允许走确定性直达路由。

    解析失败(None)时返回 True：回退到原有「先试直达」行为，保证系统不因解析异常而退化。
    直达路由本身只在能给出确定答案时才返回，否则回退 Agent；因此这里只需拦掉真正
    需要跨「内容领域」规划或高度歧义的问题，不能拦掉「卫生间在哪/去停车场」这类
    facility/parking + navigation 的单任务定位问题（navigation 视为修饰领域，不计入跨域）。
    """
    if not understanding:
        return True
    if _task_count(understanding) >= 2:
        return False
    if understanding.get("need_clarification"):
        return False
    if understanding.get("ambiguity") == "high":
        return False
    if _top_confidence(understanding) < 0.85:
        return False
    content_domains = [
        d for d in (understanding.get("domains") or [])
        if d not in ("navigation", "other")
    ]
    if len(content_domains) >= 2:
        return False
    return True


def build_understanding_context(understanding: "dict | None") -> "str | None":
    """把语义理解转成注入 Agent 的规划指引（不复述给用户）。"""
    if not understanding:
        return None

    goal = understanding.get("goal") or "（未概括）"

    intents = understanding.get("intents") or []
    intent_text = "、".join(
        f"{it.get('intent')}({float(it.get('confidence', 0.0)):.2f})"
        for it in intents
        if isinstance(it, dict) and it.get("intent")
    ) or "未识别"

    domains = understanding.get("domains") or []
    domain_text = "、".join(domains) or "未定"

    tasks = [t for t in (understanding.get("tasks") or []) if isinstance(t, dict) and t.get("type")]
    task_items = []
    for i, t in enumerate(tasks, 1):
        subject = t.get("subject")
        if subject == "user":
            suffix = "（问当前用户）"
        elif subject == "you":
            suffix = "（问客服本人）"
        else:
            suffix = ""
        task_items.append(f"{i}. {t.get('type')}{suffix}")
    task_text = "；".join(task_items)

    lines = [
        "【本轮查询语义理解（仅用于你规划工具调用，禁止复述、禁止提及“解析/理解/系统”）】",
        f"用户目标：{goal}",
        f"候选意图：{intent_text}",
        f"涉及领域：{domain_text}",
    ]
    if tasks:
        lines.append(f"待回答子问题（共 {len(tasks)} 个）：{task_text}")
    if len(tasks) >= 2:
        lines.append(
            f"⚠ 本轮共有 {len(tasks)} 个独立问题，必须全部回答；回答前逐一核对每个子问题是否都已覆盖，"
            "绝不能命中前一个就提前结束。"
        )
    lines.append(f"歧义程度：{understanding.get('ambiguity', 'low')}")
    lines.append("执行要求：")
    lines.append(
        "- 只围绕待回答子问题调用必要工具；不得为了补充背景、推荐更多内容或让答案更完整而扩展新任务。"
    )
    lines.append(
        "- 默认最多调用 3 个工具。每次新工具调用前，先确认它对应哪个仍未回答的子问题；"
        "若已有工具结果或知识片段足够回答该子问题，立即停止继续调用工具。"
    )
    lines.append(
        "- 多领域只表示候选范围，不等于每个领域都必须查。仅当该领域直接对应用户明确问到的子问题时才调用。"
    )
    lines.append(
        "- 结果需与已识别实体约束匹配（如 audience/category/预算）；若某工具结果明显不匹配约束，"
        "最多换一个直接相关工具重试，不要把不相关结果硬塞进答案。"
    )
    lines.append(
        "- 事实型结论（价格、时间、库存、名称、车位等）必须来自工具返回数据；"
        "推荐型结论用“比较适合/可以考虑”等措辞，不得写成确定事实。"
    )
    lines.append(
        "- 仅当关键信息无法从登录上下文或搜索补全时才向用户追问；否则先给出基于搜索的候选答案。"
    )
    return "\n".join(lines)
