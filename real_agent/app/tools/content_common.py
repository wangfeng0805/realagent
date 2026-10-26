"""内容通用域只读工具（content_common，§15/§16/§17）。

公告规则/动态表单/服务器时间/支付方式。技术辅助接口（验证码/二维码/上传凭据）不作
为业务工具暴露，必要时由 call_api 调用。token/appId 由通道注入。

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
def content_announcements(config: Any, adflag: str) -> dict:
    """按内容标识查询公告/图文/规则配置。adflag 为内容标识（可逗号分隔多个），必填。
    返回内容可能涉及活动、停车、积分规则，回答须以内容中的有效说明为准。"""
    if not adflag:
        return _need("adflag")
    params = {}
    if adflag:
        params["adflag"] = adflag
    return api_get_path("/ad/getNewAdList.xhtml", token_from_config(config), params)

@tool
def content_announcement_detail(config: Any, ad_id: str) -> dict:
    """查询指定图文内容详情（公告/规则/说明）。ad_id 来自 content_announcements，必填。"""
    if not ad_id:
        return _need("ad_id")
    params = {}
    if ad_id:
        params["adId"] = ad_id
    return api_get_path("/adinfo/getAdInfoById.xhtml", token_from_config(config), params)

@tool
def content_dynamic_program(config: Any, dynamic_program_id: str) -> dict:
    """查询无需登录的动态表单内容与配置。dynamic_program_id 由页面带入，必填。"""
    if not dynamic_program_id:
        return _need("dynamic_program_id")
    params = {}
    if dynamic_program_id:
        params["dynamicProgramId"] = dynamic_program_id
    return api_get_path("/dynamic/getDynamicProgram.xhtml", token_from_config(config), params)

@tool
def content_server_time(config: Any) -> dict:
    """读取服务器时间，用于时效/倒计时/过期判断。"""
    params = {}
    return api_get_path("/common/getServerTime.xhtml", token_from_config(config), params)

@tool
def content_payment_gateways(config: Any) -> dict:
    """查询支持的支付方式列表。用户问"支持哪些支付方式"时调用，以实时返回为准。"""
    params = {}
    return api_get_path("/member/getPaymentGatewayList.xhtml", token_from_config(config), params, require_session=True)
