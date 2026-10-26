"""接口网关（integrations/api_gateway.py）。纯逻辑 + mock HTTP。"""
import pytest
from real_agent.app.integrations import api_gateway as gw


@pytest.mark.parametrize("addr,expected", [
    ("/thvendor/member/info/get.xhtml", "/member/info/get.xhtml"),  # 剥服务前缀
    ("/a/b.xhtml", "/a/b.xhtml"),
    ("/a/b.json", None),                                            # 非 .xhtml
    ("https://h/thvendor/a/b.xhtml", "/a/b.xhtml"),                 # 带 scheme + 前缀
    ("http://h/a.xhtml", None),                                     # scheme 但无服务前缀
    ("q.xhtml", None),                                              # 不以 / 开头
])
def test_norm_md_path(addr, expected):
    assert gw._norm_md_path(addr) == expected


def test_is_allowed_and_call(monkeypatch):
    # 注入一个目录项 + mock httpx.get
    gw._CATALOG.clear()
    gw._CATALOG["/m/x.xhtml"] = {"path": "/m/x.xhtml", "summary": "", "tag": "",
                                 "description": "", "params": [{"name": "q", "required": True}]}
    assert gw.is_allowed("/m/x.xhtml") is True
    assert gw.is_allowed("/thvendor/m/x.xhtml") is False     # 未归一化不放行

    class R:
        status_code = 200
        def json(self): return {"data": {"ok": 1}}
        def raise_for_status(self): pass
    captured = {}
    def fake_get(url, **k):
        captured["url"] = url; captured["params"] = k.get("params")
        return R()
    monkeypatch.setattr(gw.httpx, "get", fake_get, raising=False)

    # 缺必填 q → need_params
    assert gw.call_readonly_api("/m/x.xhtml", {}, "S")["reason"] == "need_params"
    # 带上 q → 成功，且调用方 junk 被过滤、appId 附上
    out = gw.call_readonly_api("/m/x.xhtml", {"q": "KW", "junk": 1}, "S")
    assert out["found"] is True and out["data"] == {"ok": 1}
    assert captured["params"] == {"q": "KW", "appId": "wxd275b0214ea13dc8"}
    assert captured["url"].endswith("/thvendor/m/x.xhtml")
