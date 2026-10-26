"""问答日志落库（新版 / real_agent）。

把每轮问答写入本地 SQLite（data/qa_log.db），供运营后台 /admin/api/logs 查看与复盘。
best-effort：写库失败不影响对话主流程。

重建说明：本文件由新版编译产物（repositories/qa_log.*.so）重建（readable）。表结构与
log_qa 签名按 .so 还原；建表/插入为可读重写。
"""
import logging, sqlite3, time
from pathlib import Path
from real_agent.app.config import DATA_DIR

logger = logging.getLogger("real_agent.app.repositories.qa_log")
_DB_PATH = DATA_DIR / "qa_log.db"
_inited = False

def _conn():
    global _inited
    conn = sqlite3.connect(str(_DB_PATH))
    if not _inited:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS qa_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, ip TEXT, session_id TEXT, "
            "model TEXT, dev INTEGER, question TEXT, answer TEXT, reasoning TEXT, elapsed_ms INTEGER)"
        )
        conn.commit(); _inited = True
    return conn

def log_qa(ip=None, session_id=None, model=None, dev=False, question="", answer="",
           reasoning="", elapsed_ms=None) -> None:
    """写入一条问答记录（失败仅告警）。"""
    try:
        conn = _conn()
        conn.execute(
            "INSERT INTO qa_log (ts, ip, session_id, model, dev, question, answer, reasoning, elapsed_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (int(time.time()), ip, session_id, model, 1 if dev else 0, question, answer, reasoning, elapsed_ms),
        )
        conn.commit(); conn.close()
    except Exception:
        logger.warning("qa_log insert failed", exc_info=True)
