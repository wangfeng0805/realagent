"""HTTP 入口层：FastAPI 应用 + 路由（Controller）+ 对话服务编排（Service）（新版 / real_agent）。

这是整套系统的「门面」。相当于 Java(Spring) 里的 @RestController + DTO + @Service 三层挤在一个文件：
- Controller：@app.post("/chat") / "/chat/stream" 等路由函数，薄薄一层，只负责
  取参(DTO) → 调服务 → 包壳(DTO) → 落库。
- DTO：ChatRequest（前端 POST 的 JSON body）/ ChatResponse（返回体）。
- Service：chat() / chat_stream()，内部是那条「漏斗」——活动直达拦截 → understand 理解
  (input_normalize + L1/L2 路由 + 门控) → 命中则直达渲染，否则 ReActAgent + 98 工具 → 后处理 → 落库。

真实路由表（本文件 import 时由 FastAPI 装饰器注册）：
    GET  /health                               健康检查
    GET  /config                               前端配置（地图 key / Agent 名）
    GET  /home-data                            首页推荐问（246 条）
    GET  /models                               可选大模型列表
    GET  /activity-images/{path}               活动图片代理
    GET  /mall-images/{path}                   积分商城图片代理
    GET  /navmap                               导航/地图跳转
    POST /chat                                 一问一答（Controller：chat_endpoint）
    POST /chat/stream                          流式问答 SSE（Controller：chat_stream_endpoint）
    GET  /admin                                运营后台页
    (include_router)  /admin/api/*             后台增删改查接口（见 admin.py）
    (mount) /knowledge-images /app-images /    静态资源（图片 + 前端页面）

重建说明：本文件由新版编译产物（main.*.so）重建，面向「读懂入口链路」。
- 路由表（路径 + 方法 + 处理函数名）通过注入假 FastAPI 捕获装饰器参数还原，与 .so 一致；
- 常量（MODELS / DEFAULT_MODEL / AGENT_NAME / 目录 / 地图 key）、DTO 字段、四个元信息接口
  (health/config/models/home-data) 的返回结构、_client_ip 取 IP 规则，均对 .so 验证一致；
- chat() / chat_stream() 的编排顺序（live_program 拦截 → understand → 直达/ReAct → 落库）
  由对 .so 的调用轨迹还原（readable 重写）；ReActAgent 内部 token 级流程在 agent/graph.py +
  llm/client.py，本文件只负责装配与串联。
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from real_agent.app.config import (
    AGENT_NAME,
    DEFAULT_MODEL,
    MODELS,
    TENCENT_MAP_KEY,
    AMAP_JS_KEY,
    AMAP_SECURITY_JS_CODE,
    AMAP_WEB_SERVICE_KEY,
)
from real_agent.app.admin import admin_router
from real_agent.app.agent.exception_reply import exception_reply
# 对话服务（Service）真身在 agent/graph.py，这里原样 re-export，供下方两个 Controller 调用：
from real_agent.app.agent.graph import chat, chat_stream
from real_agent.app.repositories.qa_log import log_qa as _log_qa

logger = logging.getLogger("real_agent.app.main")

UPSTREAM_TIMEOUT = "upstream_timeout"

BASE_DIR = Path(__file__).resolve().parent.parent          # real_agent/
WEB_DIR = BASE_DIR / "web"                                  # 前端静态页面
APP_IMAGE_DIR = BASE_DIR / "data" / "rag" / "app_images"   # 小程序/官方应用截图
KNOWLEDGE_IMAGE_DIR = BASE_DIR / "data" / "rag" / "images"  # 知识库图片

# 首页推荐问（246 条，数据随部署下发）
try:
    HOME_QUESTIONS: "list[str]" = json.loads(
        (BASE_DIR / "data" / "home_questions.json").read_text(encoding="utf-8")
    )
except Exception:
    HOME_QUESTIONS = []


# ──────────────────────────── DTO（请求 / 响应体）────────────────────────────
class ChatRequest(BaseModel):
    """前端 POST /chat(/stream) 的 JSON body。"""
    message: str
    session_id: str = "default"
    model: "str | None" = None
    user_id: "str | None" = None
    mpsessid: "str | None" = None          # 小程序登录态（取会员/停车实时数据用）
    dev: bool = True                       # 开发模式（放开调试信息）
    dev_show_think: bool = False           # 流式：是否吐「思考过程」步骤
    dev_show_raw_think: bool = False       # 流式：是否吐模型原始思维链


class ChatResponse(BaseModel):
    reply: str


# ──────────────────────────── 跨切面小工具 ────────────────────────────
def _client_ip(request: Request) -> str:
    """取客户端真实 IP：优先 X-Forwarded-For 首段，其次 X-Real-IP，最后连接地址。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else ""


def log_qa(ip: "str | None", session_id: "str | None", model: "str | None",
           dev: bool, question: str, answer: str, reasoning: str = "",
           elapsed_ms: "int | None" = None) -> None:
    """问答落库（委托 repositories.qa_log）；失败不影响主流程。"""
    try:
        _log_qa(ip=ip, session_id=session_id, model=model, dev=dev,
                question=question, answer=answer, reasoning=reasoning,
                elapsed_ms=elapsed_ms)
    except Exception:
        logger.warning("log_qa failed", exc_info=True)


