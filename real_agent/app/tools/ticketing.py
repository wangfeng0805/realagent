"""活动票务域只读工具（ticketing）。

子域：活动项目(§3) / 场次票种(§4) / 票务订单(§5) + 优惠/发票/场馆横切。
依赖链：programId←ticketing_list_programs → showId←ticketing_show_schedules →
ticketing_ticket_types；订单 tradeNo←ticketing_list_*_orders → 详情/优惠/发票。
所有 ID 必须来自上游返回，不能臆造；token/appId 由通道注入。

说明：本模块由新版编译产物重建，面向「读懂逻辑 + 改工具」。
每个工具的名称、描述（LLM 据此选工具）、签名、接口路径均从 .so 还原；
参数名→接口字段按 snake→camelCase 约定映射，require_session 按是否 /member/ 路径推断，
个别字段映射如与实际接口不符，照此处路径对照接口文档微调即可。
"""

from typing import Any

from langchain_core.tools import tool

from real_agent.app.integrations.miniprogram_api import (
    api_get_path,
    token_from_config,
)


def _need(name: str) -> dict:
    """缺必填参数时的统一返回：提示上层按 missing_required 补齐后重试。"""
    return {"found": False, "reason": "need_params", "missing_required": [name]}


@tool
def ticketing_list_programs(config: Any, keyword: str = '', category: str = '', stadium_id: str = '', date: str = '') -> dict:
    """查询活动/项目列表，可按关键词、分类、场馆、日期筛选。用户问"有哪些活动""某天有什么活动"时调用。产出 programId。"""
    params = {}
    if keyword:
        params["keyword"] = keyword
    if category:
        params["category"] = category
    if stadium_id:
        params["stadiumId"] = stadium_id
    if date:
        params["date"] = date
    return api_get_path("/show/program/list.xhtml", token_from_config(config), params)

@tool
def ticketing_program_detail(config: Any, program_id: str) -> dict:
    """查询活动项目详情（场馆、须知、介绍等）。program_id 来自 ticketing_list_programs，必填。"""
    if not program_id:
        return _need("program_id")
    params = {}
    if program_id:
        params["programId"] = program_id
    return api_get_path("/show/program/getById.xhtml", token_from_config(config), params)

@tool
def ticketing_program_categories(config: Any) -> dict:
    """查询活动项目分类。用户问"有哪些活动分类"时调用。"""
    params = {}
    return api_get_path("/ticket/program/getProgramCategoryList.xhtml", token_from_config(config), params)

@tool
def ticketing_program_init(config: Any, date: str = '') -> dict:
    """读取活动初始化/场地与活动日期信息。可用于场馆筛选及活动日历。date 可选。"""
    params = {}
    if date:
        params["date"] = date
    return api_get_path("/program/showProgramInit.xhtml", token_from_config(config), params)

