"""商户场馆导览域只读工具（merchant_venue，§13/§14）。

商户列表/分类/导览点复用既有 miniprogram 工具（含餐饮品类过滤等逻辑）；此处补充
商户详情与导览点。场馆查询见 ticketing_stadiums / ticketing_stadium_detail。
agencyId 来自商户列表，必填、不能臆造。

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
def merchant_detail(config: Any, agency_id: str) -> dict:
    """查询商户详情（名称/地址/营业时间/标签）。用户问"这家店的介绍/在哪/几点营业"时调用。
    agency_id 来自商户列表（search_miniprogram_merchants 等），必填。"""
    if not agency_id:
        return _need("agency_id")
    params = {}
    if agency_id:
        params["agencyId"] = agency_id
    return api_get_path("/agency/getAgencyVo.xhtml", token_from_config(config), params)

@tool
def merchant_guide_points(config: Any, guide_map_id: str) -> dict:
    """查询导览地图中有关联商户的导览点。用户问"可按哪些位置查店"时调用。guide_map_id 必填。"""
    if not guide_map_id:
        return _need("guide_map_id")
    params = {}
    if guide_map_id:
        params["guideMapId"] = guide_map_id
    return api_get_path("/guide/getHaseAgenceGuidePointPageList.xhtml", token_from_config(config), params)
