"""Load local agent skills from real_agent/skills.

读取 real_agent/skills/<name>/SKILL.md，去掉 YAML frontmatter，返回正文。
用 lru_cache 避免重复读盘。

说明：本文件由编译产物重建，行为与原实现一致（已核对 load_skill 输出逐字相同）。
"""

from functools import lru_cache

from real_agent.app.config import BASE_DIR


@lru_cache(maxsize=16)
def load_skill(name: str) -> str:
    path = BASE_DIR / "skills" / name / "SKILL.md"
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text
