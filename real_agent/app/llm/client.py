"""大模型客户端工厂（新版 / real_agent）。

统一产出 OpenAI 兼容的 LangChain ChatOpenAI 客户端，按用途分三档：
- get_llm()            主推理/ReAct 用（温度高、可带工具、可选思维链）；
- get_understanding_llm()  意图理解用（低延迟、短超时 6s）；
- get_synthesis_llm()  成稿润色/合并用（低温 0.3、短超时 20s）。

模型清单来自 config.MODELS（DeepSeek V4 Flash/Pro、Kimi K3/K2.6），base_url / api_key / kind 各异。
DeepSeek 侧支持多把 api_key 轮换（current/rotate/invalidate），遇到额度或鉴权类可重试错误时
自动切下一把 key 并重建客户端。

重建说明：本文件由新版编译产物（llm/client.*.so）重建，面向「读懂装配」。
- 常量（超时/温度/重试/禁思维链开关/三档模型名）与函数签名从 .so 还原；
- key 轮换与客户端缓存逻辑按调用轨迹重写；
- ReasoningChatOpenAI 为 langchain_openai.ChatOpenAI 的轻量子类（附带「推理模型」适配：
  reasoning_effort、思维链开关），其底层网络/流式由 langchain 负责，此处只做装配。
"""

import logging
from typing import Any

try:
    from langchain_openai import ChatOpenAI
except Exception:  # 离线/未装依赖时占位，便于阅读与静态检查
    class ChatOpenAI:  # type: ignore
        def __init__(self, *a, **k): ...

from real_agent.app.config import MODELS, DEFAULT_MODEL

logger = logging.getLogger("real_agent.app.llm.client")

# ──────────────────────────── 常量（字节级还原）────────────────────────────
DISABLE_THINKING = True            # 全局默认关思维链（除非显式 enable_thinking）
OPENAI_MAX_RETRIES = 1
OPENAI_REASONING_EFFORT = ""       # 空=不传 reasoning_effort
OPENAI_TEMPERATURE = 1.0
OPENAI_TIMEOUT = 60.0              # 主推理超时
UNDERSTANDING_MODEL = ""           # 空=沿用 DEFAULT_MODEL
UNDERSTANDING_TIMEOUT = 6.0
SYNTHESIS_MODEL = ""
SYNTHESIS_TEMPERATURE = 0.3
SYNTHESIS_TIMEOUT = 20.0

# DeepSeek 多 key 轮换（运行期由环境注入；缺省为空）
DEEPSEEK_API_KEYS: "list[str]" = []
_deepseek_keys: "list[str]" = list(DEEPSEEK_API_KEYS)
_deepseek_idx = 0

# 客户端缓存：按 (model_id, 档位) 复用，key 变更时失效
_cache: "dict[Any, ChatOpenAI]" = {}
_understanding_cache: "dict[Any, ChatOpenAI]" = {}
_synthesis_cache: "dict[Any, ChatOpenAI]" = {}


# ──────────────────────────── key 轮换 ────────────────────────────
def current_deepseek_key() -> str:
    """当前使用的 DeepSeek key（无则空串）。"""
    if not _deepseek_keys:
        return ""
    return _deepseek_keys[_deepseek_idx % len(_deepseek_keys)]


def rotate_deepseek_key() -> bool:
    """切到下一把 DeepSeek key 并失效旧客户端缓存；无可切换时返回 False。"""
    global _deepseek_idx
    if len(_deepseek_keys) <= 1:
        return False
    _deepseek_idx = (_deepseek_idx + 1) % len(_deepseek_keys)
    _invalidate_deepseek_clients()
    logger.warning("rotated deepseek api key -> idx %d", _deepseek_idx)
    return True


def _invalidate_deepseek_clients() -> None:
    """清掉所有缓存的 DeepSeek 客户端（下次 get_* 时按新 key 重建）。"""
    for cache in (_cache, _understanding_cache, _synthesis_cache):
        for k in [k for k, v in cache.items() if _is_deepseek(k)]:
            cache.pop(k, None)


