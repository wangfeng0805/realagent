"""成稿后追加「行动卡」（新版 / real_agent）。

在顾客成稿末尾按问法追加 1~4 张可点击的建议卡（```suggest 块），或在问停车场入口/导航时
追加停车场入口导航卡（```nav 块），引导用户进入下一步常见操作。

规则驱动：_RULES 是 25 条 (关键词组, 领域, 卡片) 规则。命中逻辑（对 .so 还原）：
  1) 若成稿本身是在「反问澄清」（以 ？/? 结尾且含索要信息的措辞）→ 不追加任何卡；
  2) 否则按 _RULES 顺序收集命中卡：问句含该规则任一关键词、领域匹配、且卡片的 action.q
     不等于用户原问句（不建议用户刚问过的）、标题不重复；最多 4 张 → ```suggest；
  3) 若一张都没命中，但问句同时含导航词(_NAV_TERMS)和停车词(_PARKING_TERMS)
     → 追加南北停车场入口 ```nav 卡。

重建说明：本文件由新版编译产物（agent/action_cards.*.so）重建。
- 常量（GATE_M_ADDRESS/PARKING_IMAGE/_ASK_MARKERS/_NAV_TERMS/_PARKING_TERMS/_RULES 全 25 条）
  字节级还原；
- cards/suggest/ask_card/_nav_cards/_domain_ok/_is_clarifying/trailing_action_cards/
  append_action_cards 经随机对拍与原 .so 一致（命中/抑制/去重/上限/nav 回退全部核对）。
"""

import json

GATE_M_ADDRESS = "上海市徐汇区龙腾大道2266号"
PARKING_IMAGE = "/knowledge-images/0c0a9ebacfcf89241129adb1c7636589.jpeg"

_MAX_CARDS = 4

# 成稿「反问澄清」措辞（配合 ？结尾判定）
_ASK_MARKERS = (
    "告诉我", "发我", "请提供", "提供一下", "是哪一辆", "哪一辆", "哪一个",
    "完整车牌", "你的车牌", "先确认", "需要先确认", "方便告诉", "方便提供", "麻烦提供",
)
# 导航意图词 / 停车意图词（两者同现才出停车场入口导航卡）
_NAV_TERMS = ("导航", "入口", "怎么走", "怎么去", "在哪")
_PARKING_TERMS = ("停车", "车位", "车库")

