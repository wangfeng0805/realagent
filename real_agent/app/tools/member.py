"""会员领域工具（新版 / real_agent）。

会员资料/等级/认证/券/积分审计等只读工具。登录态从 config 的 mpsessid 透传。
取数统一走 api_get_path / api_post（小程序只读网关）与 member_api（会员信息快取）。

重建说明：由 .so 重建（readable）。函数名/签名对 .so 还原；取数委托已重建的 integrations 层。
"""
from typing import Any
from real_agent.app.integrations.miniprogram_api import api_get_path, api_post
from real_agent.app.integrations.member_api import fetch_current_member


def token_from_config(config: "Any") -> str:
    try:
        return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception:
        return ""


def get_current_member_info(config: "Any") -> dict:
    """当前登录会员信息（等级/积分/成长值/有效期）。"""
    return fetch_current_member(token_from_config(config))


def _get(config: "Any", path: str, params: "dict | None" = None) -> dict:
    return api_get_path(path, token_from_config(config), params or {}, require_session=True)


def member_get_personal_info(config: "Any") -> dict:
    return _get(config, "/member/info/personal.xhtml")


def member_list_certifications(config: "Any") -> dict:
    return _get(config, "/member/cert/list.xhtml")


def member_levels(config: "Any") -> dict:
    return _get(config, "/member/level/list.xhtml")


def member_code(config: "Any") -> dict:
    return _get(config, "/member/code/get.xhtml")


def member_logon_info(config: "Any") -> dict:
    return _get(config, "/member/logon/info.xhtml")


def member_personal_maps(config: "Any") -> dict:
    return _get(config, "/member/personal/maps.xhtml")


def member_personal_dynamic_fields(config: "Any") -> dict:
    return _get(config, "/member/personal/dynamicFields.xhtml")


def member_dynamic_field_options(config: "Any", param_value: str = "industry") -> dict:
    return _get(config, "/member/dynamic/options.xhtml", {"paramValue": param_value})


def member_coupons_by_status(config: "Any", status: str = "available",
                             page_no: int = 1, page_size: int = 20) -> dict:
    return _get(config, "/member/coupon/list.xhtml",
                {"status": status, "pageNo": page_no, "pageSize": page_size})


def member_coupon_promotion(config: "Any") -> dict:
    return _get(config, "/member/coupon/promotion.xhtml")


def member_coupon_other_info(config: "Any", cardpass: str) -> dict:
    return _get(config, "/member/coupon/otherInfo.xhtml", {"cardpass": cardpass})


def coupon_promotion_public(config: "Any") -> dict:
    return _get(config, "/coupon/promotion/public.xhtml")


def member_point_audit(config: "Any", status: str = "", page_no: int = 1, page_size: int = 20) -> dict:
    return _get(config, "/member/point/audit.xhtml",
                {"status": status, "pageNo": page_no, "pageSize": page_size})


def member_bind_info(config: "Any", code: str) -> dict:
    return _get(config, "/member/bind/info.xhtml", {"code": code})


def member_birthday_by_cert(config: "Any", certificate_type: str, certificate_no: str) -> dict:
    return _get(config, "/member/birthday/byCert.xhtml",
                {"certificateType": certificate_type, "certificateNo": certificate_no})
