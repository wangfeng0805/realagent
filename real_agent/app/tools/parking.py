"""停车领域工具（新版 / real_agent）。

车位/收费/车牌/缴费记录/订单/发票等停车相关的只读工具。登录态从 config 的 mpsessid 透传。

重建说明：由 .so 重建（readable）。签名对 .so 还原；取数委托 integrations.miniprogram_api
（fetch_parking_status 等）与 api_get_path（均已重建）。
"""
from typing import Any
from real_agent.app.integrations.miniprogram_api import fetch_parking_status, api_get_path


def token_from_config(config: "Any") -> str:
    try:
        return (config or {}).get("configurable", {}).get("mpsessid") or ""
    except Exception:
        return ""


def parking_query_fee(config: "Any", park_id: str, api_type: str = "", plate_no: str = "",
                      terminal_code: str = "") -> dict:
    return api_get_path("/parking/fee/query.xhtml", token_from_config(config),
                        {"parkId": park_id, "apiType": api_type, "plateNo": plate_no,
                         "terminalCode": terminal_code}, require_session=True)


def parking_list_lots(config: "Any") -> dict:
    return fetch_parking_status(token_from_config(config))


def parking_list_plates(config: "Any") -> dict:
    return api_get_path("/parking/plate/list.xhtml", token_from_config(config), {}, require_session=True)


def parking_list_orders(config: "Any") -> dict:
    return api_get_path("/parking/order/list.xhtml", token_from_config(config), {}, require_session=True)


def parking_order_detail(config: "Any", trade_no: str) -> dict:
    return api_get_path("/parking/order/detail.xhtml", token_from_config(config),
                        {"tradeNo": trade_no}, require_session=True)


def parking_invoice_list(config: "Any", trade_no: str) -> dict:
    return api_get_path("/parking/invoice/list.xhtml", token_from_config(config),
                        {"tradeNo": trade_no}, require_session=True)