# (关键词组, 领域, 卡片)；领域为 "" 表示不限领域
_RULES = (
    (("几个停车场", "停车场列表", "有哪些停车场", "停车场在哪", "停车场分布", "几个停车场分区"), "",
     {"title": "实时停车费", "meta": "查在场车辆的实时停车费", "action": {"label": "看实时停车费", "q": "我现在停车费多少"}, "icon": "💰"}),
    (("几个停车场", "停车场列表", "有哪些停车场", "停车场在哪", "停车场分布", "几个停车场分区"), "",
     {"title": "收费标准", "meta": "免费时长与封顶价", "action": {"label": "看收费标准", "q": "停车怎么收费"}, "icon": "📄"}),
    (("几个停车场", "停车场列表", "有哪些停车场", "停车场在哪", "停车场分布", "几个停车场分区"), "",
     {"title": "停车区域", "meta": "看 A/B/C/D 停车分区", "action": {"label": "看停车区域", "q": "停车场有哪些分区"}, "icon": "🗺️"}),
    (("几个停车场", "停车场列表", "有哪些停车场", "停车场在哪", "停车场分布", "几个停车场分区"), "",
     {"title": "停车入口", "meta": "看地下停车场入口", "action": {"label": "看停车入口", "q": "停车场有哪些入口"}, "icon": "🚗"}),
    (("缴费记录", "缴费历史", "停车订单", "停车账单"), "parking",
     {"title": "缴费记录", "meta": "查最近停车订单与支付状态", "action": {"label": "查缴费记录", "q": "我的停车缴费记录"}, "icon": "🧾"}),
    (("停车券",), "parking",
     {"title": "我的停车券", "meta": "看停车券适用范围和有效期", "action": {"label": "看停车券", "q": "我有哪些停车券"}, "icon": "🎫"}),
    (("停车费", "停车多少钱", "停车收费", "免费时长", "封顶"), "parking",
     {"title": "停车收费规则", "meta": "免费时长与封顶价", "action": {"label": "看收费规则", "q": "停车怎么收费"}, "icon": "💰"}),
    (("车位", "空位", "余位"), "parking",
     {"title": "实时车位", "meta": "各停车场当前空位", "action": {"label": "看实时车位", "q": "现在还有车位吗"}, "icon": "🅿️"}),
    (("车牌",), "parking",
     {"title": "停车缴费记录", "meta": "看这些车牌的停车缴费记录", "action": {"label": "看缴费记录", "q": "我的停车缴费记录"}, "icon": "🚗"}),
    (("发票", "开票"), "parking",
     {"title": "停车发票", "meta": "查停车订单的发票状态", "action": {"label": "看停车发票", "q": "我的停车发票开出来了吗"}, "icon": "📄"}),
    (("发票", "开票"), "ticketing",
     {"title": "票务发票", "meta": "查票务订单发票", "action": {"label": "看票务发票", "q": "我的票务订单发票"}, "icon": "📄"}),
    (("积分",), "member",
     {"title": "我的积分", "meta": "看当前积分与变动明细", "action": {"label": "看我的积分", "q": "我有多少积分"}, "icon": "⭐"}),
    (("成长值", "升级", "等级"), "member",
     {"title": "升级进度", "meta": "还差多少成长值升级", "action": {"label": "看升级进度", "q": "我还差多少升级"}, "icon": "📈"}),
    (("权益",), "member",
     {"title": "会员权益", "meta": "看您这一档能享受什么", "action": {"label": "看我的权益", "q": "我有什么权益"}, "icon": "🎁"}),
    (("优惠券", "我的券", "卡包"), "member",
     {"title": "我的优惠券", "meta": "看可用券与有效期", "action": {"label": "看我的券", "q": "我有哪些优惠券"}, "icon": "🎟️"}),
    (("活动", "演出", "展览", "快闪"), "ticketing",
     {"title": "近期活动", "meta": "看最近有哪些活动", "action": {"label": "看活动", "q": "最近有哪些活动"}, "icon": "🎪"}),
    (("场次", "票种", "票价"), "ticketing",
     {"title": "场次票种", "meta": "看可选场次与票价", "action": {"label": "看场次", "q": "有哪些场次可选"}, "icon": "🎭"}),
    (("票务订单", "我的票", "我的门票", "门票", "哪些票", "票务"), "ticketing",
     {"title": "我的票务订单", "meta": "看订单与可用门票", "action": {"label": "看我的票", "q": "我有哪些票务订单"}, "icon": "🎫"}),
    (("预约",), "reservation",
     {"title": "可预约项目", "meta": "看有哪些项目可预约", "action": {"label": "看可预约", "q": "有哪些项目可以预约"}, "icon": "📅"}),
    (("兑换", "积分商城", "积分能换"), "shopping",
     {"title": "积分商城", "meta": "看积分能兑换什么", "action": {"label": "看可兑换", "q": "积分商城有什么可以兑换"}, "icon": "🛍️"}),
    (("文创", "商品"), "shopping",
     {"title": "文创商品", "meta": "看在售文创商品", "action": {"label": "看商品", "q": "有哪些文创商品"}, "icon": "🛒"}),
    (("租赁", "租借", "租个", "借个"), "shopping",
     {"title": "可租借物品", "meta": "看能租什么、押金多少", "action": {"label": "看租借", "q": "有哪些可以租的物品"}, "icon": "☂️"}),
    (("我的订单", "商城订单", "物流", "快递"), "shopping",
     {"title": "我的订单", "meta": "看商城订单与物流", "action": {"label": "看我的订单", "q": "我有哪些商城订单"}, "icon": "📦"}),
    (("收货地址", "我的地址"), "shopping",
     {"title": "我的收货地址", "meta": "看已保存的收货地址", "action": {"label": "看我的地址", "q": "我保存了哪些收货地址"}, "icon": "📍"}),
    (("商户", "店铺", "餐饮", "吃什么", "好吃", "美食", "餐厅", "营业时间"), "merchant_venue",
     {"title": "商户导览", "meta": "按分类/位置找店", "action": {"label": "找商户", "q": "有哪些商户"}, "icon": "🏬"}),
)


