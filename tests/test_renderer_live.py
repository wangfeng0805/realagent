"""capabilities.renderer 模板测试（依据线上 http://47.116.7.1 实测 + .so 对拍修正）。

跑法： pytest tests/test_renderer_live.py -v
覆盖确定性模板：空 payload→未知兜底、member/fee 表格、优惠券/成长/积分明细表格列。
单元格取值绑定线上接口字段（装配点），此处只断言模板结构与兜底。
"""
import pytest
from real_agent.app.capabilities import renderer as R

_UNKNOWN = "当前小梦还没有收录相关的信息哦~"
_HANDLED = ["member.info", "member.points", "member.point_detail", "member.expiring_points",
            "member.year_end_expiring_points", "member.growth_detail", "member.upgrade_progress",
            "coupon.count", "coupon.owned", "coupon.receivable", "parking.fee",
            "parking.availability", "parking.info", "parking.plates", "parking.coupons"]


@pytest.mark.parametrize("intent", _HANDLED)
def test_empty_payload_is_unknown(intent):
    assert R.render(intent, {}) == _UNKNOWN


def test_unhandled_intents_none():
    for i in ["member.levels", "coupon.detail", "knowledge.search"]:
        assert R.render(i, {}) is None


def test_member_info_table():
    m = {"found": True, "display_name": "V", "member_level_name": "WeM2", "points": 29,
         "effective_growth_value": 324, "membership_end_time": "长期有效"}
    out = R.render("member.info", {"member": m, "found": True})
    assert out == ("您的会员信息如下：\n\n| 项目 | 信息 |\n| --- | --- |\n"
                   "| 会员等级 | WeM2 |\n| 当前积分 | 29 积分 |\n| 有效成长值 | 324 |\n| 会员有效期至 | 长期有效 |")


def test_member_points_single_line():
    m = {"found": True, "points": 29}
    assert R.render("member.points", {"member": m, "found": True}) == "您当前有 **29 积分**。"


def test_parking_fee_table():
    out = R.render("parking.fee", {"found": True, "data": {"fee": 15, "duration": "1小时30分"}})
    assert out == ("这笔停车费我帮您查到了：\n\n| 项目 | 信息 |\n| --- | --- |\n"
                   "| 当前应付金额 | 15 元 |\n| 停车时长 | 1小时30分 |\n\n最终金额以停车缴费页和出口结算为准哦。")


def test_coupon_count_available():
    assert R.render("coupon.count", {"found": True, "data": {"count": 3}}) == "您当前有 **3 张可用券**。"


def test_coupon_owned_table_header():
    out = R.render("coupon.owned", {"found": True, "data": {"coupons": [
        {"name": "星巴克券", "startTime": "2026-01-01", "endTime": "2026-12-31"}]}})
    assert "| 券名称 | 有效期 |" in out and "张**：" in out


def test_parking_availability_six_columns():
    out = R.render("parking.availability", {"found": True, "data": {"lots": [
        {"name": "A区", "location": "北", "total": 300, "free": 120, "hours": "全天", "charge": "有"}]}})
    assert "| 停车场 | 位置 | 总车位 | 剩余车位 | 营业时间 | 充电桩 |" in out