def _resolve_model(model_id: "str | None") -> dict:
    """把前端传的 model id 解析成模型配置；缺省/未知回退 DEFAULT_MODEL。"""
    return MODELS.get(model_id or DEFAULT_MODEL) or MODELS[DEFAULT_MODEL]


# ──────────────────────────── 应用 ────────────────────────────
app = FastAPI(title="小梦 · 西岸梦中心智能客服")


# ---- 元信息接口（前端启动时拉取）----
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/config")
def get_config() -> dict:
    """前端配置：地图 key + Agent 名（map_enabled 取决于是否配了地图 key）。"""
    return {
        "map_enabled": bool(TENCENT_MAP_KEY),
        "tencent_map_key": TENCENT_MAP_KEY,
        "amap_js_key": AMAP_JS_KEY,
        "amap_security_js_code": AMAP_SECURITY_JS_CODE,
        "agent_name": AGENT_NAME,
    }


@app.get("/models")
def list_models() -> dict:
    """可选大模型列表（供前端下拉切换）。"""
    return {
        "default": DEFAULT_MODEL,
        "models": [{"id": k, "label": v.get("label", k)} for k, v in MODELS.items()],
    }


@app.get("/home-data")
def get_home_data() -> dict:
    """首页推荐问。"""
    return {"questions": HOME_QUESTIONS}


# ---- 图片 / 地图代理 ----
def _antank_image(image_path: str) -> Response:
    """从知识库图片目录安全读取一张图并返回（防目录穿越）。"""
    rel = (image_path or "").lstrip("/")
    target = (KNOWLEDGE_IMAGE_DIR / rel).resolve()
    if not str(target).startswith(str(KNOWLEDGE_IMAGE_DIR.resolve())) or not target.is_file():
        return Response(status_code=404)
    return FileResponse(str(target))


@app.get("/activity-images/{image_path:path}")
def activity_image(image_path: str) -> Response:
    """活动图片代理（知识库图片目录）。"""
    return _antank_image(image_path)


@app.get("/mall-images/{image_path:path}")
def mall_image(image_path: str) -> Response:
    """积分商城图片代理（应用图片目录）。"""
    rel = (image_path or "").lstrip("/")
    target = (APP_IMAGE_DIR / rel).resolve()
    if not str(target).startswith(str(APP_IMAGE_DIR.resolve())) or not target.is_file():
        return Response(status_code=404)
    return FileResponse(str(target))


@app.get("/navmap")
def navmap(name: str = "", address: str = "", lng: str = "", lat: str = "") -> Response:
    """导航：拼一个腾讯地图标点/路线跳转页并重定向（key 来自配置）。"""
    from urllib.parse import quote
    url = (
        "https://apis.map.qq.com/uri/v1/marker"
        f"?marker=coord:{quote(lat)},{quote(lng)};title:{quote(name)};addr:{quote(address)}"
        f"&referer=xiaomeng&key={quote(TENCENT_MAP_KEY)}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url)


# ──────────────────────────── 对话服务（Service）────────────────────────────
# chat() / chat_stream() 的真身在 agent/graph.py（上方 import 进来），本文件不重复实现。
# 它们内部是那条漏斗：活动/商户直达拦截 → understand 理解 → 高置信能力直达 or ReActAgent(98 工具)
# → 成稿后处理 → 落库。流式版额外逐帧 yield「识别用户意图/查找可调用工具/生成智能建议」步骤事件。


# ──────────────────────────── Controller（路由处理函数）────────────────────────────
@app.post("/chat")
def chat_endpoint(req: ChatRequest, request: Request) -> ChatResponse:
    """一问一答 Controller：取 IP → 调 chat() 服务 → 包成 ChatResponse。

    （落库在 graph.chat() 内部完成，Controller 不重复 log_qa，避免双写。）
    """
    _ = _client_ip(request)   # 真实实现把 IP 透传给服务侧落库
    reply = chat(
        message=req.message, session_id=req.session_id, model_id=req.model,
        user_id=req.user_id, mpsessid=req.mpsessid, dev=req.dev,
    )
    return ChatResponse(reply=reply)


@app.post("/chat/stream")
def chat_stream_endpoint(req: ChatRequest, request: Request) -> StreamingResponse:
    """流式问答 Controller：把 chat_stream() 生成器包成 text/event-stream。"""
    gen = chat_stream(
        message=req.message, session_id=req.session_id, model_id=req.model,
        user_id=req.user_id, mpsessid=req.mpsessid, dev=req.dev,
        dev_show_think=req.dev_show_think, dev_show_raw_think=req.dev_show_raw_think,
    )
    return StreamingResponse(gen, media_type="text/event-stream")


# ---- 运营后台 ----
app.include_router(admin_router)


@app.get("/admin")
def admin_page() -> FileResponse:
    """后台单页。"""
    return FileResponse(str(WEB_DIR / "admin.html"))


# ---- 静态资源挂载（顺序敏感：根目录 "/" 必须最后挂）----
app.mount("/knowledge-images", StaticFiles(directory=str(KNOWLEDGE_IMAGE_DIR)), name="knowledge-images")
app.mount("/app-images", StaticFiles(directory=str(APP_IMAGE_DIR)), name="app-images")
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
