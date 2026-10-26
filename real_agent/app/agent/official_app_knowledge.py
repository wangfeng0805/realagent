"""官方 App/场馆导航知识直达 official_app_knowledge（新版 / real_agent）。

回答「怎么去西岸梦中心 / 地址在哪 / 怎么导航过去」这类场馆位置+导航问法：命中则返回地址 +
导航卡（```nav```），否则 None 交回 graph。_wants_image 判断是否顺带附出行攻略图。

重建说明：由 .so 重建。常量 _VENUE_ADDRESS / _VENUE_TRAVEL_IMAGE 与导航成稿**字节级还原**
（静态文本）。触发关键词集与 _wants_image 判定为**结构忠实重建**（偏保守）。
"""
import json  # noqa: F401

from real_agent.app.agent.table_format import key_value_table, markdown_table  # noqa: F401

_VENUE_ADDRESS = "上海市徐汇区龙腾大道2266号"
_VENUE_TRAVEL_IMAGE = "/knowledge-images/7d93ecd2815acd71ef824a1e943ad734.jpeg"

# 导航意图线索（需要同时提到场馆/去向）。
_NAV_CUES = ("怎么去", "怎么到", "怎么过去", "导航", "路线", "地址", "在哪", "位置", "地方")
_VENUE_CUES = ("西岸梦中心", "梦中心")
# 顺带要图的线索。
_IMAGE_CUES = ("看图", "图", "示意图", "地图")


def _wants_image(message: str) -> bool:
    """是否顺带附出行攻略图（含看图/图等线索，但「出行攻略图」等本身是 official_images 的活儿）。"""
    q = message or ""
    return "看图" in q or (any(c in q for c in _IMAGE_CUES) and "攻略图" not in q)


def _venue_nav_card(image: "str | None" = None) -> str:
    payload = {"name": "GATE M 西岸梦中心", "address": _VENUE_ADDRESS,
               "image": image or _VENUE_TRAVEL_IMAGE, "image_position": "travel"}
    return "```nav\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def _with_image(text: str, image: str) -> str:
    return f"{text}\n\n![GATE M 西岸梦中心出行攻略指示图]({image})"


def answer_official_app_request(message: str) -> "str | None":
    """命中场馆位置/导航问法时返回地址 + 导航卡，否则 None。"""
    q = message or ""
    if any(c in q for c in _NAV_CUES) and any(v in q for v in _VENUE_CUES):
        head = (f"西岸梦中心的地址是 **{_VENUE_ADDRESS}**，就在徐汇滨江沿岸～\n\n"
                "这就为您生成导航：\n\n")
        return head + _venue_nav_card()
    return None
