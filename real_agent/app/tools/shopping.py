"""商城购物域只读工具（shopping）。

子域：商品(§7，积分/文创/租赁) / 订单物流(§8/§10) / 地址地区(§8/§9) + 优惠横切。
依赖链：productTypeCode→商品列表→productId→详情/自提/购买资格；订单 tradeNo→详情/
物流/优惠；省→市→区级联；memberAddressId→运费。ID 必须来自上游返回，不能臆造。

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
def shopping_point_product_types(config: Any) -> dict:
    """查询积分商品分类。用户问"有哪些积分商品分类"时调用。产出 productTypeCode。"""
    params = {}
    return api_get_path("/mall/getPointProductTypeList.xhtml", token_from_config(config), params)

@tool
def shopping_point_products(config: Any, product_type_code: str = '') -> dict:
    """按分类查询积分商品。用户问"积分能兑换什么"时调用。产出 pointProductId。"""
    params = {}
    if product_type_code:
        params["productTypeCode"] = product_type_code
    return api_get_path("/mall/getPointProducts.xhtml", token_from_config(config), params)

@tool
def shopping_point_product_detail(config: Any, point_product_id: str) -> dict:
    """查询积分商品详情。point_product_id 来自 shopping_point_products，必填。"""
    if not point_product_id:
        return _need("point_product_id")
    params = {}
    if point_product_id:
        params["pointProductId"] = point_product_id
    return api_get_path("/mall/getPointProductDetail.xhtml", token_from_config(config), params)

@tool
def shopping_point_delivery_addresses(config: Any, point_product_id: str) -> dict:
    """查询积分商品自提地址。用户问"兑换商品在哪领取"时调用。point_product_id 必填。"""
    if not point_product_id:
        return _need("point_product_id")
    params = {}
    if point_product_id:
        params["pointProductId"] = point_product_id
    return api_get_path("/mall/getPointDeliveryAddresses.xhtml", token_from_config(config), params)

@tool
def shopping_point_can_buy(config: Any, product_id: str) -> dict:
    """校验积分商品兑换资格。用户问"我能兑换这个吗"时调用。product_id = 积分商品ID，必填。"""
    if not product_id:
        return _need("product_id")
    params = {}
    if product_id:
        params["productId"] = product_id
    return api_get_path("/member/mall/isAllowBuyMallpoint.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_cultural_product_types(config: Any) -> dict:
    """查询文创商品分类。用户问"商城有哪些商品分类"时调用。"""
    params = {}
    return api_get_path("/mall/getCulturalProductTypeList.xhtml", token_from_config(config), params)

@tool
def shopping_cultural_products(config: Any, product_type_code: str = '', product_name: str = '', agency_id: str = '') -> dict:
    """查询文创商品列表。用户问"某类商品有哪些""这家店有哪些商品"时调用。产出 culturalProductId。"""
    params = {}
    if product_type_code:
        params["productTypeCode"] = product_type_code
    if product_name:
        params["productName"] = product_name
    if agency_id:
        params["agencyId"] = agency_id
    return api_get_path("/mall/getCulturalProducts.xhtml", token_from_config(config), params)

@tool
def shopping_cultural_product_detail(config: Any, cultural_product_id: str) -> dict:
    """查询文创商品详情与规格。cultural_product_id 来自 shopping_cultural_products，必填。"""
    if not cultural_product_id:
        return _need("cultural_product_id")
    params = {}
    if cultural_product_id:
        params["culturalProductId"] = cultural_product_id
    return api_get_path("/mall/getCulturalProductDetail.xhtml", token_from_config(config), params)

@tool
def shopping_cultural_delivery_addresses(config: Any, cultural_product_id: str) -> dict:
    """查询文创商品自提地址。用户问"商品在哪自提"时调用。cultural_product_id 必填。"""
    if not cultural_product_id:
        return _need("cultural_product_id")
    params = {}
    if cultural_product_id:
        params["culturalProductId"] = cultural_product_id
    return api_get_path("/mall/getCulturalDeliveryAddresses.xhtml", token_from_config(config), params)

@tool
def shopping_cultural_can_buy(config: Any, product_id: str) -> dict:
    """校验文创商品购买资格。product_id = 文创商品ID，必填。"""
    if not product_id:
        return _need("product_id")
    params = {}
    if product_id:
        params["productId"] = product_id
    return api_get_path("/member/mall/isAllowBuyMallcultural.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_rent_products(config: Any) -> dict:
    """查询可租赁商品。用户问"有哪些可以租的物品"时调用。产出 rentProductCode/rentProductId。"""
    params = {}
    return api_get_path("/mall/rent/getProducts.xhtml", token_from_config(config), params)

@tool
def shopping_rent_product_detail(config: Any, rent_product_code: str) -> dict:
    """查询租赁商品详情。rent_product_code 来自 shopping_rent_products，必填。"""
    if not rent_product_code:
        return _need("rent_product_code")
    params = {}
    if rent_product_code:
        params["rentProductCode"] = rent_product_code
    return api_get_path("/mall/rent/getProductDetail.xhtml", token_from_config(config), params)

@tool
def shopping_rent_delivery_addresses(config: Any, rent_product_id: str) -> dict:
    """查询租赁商品领取地址。用户问"租赁物品在哪取"时调用。rent_product_id 必填。"""
    if not rent_product_id:
        return _need("rent_product_id")
    params = {}
    if rent_product_id:
        params["rentProductId"] = rent_product_id
    return api_get_path("/mall/rent/getDeliveryAddresses.xhtml", token_from_config(config), params)

@tool
def shopping_rent_orders(config: Any, page_no: int = 1, page_size: int = 10) -> dict:
    """查询租赁订单列表。用户问"我有哪些租赁订单"时调用。产出 tradeNo（租赁）。"""
    params = {}
    if page_no:
        params["pageNo"] = page_no
    if page_size:
        params["pageSize"] = page_size
    return api_get_path("/member/mall/rent/orderList.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_rent_order_detail(config: Any, trade_no: str) -> dict:
    """查询租赁订单详情。trade_no 来自 shopping_rent_orders（租赁订单号），必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/mall/rent/orderDetail.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_order_list(config: Any, order_type: str = '', page_no: int = 1, page_size: int = 10) -> dict:
    """查询商城/券订单列表。用户问"我有哪些商城订单"时调用。order_type：mallcultural/mallPoint。产出 tradeNo（商城）。"""
    params = {}
    if order_type:
        params["orderType"] = order_type
    if page_no:
        params["pageNo"] = page_no
    if page_size:
        params["pageSize"] = page_size
    return api_get_path("/member/coupon/memberOrderList.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_order_detail(config: Any, trade_no: str) -> dict:
    """查询商城/券订单详情。trade_no 来自 shopping_order_list（商城订单号），必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/coupon/orderDetail.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_ems(config: Any, trade_no: str) -> dict:
    """查询订单物流信息。用户问"我的快递到哪了"时调用。trade_no（商城订单号）必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/ems/getEmsInfoByTradeNo.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_mall_discounts(config: Any, trade_no: str) -> dict:
    """查询文创商城订单可用/已用优惠。trade_no（商城订单号）必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/mall/cultural/discount/getDiscountRepo.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_point_discounts(config: Any, trade_no: str) -> dict:
    """查询积分商城订单优惠。trade_no（积分订单号）必填。"""
    if not trade_no:
        return _need("trade_no")
    params = {}
    if trade_no:
        params["tradeNo"] = trade_no
    return api_get_path("/member/mall/point/discount/getDiscountRepo.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_addresses(config: Any) -> dict:
    """查询会员收货地址。用户问"我保存了哪些地址"时调用。产出 memberAddressId。"""
    params = {}
    return api_get_path("/member/address/getMemberAddressList.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_address_detail(config: Any, address_id: str) -> dict:
    """查询指定收货地址详情。address_id（memberAddressId）来自 shopping_addresses，必填。"""
    if not address_id:
        return _need("address_id")
    params = {}
    if address_id:
        params["addressId"] = address_id
    return api_get_path("/member/address/getMemberAddressById.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_freight_common(config: Any, member_address_id: str) -> dict:
    """查询运费（通用）。用户问"配送到该地址多少运费"时调用。member_address_id 来自 shopping_addresses，必填。"""
    if not member_address_id:
        return _need("member_address_id")
    params = {}
    if member_address_id:
        params["memberAddressId"] = member_address_id
    return api_get_path("/member/common/getFreightByArea.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_freight_mall(config: Any, member_address_id: str, trade_no: str = '', amount: str = '') -> dict:
    """查询商城订单运费。member_address_id 必填；trade_no/amount 为订单号与金额。"""
    if not member_address_id:
        return _need("member_address_id")
    params = {}
    if member_address_id:
        params["memberAddressId"] = member_address_id
    if trade_no:
        params["tradeNo"] = trade_no
    if amount:
        params["amount"] = amount
    return api_get_path("/member/mall/getFreightByArea.xhtml", token_from_config(config), params, require_session=True)

@tool
def shopping_provinces(config: Any) -> dict:
    """查询省份列表（填地址用）。产出 provinceCode。"""
    params = {}
    return api_get_path("/theatre/common/getProvinceAllList.xhtml", token_from_config(config), params)

@tool
def shopping_cities(config: Any, province_code: str) -> dict:
    """按省份查询城市列表。province_code 来自 shopping_provinces，必填。产出 cityCode。"""
    if not province_code:
        return _need("province_code")
    params = {}
    if province_code:
        params["provinceCode"] = province_code
    return api_get_path("/theatre/common/getCityList.xhtml", token_from_config(config), params)

@tool
def shopping_counties(config: Any, city_code: str) -> dict:
    """按城市查询区县列表。city_code 来自 shopping_cities，必填。"""
    if not city_code:
        return _need("city_code")
    params = {}
    if city_code:
        params["cityCode"] = city_code
    return api_get_path("/theatre/common/getCountyList.xhtml", token_from_config(config), params)