@tool
def ticketing_show_dates(config: Any, program_id: str) -> dict:
    """查询活动项目有场次的日期。用户问"活动哪天有场次"时调用。program_id 必填。"""
    if not program_id:
        return _need("program_id")
    params = {}
    if program_id:
        params["programId"] = program_id
    return api_get_path("/member/show/date.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_show_schedules(config: Any, program_id: str) -> dict:
    """查询活动项目场次。用户问"有哪些场次可选"时调用。program_id 必填；产出 showId。"""
    if not program_id:
        return _need("program_id")
    params = {}
    if program_id:
        params["programId"] = program_id
    return api_get_path("/member/show/list.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_ticket_types(config: Any, program_id: str, show_id: str) -> dict:
    """查询活动场次票种与票价。用户问"这场有哪些票种"时调用。
    program_id 来自 ticketing_list_programs，show_id 来自 ticketing_show_schedules，均必填、不能臆造。"""
    if not program_id:
        return _need("program_id")
    if not show_id:
        return _need("show_id")
    params = {}
    if program_id:
        params["programId"] = program_id
    if show_id:
        params["showId"] = show_id
    return api_get_path("/member/show/getShowTicketTypes.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_schedules_by_date(config: Any, program_id: str, date: str) -> dict:
    """按日期查询活动场次。用户问"这一天有什么场次"时调用。program_id、date 必填。"""
    if not program_id:
        return _need("program_id")
    if not date:
        return _need("date")
    params = {}
    if program_id:
        params["programId"] = program_id
    if date:
        params["date"] = date
    return api_get_path("/member/show/listBydate.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_list_show_orders(config: Any, status: str = '', page_no: int = 1, page_size: int = 10) -> dict:
    """查询（非选座）活动票务订单列表。用户问"我有哪些票务订单"时调用。status：new/paid_success。产出 tradeNo。"""
    params = {}
    if status:
        params["status"] = status
    if page_no:
        params["pageNo"] = page_no
    if page_size:
        params["pageSize"] = page_size
    return api_get_path("/member/order/getShowOrderList.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_valid_tickets(config: Any) -> dict:
    """查询会员有效活动票。用户问"我有哪些可用门票"时调用。"""
    params = {}
    return api_get_path("/member/order/getValidShowTicketList.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_list_seat_orders(config: Any, status: str = '') -> dict:
    """查询选座票订单列表。用户问"我有哪些选座票订单"时调用。status：空=全部/paid/new。产出 tradeNo。"""
    params = {}
    if status:
        params["status"] = status
    return api_get_path("/member/ticket/order/list.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_seat_order_detail(config: Any, trade_no: str) -> dict:
    """查询选座票订单详情与支付状态。trade_no 来自 ticketing_list_seat_orders，必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/ticket/order/detail.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_order_extra(config: Any, trade_no: str) -> dict:
    """查询订单扩展信息与配送状态（入参格式待确认）。trade_no 来自票务订单，必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/getOrderExtraByTradeNo.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_seat_discounts(config: Any, trade_no: str) -> dict:
    """查询选座票订单可用/已用优惠。trade_no（选座票订单号）必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/ticket/discount/getDiscountRepo.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_show_discounts(config: Any, trade_no: str) -> dict:
    """查询非选座活动票订单优惠。trade_no（活动订单号）必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/show/discount/getDiscountRepo.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_invoice_list(config: Any, trade_no: str) -> dict:
    """查询票务订单发票列表。trade_no 必填；产出 invoiceNo/serialNo 供下载 PDF。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/show/order/getInvoiceList.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_invoice_pdf(config: Any, serial_no: str, trade_no: str) -> dict:
    """查询发票 PDF 地址。serial_no（发票序号）与 trade_no（发票记录 orderNo）来自 ticketing_invoice_list，均必填。"""
    if not serial_no:
        return _need("serial_no")
    if not trade_no:
        return _need("trade_no")
    params = {}
    if serial_no:
        params["serialNo"] = serial_no
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/show/order/getInvoicePdfUrl.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_invoice_by_out_no(config: Any, out_trade_no: str) -> dict:
    """按外部订单号查询线下发票信息。out_trade_no 由用户/外部提供，必填。"""
    if not out_trade_no:
        return _need("out_trade_no")
    params = {}
    if out_trade_no:
        params["outTradeNo"] = out_trade_no
    return api_get_path("/member/show/order/getInvoiceByOutNo.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_invoice_titles(config: Any) -> dict:
    """查询已保存的发票抬头。用户问"我保存了哪些抬头"时调用。"""
    params = {}
    return api_get_path("/member/invoicetitle/getList.xhtml", token_from_config(config), params, require_session=True)

@tool
def ticketing_stadiums(config: Any) -> dict:
    """查询场馆列表。用户问"有哪些场馆"时调用。产出 stadiumId。"""
    params = {}
    return api_get_path("/getStadiums.xhtml", token_from_config(config), params)

@tool
def ticketing_stadium_detail(config: Any, stadium_id: str) -> dict:
    """查询场馆信息（含经纬度），用于活动位置校验。stadium_id 来自 ticketing_stadiums，必填。"""
    if not stadium_id:
        return _need("stadium_id")
    params = {}
    if stadium_id:
        params["stadiumId"] = stadium_id
    return api_get_path("/stadium/getById.xhtml", token_from_config(config), params)