# ──────────────────────────── 卡片块编码 ────────────────────────────
def cards(items: "list[dict]") -> str:
    """编码成 ```cards 块。"""
    return "```cards\n" + json.dumps(items, ensure_ascii=False) + "\n```"


def suggest(items: "list[dict]") -> str:
    """编码成 ```suggest 块（行动建议卡）。"""
    return "```suggest\n" + json.dumps(items, ensure_ascii=False) + "\n```"


def ask_card(title: str, meta: str, label: str, question: str, icon: str = "") -> dict:
    """构造一张行动卡。"""
    return {"title": title, "meta": meta, "action": {"label": label, "q": question}, "icon": icon}


def _nav_cards() -> str:
    """南北两个地下停车场入口的 ```nav 导航卡。"""
    north = {
        "name": "GATE M 西岸梦中心北区地下停车场入口", "image_position": "parking-north",
        "address": GATE_M_ADDRESS, "image": PARKING_IMAGE,
    }
    south = {
        "name": "GATE M 西岸梦中心南区地下停车场入口", "image_position": "parking-south",
        "address": GATE_M_ADDRESS, "image": PARKING_IMAGE,
    }
    return ("```nav\n" + json.dumps(north, ensure_ascii=False) + "\n```"
            + "\n\n```nav\n" + json.dumps(south, ensure_ascii=False) + "\n```")


# ──────────────────────────── 命中判定 ────────────────────────────
def _domain_ok(rule_domain: str, domains) -> bool:
    """领域匹配：规则不限领域(空)、或未给领域、或规则领域在给定领域内 → 放行。"""
    if not rule_domain:
        return True
    if not domains:
        return True
    return rule_domain in domains


def _is_clarifying(answer: str) -> bool:
    """成稿是否在反问澄清：以 ？/? 结尾，且含任一索要信息的措辞。"""
    text = (answer or "").rstrip()
    if not text.endswith(("？", "?")):
        return False
    return any(mk in answer for mk in _ASK_MARKERS)


def cards_for(message: str, domains=None) -> str:
    """按问法选出行动卡块（```suggest 或 ```nav），没有则空串。"""
    picked: "list[dict]" = []
    seen_titles: "set[str]" = set()
    for keywords, rule_domain, card in _RULES:
        if not _domain_ok(rule_domain, domains):
            continue
        if not any(kw in message for kw in keywords):
            continue
        if card["action"]["q"] == message:        # 不建议用户刚问过的那句
            continue
        if card["title"] in seen_titles:
            continue
        seen_titles.add(card["title"])
        picked.append(card)
        if len(picked) >= _MAX_CARDS:
            break
    if picked:
        return suggest(picked)
    # 没有建议卡时，停车场入口/导航意图 → 停车场入口导航卡
    if any(n in message for n in _NAV_TERMS) and any(p in message for p in _PARKING_TERMS):
        return _nav_cards()
    return ""


# ──────────────────────────── 对外 ────────────────────────────
def trailing_action_cards(answer: str, message: str, domains=None) -> str:
    """返回要追加到成稿末尾的卡片后缀（"\\n\\n" + 块），无则空串。

    成稿本身在反问澄清时不追加，避免「又要信息又给建议」的割裂感。
    """
    if not (answer or "").strip():     # 空成稿不追加
        return ""
    if _is_clarifying(answer):
        return ""
    block = cards_for(message, domains)
    return ("\n\n" + block) if block else ""


def append_action_cards(answer: str, message: str, domains=None) -> str:
    """把行动卡追加到成稿末尾并返回完整成稿。"""
    return (answer or "") + trailing_action_cards(answer or "", message, domains)
