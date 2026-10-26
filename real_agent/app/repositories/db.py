"""园区演示数据层（新版 / real_agent）。

内置种子 SQLite（景点/活动/POI/路线/会员/行为/停车/实时），为推荐与行程类演示问法提供
确定性数据。线上实时数据走 integrations.*，本层仅承载演示/静态域。

重建说明：由 .so 重建（readable 骨架）。表与查询函数签名对 .so 还原；schema/种子为可读重写。
"""
import sqlite3
import threading
from pathlib import Path
from real_agent.app.config import DATA_DIR

_DB_PATH = DATA_DIR / "park_demo.db"
_lock = threading.Lock()
_inited = False


def _locked(fn):
    def w(*a, **k):
        with _lock:
            return fn(*a, **k)
    return w


def _conn():
    global _inited
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    if not _inited:
        _init_schema(conn)
        _seed_if_empty(conn)
        _inited = True
    return conn


def _init_schema(conn=None) -> None:
    c = conn or sqlite3.connect(str(_DB_PATH))
    c.executescript(
        "CREATE TABLE IF NOT EXISTS attractions(id INTEGER PRIMARY KEY, name TEXT, theme TEXT, intro TEXT);"
        "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, name TEXT, day TEXT, tags TEXT, location TEXT);"
        "CREATE TABLE IF NOT EXISTS pois(id INTEGER PRIMARY KEY, name TEXT, category TEXT, location TEXT);"
        "CREATE TABLE IF NOT EXISTS routes(id INTEGER PRIMARY KEY, theme TEXT, stops TEXT);"
        "CREATE TABLE IF NOT EXISTS members(member_id TEXT PRIMARY KEY, name TEXT, level TEXT, interests TEXT);"
        "CREATE TABLE IF NOT EXISTS behavior(member_id TEXT PRIMARY KEY, visited TEXT);"
    )
    c.commit()


def _seed_if_empty(conn=None) -> None:
    c = conn or sqlite3.connect(str(_DB_PATH))
    if c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
        c.executemany("INSERT INTO events(name,day,tags,location) VALUES(?,?,?,?)",
                      [("亲子手作市集", "", "亲子,手作", "北区广场"),
                       ("周末露天音乐会", "", "音乐,户外", "滨江舞台")])
        c.commit()


def _attraction_row(row) -> dict:
    return {"id": row["id"], "name": row["name"], "theme": row["theme"], "intro": row["intro"]}


def _event_row(row) -> dict:
    return {"id": row["id"], "name": row["name"], "day": row["day"],
            "tags": (row["tags"] or "").split(","), "location": row["location"]}


@_locked
def search_attractions(query: str = "") -> "list[dict]":
    c = _conn()
    rows = c.execute("SELECT * FROM attractions WHERE name LIKE ?", (f"%{query}%",)).fetchall()
    return [_attraction_row(r) for r in rows]


@_locked
def search_events(query: str = "", date: str = "") -> "list[dict]":
    c = _conn()
    rows = c.execute("SELECT * FROM events WHERE name LIKE ?", (f"%{query}%",)).fetchall()
    return [_event_row(r) for r in rows]


@_locked
def all_events() -> "list[dict]":
    c = _conn()
    return [_event_row(r) for r in c.execute("SELECT * FROM events").fetchall()]


@_locked
def check_sessions(attraction: str = "", date: str = "") -> "list[dict]":
    return []


@_locked
def find_pois(query: str = "") -> "list[dict]":
    c = _conn()
    rows = c.execute("SELECT * FROM pois WHERE name LIKE ? OR category LIKE ?",
                     (f"%{query}%", f"%{query}%")).fetchall()
    return [{"name": r["name"], "category": r["category"], "location": r["location"]} for r in rows]


@_locked
def get_parking() -> dict:
    return {"lots": []}


@_locked
def get_realtime() -> dict:
    return {"crowd": "正常", "weather": "晴"}


@_locked
def get_routes(theme: str = "") -> "list[dict]":
    c = _conn()
    rows = c.execute("SELECT * FROM routes WHERE theme LIKE ?", (f"%{theme}%",)).fetchall()
    return [{"theme": r["theme"], "stops": (r["stops"] or "").split(",")} for r in rows]


@_locked
def find_member(query: str):
    if not query:
        return None
    c = _conn()
    r = c.execute("SELECT * FROM members WHERE member_id=? OR name=?", (query, query)).fetchone()
    return {"member_id": r["member_id"], "name": r["name"], "level": r["level"],
            "interests": (r["interests"] or "").split(",")} if r else None


@_locked
def get_user_behavior(member_id: str) -> dict:
    c = _conn()
    r = c.execute("SELECT * FROM behavior WHERE member_id=?", (member_id,)).fetchone()
    return {"visited": (r["visited"] or "").split(",")} if r else {}
