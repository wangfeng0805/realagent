"""小梦 real_agent · 逐层 debug 驱动。

用法：在 VS Code 里对想看的那一层下断点，然后 F5 选 "调试：debug_driver" 跑本文件。
每个 step_* 块相互独立，可单独注释掉别的、只留一个慢慢单步。

为什么分层跑：整条 chat() 端到端需要「数据文件 + 模型 key + 网络」才有真实结果；
但下面标 ✅ 的几层是纯逻辑，不碰网络/key，是你"读懂逻辑"最该单步的部分。

想从入口一路跑到 api / llm / rag：用 step_chat_pipeline()（把 chat() 的 8 个阶段拆开逐行跑，
每阶段都 show 中间值，注释里标了哪一步会碰 LLM / RAG / tools_catalog 接口），或 step_full_chat()
（真·端到端）。这两个要到达 LLM/API 阶段需要配 key + 网络；前面的阶段纯离线即可单步。
"""
import sys, pathlib, json, time

# 让 import real_agent.* 生效（本文件放在项目根）
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def show(tag, val):
    print(f"\n── {tag} ──")
    if isinstance(val, (dict, list)):
        print(json.dumps(val, ensure_ascii=False, indent=2, default=str))
    else:
        print(repr(val))


# ════════════════════════════ 纯逻辑层（离线可单步）════════════════════════════
def step_L1_router():
    """✅ 纯逻辑 · L1 关键词路由（capabilities/router.py）。断点就下在 deterministic_intents 里。"""
    from real_agent.app.capabilities.router import deterministic_intents
    for q in ["有哪些停车场", "我的积分还有多少", "停车费多少", "你好"]:
        show(f"L1 deterministic_intents({q!r})", deterministic_intents(q))


def step_understand():
    """理解全链：understand → L1+L2 → should_route_direct（understanding.py）。
    本地高置信路由命中即返回，不走 LLM；没命中才走大模型解析（需 key）。"""
    from real_agent.app.agent.understanding import understand, should_route_direct
    for q in ["我的积分还有多少", "停车费多少和积分"]:
        u = understand(q)                 # ← 断点：F11 步入 route_to_understanding → route_query
        show(f"understand({q!r})", u)
        show("should_route_direct", should_route_direct(u))


def step_renderer():
    """✅ 纯逻辑 · 能力渲染（capabilities/renderer.py）。喂假 payload，看它出中文成稿。"""
    from real_agent.app.capabilities.renderer import render
    payload = {"found": True, "member": {"member_level_name": "WeM3", "points": 1200,
               "effective_growth_value": 5000, "membership_end_time": "2026-12-31"}}
    show("render(member.info)", render("member.info", payload))
    show("render(member.points)", render("member.points", payload))


def step_postprocess():
    """✅ 纯逻辑 · 后处理（customer_reply + action_cards + exception_reply）。"""
    from real_agent.app.agent.customer_reply import sanitize_customer_reply
    from real_agent.app.agent.action_cards import append_action_cards
    from real_agent.app.agent.exception_reply import reply_for
    draft = "根据截图可知，停车费是 30 元。"
    show("sanitize_customer_reply", sanitize_customer_reply(draft))
    show("append_action_cards", append_action_cards("停车费 30 元。", "有哪些停车场", ["parking"]))
    show("exception_reply(unclear_intent)", reply_for("unclear_intent"))


def step_api_catalog():
    """✅ 大部分离线 · tools_catalog.json 接口目录（api_gateway + tools/api_registry）。
    这就是 ReAct agent 里 search_apis / call_api 两个工具背后的实现。"""
    from real_agent.app.integrations import api_gateway as G
    from real_agent.app.tools import api_registry as AR
    show("目录条数 _active_catalog()", len(G._active_catalog()))
    show("search_catalog('停车费')", [(h.get("path"), h.get("summary")) for h in G.search_catalog("停车费", k=5)])
    show("is_allowed(.../queryFee.xhtml)", G.is_allowed("/member/parking/sooBin/queryFee.xhtml"))
    show("search_apis('停车') [工具层]", AR.search_apis("停车"))
    # call_api：缺参校验离线即可复现；传齐参数且有网络+mpsessid 才会真正 GET anticket.lengliwh.com
    cfg = {"configurable": {"mpsessid": ""}}
    show("call_api(缺参)", AR.call_api("/member/parking/sooBin/queryFee.xhtml", {}, cfg))


