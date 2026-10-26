"""顾客成稿净化（新版 / real_agent）。

大模型/工具链产出的草稿里常带「信息来源」口癖（"根据截图可知…"、"依据知识库显示…"），
对顾客没意义还显得机械。本模块把这些来源前缀抹掉，让成稿直接讲结论。

重建说明：本文件由新版编译产物（agent/customer_reply.*.so）重建。
- UNKNOWN_REPLY、5 条 _SOURCE_PREFIXES 正则字节级还原；
- sanitize_customer_reply 经随机对拍与原 .so 一致（全局 sub 去前缀 + 两端 strip）。
"""

import re

UNKNOWN_REPLY = "当前小梦还没有收录相关的信息哦~"

# 需要从成稿里抹掉的「信息来源」前缀（全局匹配，连同其后的标点/空白一并去掉）
_SOURCE_PREFIXES = (
    re.compile(r"(?:根据|依据|从)(?:现有|真实|官方)?(?:截图|图片|资料)(?:可知|显示|可确认)?[，,:：\s]*"),
    re.compile(r"(?:根据|依据|从)[^，,:：\n]{0,50}(?:知识库|工具|接口|系统记录)[^，,:：\n]{0,20}[，,:：\s]+"),
    re.compile(r"(?:现有|真实|官方)?截图(?:中)?(?:显示|可确认|明确)(?:的是)?[，,:：\s]*"),
    re.compile(r"(?:现有|真实|官方)?图中(?:可见|显示|标有|标注|可确认)?[，,:：\s]*"),
    re.compile(r"(?:会员手册|小程序页面|官方公告)(?:中)?(?:列出|显示|写明|明确)(?:的|的是)?[，,:：\s]*"),
)


def sanitize_customer_reply(reply: str) -> str:
    """抹掉成稿里的来源口癖前缀，并去掉首尾空白。"""
    text = reply or ""
    for pat in _SOURCE_PREFIXES:
        text = pat.sub("", text)
    return text.strip()
