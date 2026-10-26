"""预约域只读工具（reservation，§6）。

依赖链：reserveProgramId←reservation_search_programs → reservation_dates →
reservedate → reservation_periods；reserveNo←reservation_list_orders → 详情。
ID 必须来自上游返回，不能臆造；token/appId 由通道注入。

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
def reservation_program_types(config: Any) -> dict:
    """查询预约项目分类。用户问"有哪些预约项目类型"时调用。"""
    params = {}
    return api_get_path("/westbund/getReserveProgramTypes.xhtml", token_from_config(config), params)

@tool
def reservation_search_programs(config: Any, category: str = '') -> dict:
    """按分类搜索可预约项目。用户问"有哪些项目可以预约"时调用。category 可空；产出 reserveProgramId。"""
    params = {}
    if category:
        params["category"] = category
    return api_get_path("/reserve/getAvaiableReserveProgramsBySearch.xhtml", token_from_config(config), params)

@tool
def reservation_program_detail(config: Any, reserve_program_id: str) -> dict:
    """查询预约项目详情与须知。reserve_program_id 来自 reservation_search_programs，必填。"""
    if not reserve_program_id:
        return _need("reserve_program_id")
    params = {}
    if reserve_program_id:
        params["reserveProgramId"] = reserve_program_id
    return api_get_path("/member/reserve/getReserveProgram.xhtml", token_from_config(config), params, require_session=True)

@tool
def reservation_dates(config: Any, reserve_program_id: str) -> dict:
    """查询预约项目可预约日期。用户问"哪天可以预约"时调用。reserve_program_id 必填；产出 reservedate。"""
    if not reserve_program_id:
        return _need("reserve_program_id")
    params = {}
    if reserve_program_id:
        params["reserveProgramId"] = reserve_program_id
    return api_get_path("/member/reserve/getReserveDateList.xhtml", token_from_config(config), params, require_session=True)

@tool
def reservation_periods(config: Any, reserve_program_id: str, reserve_date: str) -> dict:
    """查询指定日期可预约时段。用户问"当天能约哪些时段"时调用。
    reserve_program_id、reserve_date 均必填，后者来自 reservation_dates。"""
    if not reserve_program_id:
        return _need("reserve_program_id")
    if not reserve_date:
        return _need("reserve_date")
    params = {}
    if reserve_program_id:
        params["reserveProgramId"] = reserve_program_id
    if reserve_date:
        params["reserveDate"] = reserve_date
    return api_get_path("/member/reserve/getReservePeriodList.xhtml", token_from_config(config), params, require_session=True)

@tool
def reservation_list_orders(config: Any, status: str = '', page_no: int = 1, page_size: int = 10) -> dict:
    """查询预约订单列表。用户问"我的预约有哪些"时调用。产出 reserveNo。"""
    params = {}
    if status:
        params["status"] = status
    if page_no:
        params["pageNo"] = page_no
    if page_size:
        params["pageSize"] = page_size
    return api_get_path("/member/reserve/getReserveOrderList.xhtml", token_from_config(config), params, require_session=True)

@tool
def reservation_order_detail(config: Any, reserve_no: str) -> dict:
    """查询预约订单详情（时段、预约人、凭证）。用户问"预约成功了吗""预约时间是什么"时调用。
    reserve_no 来自 reservation_list_orders，必填，不能臆造。"""
    if not reserve_no:
        return _need("reserve_no")
    params = {}
    if reserve_no:
        params["reserveNo"] = reserve_no
    return api_get_path("/member/reserve/getReserveOrderDetail.xhtml", token_from_config(config), params, require_session=True)