def _is_deepseek(cache_key: Any) -> bool:
    mid = cache_key[0] if isinstance(cache_key, tuple) else cache_key
    return (MODELS.get(mid or DEFAULT_MODEL) or {}).get("kind", "").startswith("deepseek")


def is_retriable_key_error(exc: BaseException) -> bool:
    """判断异常是否属于「换把 key 重试能解决」的类型（额度/鉴权/限流）。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    hints = ("401", "403", "429", "quota", "insufficient", "rate limit",
             "invalid api key", "unauthorized", "payment")
    return any(h in text for h in hints)


# ──────────────────────────── 装配 ────────────────────────────
def _api_key_for(cfg: dict) -> str:
    """取该模型配置应使用的 api_key：DeepSeek 用轮换 key，否则用配置里的 key。"""
    if cfg.get("kind", "").startswith("deepseek"):
        return current_deepseek_key() or cfg.get("api_key", "")
    return cfg.get("api_key", "")


def _resolve(model_id: "str | None") -> dict:
    return MODELS.get(model_id or DEFAULT_MODEL) or MODELS[DEFAULT_MODEL]


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI 的「推理模型」子类。

    真实 .so 里用 enable_thinking / reasoning_effort 覆写请求体以适配 DeepSeek/Kimi 的
    reasoning 字段；本地调试（含 Ollama/qwen3）不需要这套定制，这里把两个参数从 kwargs 里
    吃掉、其余原样透传给 ChatOpenAI 即可。

    注意：必须先 super().__init__() 再设实例属性——ChatOpenAI 是 Pydantic 模型，
    在 __init__ 完成前赋私有属性会触发 `__pydantic_private__` 未初始化错误（这正是之前
    第 6 步 ReAct 崩掉的原因）。这里干脆不存这两个占位属性，彻底规避。
    """

    def __init__(self, *args, enable_thinking: bool = False,
                 reasoning_effort: str = "", **kwargs):
        super().__init__(*args, **kwargs)


def _build(model_id: "str | None", *, temperature: float, timeout: float,
           enable_thinking: bool) -> ChatOpenAI:
    cfg = _resolve(model_id)
    return ReasoningChatOpenAI(
        model=cfg.get("model", DEFAULT_MODEL),
        base_url=cfg.get("base_url") or None,
        api_key=_api_key_for(cfg) or "EMPTY",
        temperature=temperature,
        timeout=timeout,
        max_retries=OPENAI_MAX_RETRIES,
        enable_thinking=enable_thinking,
        reasoning_effort=OPENAI_REASONING_EFFORT,
    )


def get_llm(model_id: "str | None" = None, enable_thinking: bool = False) -> ChatOpenAI:
    """主推理/ReAct 客户端（带工具调用、温度 1.0、超时 60s）。"""
    key = (model_id or DEFAULT_MODEL, "main", enable_thinking, current_deepseek_key())
    client = _cache.get(key)
    if client is None:
        client = _build(model_id, temperature=OPENAI_TEMPERATURE,
                        timeout=OPENAI_TIMEOUT, enable_thinking=enable_thinking)
        _cache[key] = client
    return client


def get_understanding_llm(model_id: "str | None" = None) -> ChatOpenAI:
    """意图理解客户端（短超时 6s，不带思维链）。"""
    mid = UNDERSTANDING_MODEL or model_id or DEFAULT_MODEL
    key = (mid, "understanding", current_deepseek_key())
    client = _understanding_cache.get(key)
    if client is None:
        client = _build(mid, temperature=OPENAI_TEMPERATURE,
                        timeout=UNDERSTANDING_TIMEOUT, enable_thinking=False)
        _understanding_cache[key] = client
    return client


def get_synthesis_llm(model_id: "str | None" = None) -> ChatOpenAI:
    """成稿润色/合并客户端（低温 0.3，短超时 20s）。"""
    mid = SYNTHESIS_MODEL or model_id or DEFAULT_MODEL
    key = (mid, "synthesis", current_deepseek_key())
    client = _synthesis_cache.get(key)
    if client is None:
        client = _build(mid, temperature=SYNTHESIS_TEMPERATURE,
                        timeout=SYNTHESIS_TIMEOUT, enable_thinking=False)
        _synthesis_cache[key] = client
    return client
