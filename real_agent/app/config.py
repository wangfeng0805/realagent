"""运行配置：集中加载 real_agent 的 REAL_ 前缀环境变量（新版 / real_agent）。

真实数据 Agent 使用独立的 REAL_ 前缀，不读取根目录 Demo 的 .env。
所有密钥、登录态、模型服务信息均从 real_agent/.env 读取，默认值见下。

说明：本文件由编译产物（.so）重建，常量名、默认值、环境变量名与原实现一致；
env 解析辅助函数按行为重写。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # .../real_agent

# 只加载 real_agent 自己的 .env，避免和原 Demo 混用。
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


# ---------- 路径 ----------
DATA_DIR = Path(_env("REAL_DATA_DIR", str(BASE_DIR / "data")))
DOCS_DIR = Path(_env("REAL_DOCS_DIR", str(DATA_DIR / "docs")))
MALL_DB_PATH = Path(_env("REAL_MALL_SQLITE_PATH", str(DATA_DIR / "mall.sqlite")))
CONVERSATIONS_DB_PATH = Path(
    _env("REAL_CONVERSATIONS_SQLITE_PATH", str(DATA_DIR / "conversations.sqlite"))
)
QA_LOG_DB_PATH = Path(_env("REAL_QA_LOGS_SQLITE_PATH", str(DATA_DIR / "qa_logs.sqlite")))
MILVUS_PATH = Path(_env("REAL_MILVUS_PATH", str(DATA_DIR / "milvus.db")))
MILVUS_COLLECTION = _env("REAL_MILVUS_COLLECTION", "park_docs")
MILVUS_FP_FILE = Path(_env("REAL_MILVUS_FP_FILE", str(DATA_DIR / ".milvus_fp")))

# ── 新版新增：数据目录重组（images 移入 data/rag/），会话/工具/遗留 mock 子目录 ──
SESSION_DIR = Path(_env("REAL_SESSION_DIR", str(DATA_DIR / "session")))
TOOLS_DIR = Path(_env("REAL_TOOLS_DIR", str(DATA_DIR / "tools")))
RAG_DIR = Path(_env("REAL_RAG_DIR", str(DATA_DIR / "rag")))
LEGACY_MOCK_DIR = Path(_env("REAL_LEGACY_MOCK_DIR", str(DATA_DIR / "legacy_mock")))
KNOWLEDGE_IMAGE_DIR = Path(_env("REAL_KNOWLEDGE_IMAGE_DIR", str(RAG_DIR / "images")))
APP_IMAGE_DIR = Path(_env("REAL_APP_IMAGE_DIR", str(RAG_DIR / "app_images")))
APP_ID = _env("REAL_APP_ID", "wxd275b0214ea13dc8")

_tok = "HUGGINGFACE_TOKEN"
# 本地 embedding 允许离线；若环境提供 HF token 则透传。
if os.getenv(_tok):
    os.environ.setdefault("HF_TOKEN", os.environ[_tok])

# ---------- 对话模型（OpenAI 兼容） ----------
OPENAI_API_KEY = _env("REAL_OPENAI_API_KEY", "")
OPENAI_BASE_URL = _env("REAL_OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = _env("REAL_OPENAI_MODEL", "kimi-k2.6")
OPENAI_TEMPERATURE = _env_float("REAL_OPENAI_TEMPERATURE", 1.0)
OPENAI_TIMEOUT = _env_float("REAL_OPENAI_TIMEOUT", 60.0)
UNDERSTANDING_TIMEOUT = _env_float("REAL_UNDERSTANDING_TIMEOUT", 6.0)
OPENAI_MAX_RETRIES = _env_int("REAL_OPENAI_MAX_RETRIES", 1)
AGENT_MAX_TOOL_CALLS = _env_int("REAL_AGENT_MAX_TOOL_CALLS", 5)
AGENT_RECURSION_LIMIT = _env_int("REAL_AGENT_RECURSION_LIMIT", 13)
LLM_FIRST_PARKING_MEMBER = _env_bool("REAL_LLM_FIRST_PARKING_MEMBER", True)
UNDERSTANDING_MODEL = _env("REAL_UNDERSTANDING_MODEL", "")
SYNTHESIS_MODEL = _env("REAL_SYNTHESIS_MODEL", "")
SYNTHESIS_TIMEOUT = _env_float("REAL_SYNTHESIS_TIMEOUT", 20.0)
SYNTHESIS_TEMPERATURE = _env_float("REAL_SYNTHESIS_TEMPERATURE", 0.3)

# ---------- 功能开关 ----------
ENABLE_PLANNER = _env_bool("REAL_ENABLE_PLANNER", True)
ENABLE_SEMANTIC_ROUTER = _env_bool("REAL_ENABLE_SEMANTIC_ROUTER", True)
ENABLE_ABILITY_ROUTER = _env_bool("REAL_ENABLE_ABILITY_ROUTER", True)
ENABLE_CAPABILITY_REGISTRY = _env_bool("REAL_ENABLE_CAPABILITY_REGISTRY", True)
ENABLE_DIRECT_RESPONSE = _env_bool("REAL_ENABLE_DIRECT_RESPONSE", True)
ENABLE_PARALLEL_SKILLS = _env_bool("REAL_ENABLE_PARALLEL_SKILLS", True)
ENABLE_DYNAMIC_TOOL_SCOPE = _env_bool("REAL_ENABLE_DYNAMIC_TOOL_SCOPE", True)
USE_REAL_API = _env_bool("REAL_USE_REAL_API", True)

SEMANTIC_ROUTER_HIGH = _env_float("REAL_SEMANTIC_ROUTER_HIGH", 0.82)
SEMANTIC_ROUTER_MEDIUM = _env_float("REAL_SEMANTIC_ROUTER_MEDIUM", 0.65)
SEMANTIC_ROUTER_MARGIN = _env_float("REAL_SEMANTIC_ROUTER_MARGIN", 0.08)

DISABLE_THINKING = _env_bool("REAL_DISABLE_THINKING", True)
OPENAI_REASONING_EFFORT = _env("REAL_OPENAI_REASONING_EFFORT", "")
DEFAULT_USER_ID = _env("REAL_DEFAULT_USER_ID", "")
AGENT_NAME = _env("REAL_AGENT_NAME", "小梦")

# ---------- 地图 ----------
AMAP_JS_KEY = _env("REAL_AMAP_JS_KEY", "")
AMAP_SECURITY_JS_CODE = _env("REAL_AMAP_SECURITY_JS_CODE", "")
AMAP_WEB_SERVICE_KEY = _env("REAL_AMAP_WEB_SERVICE_KEY", _env("REAL_AMAP_KEY", ""))
TENCENT_MAP_KEY = _env("REAL_TENCENT_MAP_KEY", "")

# ---------- 小程序会员接口 ----------
MEMBER_INFO_URL = _env(
    "REAL_MEMBER_INFO_URL",
    "https://anticket.lengliwh.com/thvendor/member/info/getMemberInfo.xhtml",
)
MEMBER_KSCLIENT = _env("REAL_MEMBER_KSCLIENT", "DZ97916675")
MEMBER_KSVERSION = _env("REAL_MEMBER_KSVERSION", "66314b202608031502")
MEMBER_CMPAPPKEY = _env("REAL_MEMBER_CMPAPPKEY", "xamzx1")
MEMBER_KSMPID = _env("REAL_MEMBER_KSMPID", "wbDreamwxd275b0214ea13dc8")
MEMBER_MPSESSID = _env("REAL_MEMBER_MPSESSID", "")
MEMBER_API_TIMEOUT = _env_float("REAL_MEMBER_API_TIMEOUT", 15.0)
MEMBER_CACHE_SECONDS = _env_int("REAL_MEMBER_CACHE_SECONDS", 30)
MEMBER_USER_AGENT = _env(
    "REAL_MEMBER_USER_AGENT",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1 "
    "wechatdevtools/2.02.2607161 MicroMessenger/8.0.5 Language/zh_CN webview/",
)
MEMBER_REFERER = _env(
    "REAL_MEMBER_REFERER",
    "https://servicewechat.com/undefined/devtools/page-frame.html",
)

# ---------- 活动接口 ----------
ACTIVITY_LIST_URL = _env(
    "REAL_ACTIVITY_LIST_URL",
    "https://anticket.lengliwh.com/thvendor/ad/getNewAdList.xhtml",
)
ACTIVITY_KSMPID = _env("REAL_ACTIVITY_KSMPID", "wbDreamwxd275b0214ea13dc8")
ACTIVITY_ADFLAGS = _env("REAL_ACTIVITY_ADFLAGS", "exhibit,eventFlash_mob,accommodation")
ACTIVITY_CACHE_SECONDS = _env_int("REAL_ACTIVITY_CACHE_SECONDS", 60)

# ---------- 积分商城接口 ----------
POINT_MALL_URL = _env(
    "REAL_POINT_MALL_URL",
    "https://anticket.lengliwh.com/thvendor/mall/getPointProducts.xhtml",
)
POINT_MALL_APP_ID = _env("REAL_POINT_MALL_APP_ID", "wxd275b0214ea13dc8")
POINT_MALL_KSMPID = _env("REAL_POINT_MALL_KSMPID", "wbDreamwxd275b0214ea13dc8")
POINT_MALL_CACHE_SECONDS = _env_int("REAL_POINT_MALL_CACHE_SECONDS", 30)

# ---------- 小程序通用接口 ----------
MINIPROGRAM_API_BASE_URL = _env(
    "REAL_MINIPROGRAM_API_BASE_URL", "https://anticket.lengliwh.com/thvendor"
)
MINIPROGRAM_KSMPID = _env("REAL_MINIPROGRAM_KSMPID", "wbDreamwxd275b0214ea13dc8")

# ---------- DeepSeek 多 key 轮换 ----------
_deepseek_keys_env = _env("REAL_DEEPSEEK_API_KEYS", "")
_deepseek_single = _env("REAL_DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEYS = [k.strip() for k in _deepseek_keys_env.split(",") if k.strip()]
if _deepseek_single and _deepseek_single not in DEEPSEEK_API_KEYS:
    DEEPSEEK_API_KEYS.insert(0, _deepseek_single)
DEEPSEEK_API_KEY = DEEPSEEK_API_KEYS[0] if DEEPSEEK_API_KEYS else ""

# ---------- 模型注册表 ----------
# ---------- 本地 Ollama（仅用于本地调试；OpenAI 兼容端点）----------
OLLAMA_BASE_URL = _env("REAL_OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = _env("REAL_OLLAMA_MODEL", "qwen3:8b")

MODELS = {
    "kimi-k3": {
        "label": "Kimi K3",
        "model": "kimi-k3",
        "base_url": OPENAI_BASE_URL,
        "api_key": OPENAI_API_KEY,
        "kind": "kimi-k3",
    },
    "kimi-k2.6": {
        "label": "Kimi K2.6",
        "model": "kimi-k2.6",
        "base_url": OPENAI_BASE_URL,
        "api_key": OPENAI_API_KEY,
        "kind": "kimi-k2",
    },
    "deepseek-v4-pro": {
        "label": "DeepSeek V4 Pro",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com",
        "api_key": DEEPSEEK_API_KEY,
        "kind": "deepseek",
    },
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "api_key": DEEPSEEK_API_KEY,
        "kind": "deepseek",
    },
    # 本地 Ollama 的 qwen3:8b（仅本地调试用）。kind 用中性值 "ollama"，
    # 这样 _api_key_for 直接用下面的占位 key、也不触发 DeepSeek/Kimi 的 reasoning 请求体。
    "qwen3:8b": {
        "label": "Qwen3 8B (本地 Ollama · 仅调试)",
        "model": OLLAMA_MODEL,
        "base_url": OLLAMA_BASE_URL,
        "api_key": "ollama",          # 任意非空占位，Ollama 不校验
        "kind": "ollama",
    },
}

# 默认模型切到本地 qwen3:8b（仅本地调试）。想用回云端：设环境变量
# REAL_DEFAULT_MODEL=deepseek-v4-flash，或在调用处传 model_id。
_default_model = _env("REAL_DEFAULT_MODEL", "qwen3:8b")
DEFAULT_MODEL = _default_model if _default_model in MODELS else "qwen3:8b"

# ---------- RAG Embedding ----------
EMBED_BACKEND = _env("REAL_EMBED_BACKEND", "local")
EMBED_LOCAL_MODEL = _env("REAL_EMBED_LOCAL_MODEL", "BAAI/bge-small-zh-v1.5")
OPENAI_EMBED_MODEL = _env("REAL_OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBED_API_KEY = _env("REAL_EMBED_API_KEY", OPENAI_API_KEY)
EMBED_BASE_URL = _env("REAL_EMBED_BASE_URL", "https://api.openai.com/v1")
