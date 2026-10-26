"""路由前的输入归一化：把高频词的拼音、错拼、中英混写收敛到标准中文词。

确定性直达路由依赖中文关键词精确匹配，纯拼音或中英混写（如“导lan tu”“dao lan che”）
会绕过全部路由、落到大模型自由发挥。这里用「高频词别名表」做实用覆盖（约 80% 场景），
不引入 pypinyin 等重依赖：命中已知变体即替换为标准词，未命中的输入保持原样、行为不变。

is_multi_intent：含分隔符且命中 >=2 个领域组时判为多意图（多意图不走确定性直达）。

说明：本文件由编译产物重建，三张表字节级还原，两个函数经随机对拍与原实现一致。
"""

_ALIASES = {'导览图': ['导览地图', 'daolantu', 'dao lan tu', '导lantu', '导lan tu', '导览tu', '导览map'], '导览车': ['daolanche', 'dao lan che', '导lanche', '导lan che', '导lan车', '接驳车', '接驳巴士', '西岸巴士'], '停车缴费': ['tingchejiaofei', 'ting che jiao fei'], '停车场': ['tingchechang', '停车chang', 'parking'], '停车': ['tingche', 'ting che'], '缴费': ['jiaofei', 'jiao fei'], '卫生间': ['weishengjian', 'wei sheng jian', '洗手间', '厕所', 'toilet'], '客服中心': ['kefuzhongxin', 'kefu', 'ke fu', '客服'], '会员': ['huiyuan', 'hui yuan'], '积分': ['jifen', 'ji fen'], '优惠券': ['youhuiquan', 'you hui quan', 'coupon'], '活动': ['huodong', 'huo dong'], '充电': ['chongdian', 'chong dian', 'charging'], '宠物': ['chongwu', 'chong wu'], '商户': ['shanghu', 'shang hu']}

_RULES = [('ting che jiao fei', '停车缴费'), ('tingchejiaofei', '停车缴费'), ('wei sheng jian', '卫生间'), ('tingchechang', '停车场'), ('weishengjian', '卫生间'), ('kefuzhongxin', '客服中心'), ('you hui quan', '优惠券'), ('dao lan che', '导览车'), ('dao lan tu', '导览图'), ('youhuiquan', '优惠券'), ('chong dian', '充电'), ('daolanche', '导览车'), ('chongdian', '充电'), ('daolantu', '导览图'), ('导lan che', '导览车'), ('ting che', '停车'), ('jiao fei', '缴费'), ('hui yuan', '会员'), ('huo dong', '活动'), ('charging', '充电'), ('chong wu', '宠物'), ('shang hu', '商户'), ('导lan tu', '导览图'), ('导lanche', '导览车'), ('停车chang', '停车场'), ('parking', '停车场'), ('tingche', '停车'), ('jiaofei', '缴费'), ('huiyuan', '会员'), ('huodong', '活动'), ('chongwu', '宠物'), ('shanghu', '商户'), ('导lantu', '导览图'), ('toilet', '卫生间'), ('ji fen', '积分'), ('coupon', '优惠券'), ('导览map', '导览图'), ('导lan车', '导览车'), ('ke fu', '客服中心'), ('jifen', '积分'), ('导览地图', '导览图'), ('导览tu', '导览图'), ('接驳巴士', '导览车'), ('西岸巴士', '导览车'), ('kefu', '客服中心'), ('接驳车', '导览车'), ('洗手间', '卫生间'), ('厕所', '卫生间'), ('客服', '客服中心')]

_DOMAIN_GROUPS = {'停车': ('停车', '车位', '车场', '停车费', '缴费', '车牌'), '会员': ('会员', '等级', '成长值', '升级', '保级'), '积分': ('积分',), '优惠券': ('优惠券',), '活动': ('活动', '演出', '展览', '快闪', '门票', '票务'), '商户': ('商户', '商家', '店铺', '美食', '餐饮', '咖啡'), '设施': ('卫生间', '洗手间', '厕所', '客服', '母婴', '充电', '轮椅', '寄存', '淋浴'), '交通': ('导览车', '接驳', '地铁', '公交', '打车', '自驾', '导航'), '规则': ('宠物', '运动友好', '租赁', '押金')}

_SEPARATORS = "，,；;、/"


def normalize_query(message: str) -> str:
    text = message.lower()
    for variant, standard in _RULES:
        if variant in text:
            text = text.replace(variant, standard)
    return text


def is_multi_intent(message: str) -> bool:
    q = message
    has_separator = any(sep in q for sep in _SEPARATORS)
    if not has_separator:
        return False
    hit_groups = {
        name
        for name, words in _DOMAIN_GROUPS.items()
        if any(w in q for w in words)
    }
    return len(hit_groups) >= 2
