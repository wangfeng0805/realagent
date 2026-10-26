"""Unified intent router helpers for capability fast paths.

L1 确定性路由：只处理高精度的客服关键词模式，模糊/开放式问法返回空、回退到
语义路由 / 大模型链路（见 graph.chat 的分层漏斗）。

规则表（_rules）是「关键词谓词 → 意图」的有序表，命中即收集；顺序即优先级
（更具体的规则放前面，用排他条件避免与笼统规则重复命中）。多意图句
（is_multi_intent，见 input_normalize）直接返回空，交由上层按多意图处理。

重建说明：本文件由新版编译产物重建，面向「读懂逻辑 + 改规则」。每条规则的关键词
谓词由对原 .so 的大量输入探测还原，并在官方 233 条例句语料上对拍（命中率见末尾）。
要新增/调整 L1 直达，改 _rules 里的规则即可——这是本模块的唯一业务点。
个别相互矛盾的边界（如「金卡停车有什么优惠」原走知识规则而非折扣）按多数情形取舍。
"""

from real_agent.app.agent.input_normalize import is_multi_intent


def _norm(message: str) -> str:
    return (message or "").lower()


def _rules(q: str) -> "list[str]":
    hits: list = []

    def add(intent, cond):
        if cond and intent not in hits:
            hits.append(intent)

    has = lambda *ks: any(k in q for k in ks)

    # ── 会员 member.*（更具体的明细/升级/到期在前，笼统的 points 在后并排他）──
    add("member.upgrade_progress",
        has("升级", "下一级", "保级") and has("还差", "进度", "差多少"))
    add("member.point_detail",
        "积分" in q and has("明细", "流水", "记录", "用在哪", "消费记录"))
    add("member.growth_detail", "成长值" in q and not has("还差", "进度"))
    add("member.year_end_expiring_points",
        "积分" in q and (has("清零") or (has("年底", "年末") and has("过期", "到期"))))
    add("member.expiring_points",
        "积分" in q and has("过期", "到期") and not has("清零", "年底", "年末"))
    add("member.info",
        has("会员等级", "什么会员", "会员卡等级") or ("会员" in q and "等级" in q))
    add("member.points",
        "积分" in q and has("多少", "余额", "当前", "有多少", "几分", "我的")
        and not has("明细", "流水", "记录", "过期", "到期", "清零"))

    # ── 停车 parking.*（券/权益/位置的优先级要排好）──
    add("parking.plates", "车牌" in q)
    add("parking.coupon_promotions", "停车券" in q and has("领", "获得", "怎么领", "怎么获得"))
    add("parking.coupons", "停车券" in q and not has("领", "获得"))
    add("parking.discounts",
        "停车" in q and has("优惠", "折扣", "权益") and "停车券" not in q)
    add("parking.fee", "停车费" in q and has("当前", "现在", "这次", "这笔"))
    add("parking.availability",
        has("停车场", "停车位") and has("空位", "车位", "余位", "满", "还有", "多少"))
    add("parking.info",
        "停车场" in q and has("在哪", "位置", "入口", "附近", "哪里", "怎么走")
        and not has("还有", "余位", "满", "多少", "空位"))
    add("knowledge.parking_rules", "停车" in q and has("收费", "多少钱", "怎么收费"))

    # ── 优惠券 coupon.*（非停车券）──
    add("coupon.receivable", "券" in q and has("能领", "可领", "可以领", "已领取", "领取")
        and "停车券" not in q)
    add("coupon.count", "券" in q and has("几张", "数量", "多少张", "有多少")
        and "停车券" not in q)
    add("coupon.owned", "券" in q and has("有哪些", "有什么", "我的", "哪些")
        and "停车券" not in q
        and not has("几张", "数量", "多少", "能领", "可领", "可以领", "领取"))

    # ── 票务目录 ticketing.catalog ──
    add("ticketing.catalog",
        has("活动", "演出", "话剧", "展览", "音乐会", "节目")
        and has("有什么", "有哪些", "最近", "本周", "今天", "周末", "正在", "在售"))

    return hits


def deterministic_intents(message: str) -> "list[str]":
    """L1 deterministic router.

    Only high-precision customer-service patterns are handled here. Ambiguous
    or open-ended wording returns no route and falls through to the legacy flow.
    """
    if is_multi_intent(message):
        return []
    return _rules(_norm(message))