# ════════════════════════════ 入口层：从 chat() 拆开逐阶段 ════════════════════════════
def step_chat_pipeline(message: str = "停车费多少和积分", mpsessid: str = "",
                       session_id: str = "dbg", model_id=None, dev: bool = True):
    """★ 入口 chat() 的 8 个阶段逐行拆开跑（graph.py:chat 的等价展开）。

    在想看的阶段下断点即可。阶段与「会碰到什么」：
      1 活动直达    answer_live_program_request      —— 纯逻辑
      2 理解        _understand_timed                —— L1/L2 命中纯逻辑；否则 **LLM**（理解模型，需 key）
      3 语义直达    _from_semantic_router → _capability_fast_reply
                                                     —— 命中则走 **能力层取数**(member/parking API)+ renderer，不进大模型
      4 组装上下文  build_static_knowledge_context   —— **RAG/静态知识**(static_context 字面检索；向量检索在 retriever)
                   build_understanding_context / build_policy_context —— 纯逻辑
      5 裁剪工具    _scoped_tools                    —— 纯逻辑，决定把哪些工具交给 agent
      6 ReAct 跑   get_agent + _run_agent_sync      —— **LLM 推理循环**；模型在这里决定调
                                                        search_apis/call_api(tools_catalog 接口)、知识/会员/停车工具
      7 后处理      _postprocess                     —— 纯逻辑
      8 落库        log_qa                           —— 写 data/qa_log.db
    """
    import real_agent.app.agent.graph as G

    t0 = time.time()
    answer, reasoning = "", ""

    # 1) 活动列表直达
    quick = G.answer_live_program_request(message, mpsessid)
    show("1) answer_live_program_request", quick)
    if quick:
        show("→ 命中活动直达，直接返回", quick)
        return quick

    # 2) 理解（L1/L2 命中纯逻辑；miss 走理解 LLM）
    understanding = G._understand_timed(message, model_id)      # ← 断点：步入看 understand()
    domains = G._domains_of(understanding)
    show("2) understanding", understanding)
    show("   domains", domains)

    # 3) 高置信语义直达 → 能力层出稿（不进大模型）
    from_sr = G._from_semantic_router(understanding)
    show("3) _from_semantic_router", from_sr)
    if from_sr:
        fast, dbg = G._capability_fast_reply(message, session_id, mpsessid)  # ← 断点：能力取数 + render
        show("   _capability_fast_reply.fast", fast)
        show("   _capability_fast_reply.dbg", dbg)
        if fast:
            answer = G._postprocess(fast, message, domains)
            show("→ 能力直达成稿（已后处理）", answer)
            _safe_log(G, session_id, model_id, dev, message, answer, reasoning, t0)
            return answer

    # 4) 组装上下文（RAG/静态知识 + 理解指引 + 政策）
    knowledge_ctx = G.build_static_knowledge_context(message)  # ← 断点：static_context 字面检索
    understanding_ctx = G.build_understanding_context(understanding)
    policy_ctx = G.build_policy_context(domains)
    show("4) knowledge_ctx (RAG/静态)", knowledge_ctx)
    show("   understanding_ctx", understanding_ctx)
    show("   policy_ctx", policy_ctx)

    # 5) 裁剪工具
    tools, scope = G._scoped_tools(domains)
    show("5) _scoped_tools.scope", scope)
    show("   工具数", len(tools) if tools else 0)

    # 6) ReAct 跑一轮（LLM + tools_catalog 接口 + 知识/会员/停车工具）
    try:
        agent = G.get_agent(model_id, dev=dev, tool_scope=scope, tools=tools)
        config = G._run_config(session_id, None, mpsessid, knowledge_ctx, understanding_ctx, policy_ctx)
        result = G._run_agent_sync(agent, message, config)      # ← 主断点：步入看 agent.invoke 的工具循环
        answer = result.get("answer") or ""
        reasoning = result.get("reasoning", "")
        show("6) _run_agent_sync.answer", answer)
        if G._is_blank_agent_reply(answer) or G.is_soft_unknown(answer):
            answer = G.exception_reply("unknown")
            show("   空/软未知 → 兜底", answer)
    except Exception as exc:
        # 没配 key / 没网络时会在这里抛；前 5 阶段仍然单步得到了真实中间值
        show("6) ReAct 阶段异常（通常是缺 key/网络）", f"{type(exc).__name__}: {exc}")
        answer = G.exception_reply("unknown")

    # 7) 后处理
    answer = G._postprocess(answer, message, domains)
    show("7) _postprocess 最终成稿", answer)

    # 8) 落库
    _safe_log(G, session_id, model_id, dev, message, answer, reasoning, t0)
    return answer


def _safe_log(G, session_id, model_id, dev, message, answer, reasoning, t0):
    try:
        G.log_qa(ip=None, session_id=session_id, model=model_id, dev=dev,
                 question=message, answer=answer, reasoning=reasoning,
                 elapsed_ms=int((time.time() - t0) * 1000))
        show("8) log_qa", "已写入 data/qa_log.db")
    except Exception as e:
        show("8) log_qa 失败", f"{type(e).__name__}: {e}")


def step_full_chat(message: str = "停车费多少和积分", mpsessid: str = ""):
    """真·端到端 chat()（graph.py:chat）。⚠️ 需要 数据文件 + 模型 key + 网络。
    想在阶段之间看中间值、或没配 key 时，优先用 step_chat_pipeline()。"""
    from real_agent.app.agent.graph import chat
    reply = chat(message, session_id="dbg", mpsessid=mpsessid)   # ← 主断点下在 graph.py chat() 开头
    show("chat() reply", reply)


if __name__ == "__main__":
    # —— 纯逻辑层：先从这些开始，离线可单步 ——
    # step_L1_router()        # ✅
    # step_understand()
    # step_renderer()         # ✅
    # step_postprocess()      # ✅
    # step_api_catalog()      # ✅ tools_catalog 接口目录

    # —— 入口层：从 chat() 逐阶段跑到 api/llm/rag ——
    step_chat_pipeline()      # ★ 推荐：阶段拆开、每步 show 中间值
    # step_full_chat()        # 真·端到端（需 key + 网络）
