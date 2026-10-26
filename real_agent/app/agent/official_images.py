"""官方图片直达 official_images（新版 / real_agent）。

回答需要配官方图/静态设施说明的问法（停车指引图、卫生间分布图、客服中心指示图、出行攻略、
地铁路线），命中则返回**静态成稿 + 本地知识图**（/knowledge-images/…），否则 None 交回 graph。

重建说明：由 .so 重建。图片常量（PARKING_IMAGE/RESTROOM_IMAGE/SERVICE_IMAGE/TRAVEL_IMAGE/
SPORT_IMAGE/PET_IMAGE、GATE_M_ADDRESS）与各分支**静态成稿字节级还原**（这些文案在 .so 内即为
硬编码静态文本，非实时数据，故逐字一致）。触发关键词集为**结构忠实重建**（偏保守，避免把
「停车费/实时车位」这类实时问法误拦成图）。
"""
import json  # noqa: F401

from real_agent.app.agent.table_format import key_value_table, markdown_table  # noqa: F401

GATE_M_ADDRESS = "上海市徐汇区龙腾大道2266号"
PARKING_IMAGE = "/knowledge-images/0c0a9ebacfcf89241129adb1c7636589.jpeg"
PET_IMAGE = "/knowledge-images/e7c2491a998b8f11619635295c13e867.jpeg"
RESTROOM_IMAGE = "/knowledge-images/ffca58d56af065d3be793dc118a28b61.jpeg"
SERVICE_IMAGE = "/knowledge-images/2379312b7f7ca4310238fc204c9d8fcd.jpeg"
SPORT_IMAGE = "/knowledge-images/b9b14b7886e485e1b1de6542fbdefce4.jpeg"
TRAVEL_IMAGE = "/knowledge-images/7d93ecd2815acd71ef824a1e943ad734.jpeg"

# ───────────── 静态成稿（字节级还原）─────────────
_PARKING_REPLY = (
    "西岸梦中心设有 A/B/C/D 四个停车分区，并设北区、南区两个地下停车场入口。详细如下：\n\n"
    "| 类型 | 数量 | 名称/说明 |\n| --- | --- | --- |\n"
    "| 停车分区 | 4个 | A区、B区、C区、D区 |\n"
    "| 地下停车场入口 | 2个 | 北区入口、南区入口 |\n"
    "| 独立停车场总数 | 待确认 | 当前小梦还没有收录相关的信息哦~ |\n\n"
    "![GATE M 西岸梦中心停车指引图](/knowledge-images/0c0a9ebacfcf89241129adb1c7636589.jpeg)"
)
_RESTROOM_REPLY = (
    "馆内共有 7 处卫生间标记哦～具体分布见下图：\n\n"
    "| 项目 | 信息 |\n| --- | --- |\n| 设施标记 | 7处 |\n"
    "| 类型 | 普通男女卫生间、带儿童/无障碍图形的标记 |\n"
    "| 楼层/门牌/坐标 | 当前小梦还没有收录相关的信息哦~ |\n\n"
    "![GATE M 西岸梦中心卫生间指示图](/knowledge-images/ffca58d56af065d3be793dc118a28b61.jpeg)"
)
_SERVICE_REPLY = (
    "这是官方 **客服中心指示图**，图中以橙色边框的“i”标记客服中心大致位置。"
    "原图没有标注楼层、门牌或坐标，请结合现场导视确认。\n\n"
    "![GATE M 西岸梦中心客服中心指示图](/knowledge-images/2379312b7f7ca4310238fc204c9d8fcd.jpeg)"
)
_TRAVEL_REPLY = (
    "| 方式 | 指引 |\n| --- | --- |\n"
    "| 打车 | GATE M 西岸梦中心下车点 |\n"
    "| 自驾 | 北区/南区地下停车场入口 |\n"
    "| 地铁 | 11号线龙耀路站1号口或2号口 |\n"
    "| 公交 | 浦西滨江1路至龙腾大道龙文路站 |\n\n"
    '```nav\n{"name": "GATE M 西岸梦中心", "address": "上海市徐汇区龙腾大道2266号", '
    '"image": "/knowledge-images/7d93ecd2815acd71ef824a1e943ad734.jpeg", "image_position": "travel"}\n```'
)
_METRO_REPLY = (
    "| 方式 | 路线 | 步行时间 |\n| --- | --- | --- |\n"
    "| 地铁 | 11号线 → 龙耀路站1号口或2号口 → 沿龙文路步行 | 约10分钟 |\n\n"
    '```nav\n{"name": "GATE M 西岸梦中心", "address": "上海市徐汇区龙腾大道2266号", '
    '"image": "/knowledge-images/7d93ecd2815acd71ef824a1e943ad734.jpeg", "image_position": "travel"}\n```'
)

# ───────────── 触发关键词集（结构忠实）─────────────
_PARKING_CUES = ("停车指引", "停车指示", "停车分区", "停车场入口", "停车场", "停车区域", "几个停车场")
_RESTROOM_CUES = ("卫生间", "洗手间", "厕所")
_SERVICE_CUES = ("客服中心",)
_METRO_CUES = ("地铁", "几号线", "11号线")
_TRAVEL_CUES = ("出行攻略", "交通指引", "怎么过来的图")


def _nav_card(name: str, address: str, image: str, position: str = "travel") -> str:
    payload = {"name": name, "address": address, "image": image, "image_position": position}
    return "```nav\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def answer_official_image_request(message: str) -> "str | None":
    """命中官方图/静态设施说明问法时返回静态成稿，否则 None。"""
    q = message or ""
    if any(c in q for c in _RESTROOM_CUES):
        return _RESTROOM_REPLY
    if any(c in q for c in _SERVICE_CUES):
        return _SERVICE_REPLY
    if any(c in q for c in _PARKING_CUES):
        return _PARKING_REPLY
    if any(c in q for c in _METRO_CUES):
        return _METRO_REPLY
    if any(c in q for c in _TRAVEL_CUES):
        return _TRAVEL_REPLY
    return None
