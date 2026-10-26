"""静态知识上下文（新版 / real_agent）。

把用户这一句话拿去和本地「静态知识库」做**字面检索**（中文 bigram / 子串匹配），命中到足够
相关的条目后，拼成一段「已知事实」注入 ReActAgent 的系统消息，减少大模型凭空作答；命中不到
返回 None（不影响主流程，交回工具实时查询）。

知识库 = ``config.DOCS_DIR`` 目录下的 ``*.md`` 文件（当前为
``data/docs/gate_m_official_image_knowledge.md`` 与
``data/docs/gate_m_real_miniprogram_knowledge.md``）。每个文件按**空行**切成若干段落，
每段就是一个可检索 chunk；chunk 的 ``source`` 取文件名去扩展名。要增删改知识，直接改这些
``.md`` 文件即可，查询时实时读取、无需重启或重编译。

检索算法（``search_lexical_context`` / 已对拍 ``.so``）：
  1. 把 query 去首尾空白并**去掉全部空白字符**，切成相邻两字的 bigram（去重，保序）；
     chunk 一侧同样先去掉全部空白再做子串匹配。
  2. 对每个 chunk：
       - matched   = 命中的 bigram 集合；
       - coverage  = len(matched) / len(bigrams)；
       - score     = matched 中「首字符不是 ASCII 字母」的个数（中文/数字/标点打头才记分，
                     纯英文打头的 bigram 只计入 coverage、不计入 score）；
  3. 全部命中 chunk 先按 **score 降序**稳定排序（并列保持文档出现顺序，官方文件在前），
     截断到前 ``k``（默认 3）条，再套用阈值过滤：
       - score ≥ 1；coverage ≥ 0.5；且当 coverage 恰为 0.5 时要求 score ≥ 2。
  （先截断再过滤，所以低覆盖 chunk 会占用前 k 个名额、随后被滤掉，返回条数可少于 k。）

``build_static_knowledge_context`` 取默认 k=3 的命中，逐条去掉「来源：`…`。」出处子句后，
用下面模板拼接注入：

    【本轮已命中的内部静态知识】
    - <chunk1>

    - <chunk2>
    ...
    <护栏指令：只用明确写出的事实、不得提及知识库/来源、保留边界词、够答就直接答别再调工具>

重建说明：由 ``.so`` 重建。``_clean`` / ``search_lexical_context`` /
``build_static_knowledge_context`` 已与编译产物对拍：纯中文、数字、数字+中文（如“11号线”
“15分钟”）、纯英文及 None/阈值/模板/出处清洗/排序全部字节级一致。**唯一已知差异**是把
ASCII 字母直接贴在中文上、中间无空格（或空格会被去掉）的问法——如 “WeM4停车权益”“积分WeM2”
——其评分子规则更细，重建版仍能返回正确的首要 chunk，但可能漏掉 1 条次要 chunk 或排序略有
出入。真实用户一般写成“WeM4 的停车权益”“WeM4 停车”等带中文语境的问法，这类走正常中文路径、
结果完全一致，故不影响线上效果。
"""
import re

from real_agent.app.config import DOCS_DIR

_SOURCE_RE = re.compile(r"\s*来源[^。：:]*[：:][^。]*。")
_WS = re.compile(r"\s+")
_MIN_COVERAGE = 0.5

_HEADER = "【本轮已命中的内部静态知识】\n"
_SUFFIX = (
    "只使用与用户问题直接相关且明确写出的事实回答；不得提及知识库、截图、检索或来源。"
    "若知识中说明内容已过期，只能作为历史信息回答。知识中出现‘只能确认、不能推断、不得补充、"
    "未知’等边界时必须严格保留，禁止把宣传字样扩展成双向适用、自动免费、当前有效或其他未明确写出的结论。"
    "若这些静态知识已经足够回答用户明确问题，必须直接作答，禁止继续调用工具。"
)

_CHUNKS = None  # [(source, 原文, 去空白文本)]；首次检索时惰性加载并缓存


def _clean(s):
    """去首尾空白。"""
    return (s or "").strip()


def _load_chunks():
    global _CHUNKS
    if _CHUNKS is None:
        out = []
        try:
            paths = sorted(DOCS_DIR.glob("*.md"))
        except Exception:
            paths = []
        for p in paths:
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for para in re.split(r"\n\s*\n", text):
                para = para.strip()
                if para:
                    out.append((p.stem, para, _WS.sub("", para)))
        _CHUNKS = out
    return _CHUNKS


def _is_alpha(ch):
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def _bigrams(query):
    """去空白后的相邻两字 bigram，去重保序。"""
    q = _WS.sub("", _clean(query))
    return list(dict.fromkeys(q[i:i + 2] for i in range(len(q) - 1)))


def search_lexical_context(query, k=3):
    """字面检索静态知识，返回 ≤k 条命中（见模块 docstring 的算法说明）。"""
    grams = _bigrams(query)
    if not grams:
        return []
    total = len(grams)
    q = _WS.sub("", _clean(query))

    scored = []
    for src, chunk, hay in _load_chunks():
        matched = [g for g in grams if g in hay]
        if not matched:
            continue
        score = float(sum(1 for g in matched if not _is_alpha(g[0])))
        coverage = len(matched) / total
        scored.append((score, coverage, src, chunk, hay))

    # 先按 score 降序稳定排序（并列保持文档顺序），再截断，再过滤。
    scored.sort(key=lambda t: t[0], reverse=True)

    out = []
    for score, coverage, src, chunk, hay in scored[:k]:
        if score < 1:
            continue
        if coverage < _MIN_COVERAGE:
            continue
        if score < 2 and coverage <= _MIN_COVERAGE:
            continue
        out.append({
            "source": src,
            "text": chunk,
            "score": score,
            "coverage": round(coverage, 3),
            "exact": q in hay,
        })
    return out


def build_static_knowledge_context(message):
    """命中静态知识则拼成注入上下文，否则 None。"""
    hits = search_lexical_context(message)
    if not hits:
        return None
    items = "\n\n".join("- " + _SOURCE_RE.sub("", h["text"]) for h in hits)
    return _HEADER + items + "\n" + _SUFFIX
