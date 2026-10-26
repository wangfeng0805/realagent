"""运营后台接口（新版 / real_agent）。

挂在 /admin/api/* 下，供运营维护文本知识、图片知识、结构化数据、工具/接口目录，查看问答日志
（运营日志），并在测试中心直接跑一条对话。以 admin_router（APIRouter）被 main.py include。

重建说明：由 .so 重建 + 线上(http://47.116.7.1/admin) 接口校正。各接口的**响应结构**对线上
对齐：列表接口统一 `{"items":[...]}`（部分带 `total`），item 字段与线上一致：
  - /docs           items[{name,size,mtime}]
  - /docs/{name}    {name,content}
  - /images         items[{key,dir,name,url,meta}]
  - /data           items[{name,count}]（count = JSON 顶层键/元素个数）
  - /data/{name}    {name,content}（原始 JSON 串）/ 404 {"detail":"数据不存在"}
  - /tools          items[{name,domain,description,args:[{name,type}]}]
  - /apis?q=        items[...]（api_gateway 只读目录检索）
  - /api-detail?path= 详情 / 404 {"detail":"接口不存在或不在只读目录"}
  - /uncataloged    items[{path,method,summary,tag,reason,sources}]
  - /westbund       {items,total,api_md_total}
  - /logs?q=&ip=&limit= {items[{id,ts,ip,session_id,model,dev,question,answer,reasoning,elapsed_ms}],total}
  - POST /test      {message,...} → 跑一条对话（委托 graph.chat）
读写委托 config 目录 + repositories.qa_log + integrations.api_gateway；目录/文件缺失时安全回落空列表。
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from real_agent.app import config
from real_agent.app.integrations import api_gateway

logger = logging.getLogger("real_agent.app.admin")

admin_router = APIRouter(prefix="/admin/api")

_UNKNOWN = "暂未收录"


def _safe_items(gen) -> dict:
    try:
        return {"items": list(gen)}
    except Exception:
        logger.warning("admin list failed", exc_info=True)
        return {"items": []}


# ──────────────────────────── 文本知识 ────────────────────────────
@admin_router.get("/docs")
def list_docs() -> dict:
    def gen():
        for p in sorted(Path(config.DOCS_DIR).glob("*.md")):
            st = p.stat()
            yield {"name": p.stem, "size": st.st_size, "mtime": int(st.st_mtime)}
    return _safe_items(gen())


@admin_router.get("/docs/{name}")
def get_doc(name: str) -> dict:
    p = Path(config.DOCS_DIR) / f"{name}.md"
    if not p.exists():
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"name": name, "content": p.read_text(encoding="utf-8")}


@admin_router.put("/docs/{name}")
def save_doc(name: str, body: dict) -> dict:
    p = Path(config.DOCS_DIR) / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.get("content", ""), encoding="utf-8")
    return {"name": name, "saved": True}


@admin_router.delete("/docs/{name}")
def delete_doc(name: str) -> dict:
    p = Path(config.DOCS_DIR) / f"{name}.md"
    if p.exists():
        p.unlink()
    return {"name": name, "deleted": True}


# ──────────────────────────── 图片知识 ────────────────────────────
def _image_dirs() -> "list[tuple[str, Path, str]]":
    # (dir 标签, 磁盘目录, URL 前缀)
    return [
        ("images", Path(config.KNOWLEDGE_IMAGE_DIR), "/knowledge-images"),
        ("app_images", Path(config.APP_IMAGE_DIR), "/app-images"),
    ]


@admin_router.get("/images")
def list_images() -> dict:
    def gen():
        for label, d, url_prefix in _image_dirs():
            if not d.exists():
                continue
            for p in sorted(d.iterdir()):
                if not p.is_file():
                    continue
                meta_path = p.with_suffix(p.suffix + ".meta.json")
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except Exception:
                        meta = {}
                yield {"key": f"{label}/{p.name}", "dir": label, "name": p.name,
                       "url": f"{url_prefix}/{p.name}", "meta": meta}
    return _safe_items(gen())


@admin_router.put("/images/{dirkey}/{name}/meta")
def save_image_meta(dirkey: str, name: str, body: dict) -> dict:
    for label, d, _ in _image_dirs():
        if label == dirkey:
            (d / f"{name}.meta.json").write_text(
                json.dumps(body, ensure_ascii=False), encoding="utf-8")
            return {"saved": True}
    raise HTTPException(status_code=404, detail="目录不存在")


# ──────────────────────────── 结构化数据 ────────────────────────────
def _data_count(obj) -> int:
    if isinstance(obj, (list, dict)):
        return len(obj)
    return 0


# 结构化数据域（/data 只列这些业务域文件，排除 capabilities/home_questions 等配置文件）。
_DATA_EXCLUDE = {"capabilities", "home_questions"}


@admin_router.get("/data")
def list_data() -> dict:
    def gen():
        for p in sorted(Path(config.DATA_DIR).glob("*.json")):
            if p.stem in _DATA_EXCLUDE:
                continue
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                obj = None
            yield {"name": p.stem, "count": _data_count(obj)}
    return _safe_items(gen())


@admin_router.get("/data/{name}")
def get_data(name: str) -> dict:
    p = Path(config.DATA_DIR) / f"{name}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="数据不存在")
    return {"name": name, "content": p.read_text(encoding="utf-8")}


@admin_router.put("/data/{name}")
def save_data(name: str, body: dict) -> dict:
    p = Path(config.DATA_DIR) / f"{name}.json"
    content = body.get("content")
    if content is None:
        content = json.dumps(body, ensure_ascii=False, indent=2)
    p.write_text(content, encoding="utf-8")
    return {"name": name, "saved": True}


# ──────────────────────────── 工具 / 接口目录 ────────────────────────────
@admin_router.get("/tools")
def list_tools() -> dict:
    return _safe_items(api_gateway.list_tools() if hasattr(api_gateway, "list_tools") else [])


@admin_router.get("/apis")
def search_apis_catalog(q: str = "") -> dict:
    return {"items": api_gateway.search_catalog(q)}


@admin_router.get("/api-detail")
def api_detail(path: str = "") -> dict:
    detail = api_gateway.api_detail(path) if hasattr(api_gateway, "api_detail") else None
    if not detail:
        raise HTTPException(status_code=404, detail="接口不存在或不在只读目录")
    return detail


@admin_router.get("/uncataloged")
def list_uncataloged() -> dict:
    return _safe_items(api_gateway.list_uncataloged() if hasattr(api_gateway, "list_uncataloged") else [])


@admin_router.get("/westbund")
def list_westbund() -> dict:
    items = list(api_gateway.list_westbund()) if hasattr(api_gateway, "list_westbund") else []
    return {"items": items, "total": len(items), "api_md_total": 0}


# ──────────────────────────── 测试中心 ────────────────────────────
class _TestRequest(BaseModel):
    message: str
    session_id: str = "admin_test"
    model: "str | None" = None
    mpsessid: "str | None" = None
    dev: bool = True


@admin_router.post("/test")
def run_test(body: _TestRequest) -> dict:
    from real_agent.app.agent.graph import chat
    reply = chat(body.message, session_id=body.session_id, model=body.model,
                 mpsessid=body.mpsessid or "", dev=body.dev)
    return {"reply": reply}


# ──────────────────────────── 运营日志 ────────────────────────────
@admin_router.get("/logs")
def get_logs(q: str = "", ip: str = "", limit: int = 100, offset: int = 0) -> dict:
    db = Path(config.DATA_DIR) / "qa_log.db"
    if not db.exists():
        return {"items": [], "total": 0}
    try:
        conn = sqlite3.connect(str(db))
        where, params = [], []
        if q:
            where.append("(question LIKE ? OR answer LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if ip:
            where.append("ip LIKE ?")
            params.append(f"%{ip}%")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute(f"SELECT COUNT(*) FROM qa_log{clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id,ts,ip,session_id,model,dev,question,answer,reasoning,elapsed_ms "
            f"FROM qa_log{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        conn.close()
    except Exception:
        logger.warning("admin logs query failed", exc_info=True)
        return {"items": [], "total": 0}
    items = [{
        "id": r[0],
        "ts": datetime.fromtimestamp(r[1]).strftime("%Y-%m-%dT%H:%M:%S") if r[1] else "",
        "ip": r[2] or "", "session_id": r[3] or "", "model": r[4] or "",
        "dev": r[5] or 0, "question": r[6] or "", "answer": r[7] or "",
        "reasoning": r[8] or "", "elapsed_ms": r[9],
    } for r in rows]
    return {"items": items, "total": total}
