"""会员信息（integrations/member_api.py）。mock HTTP 覆盖各返回分支。"""
import pytest
from real_agent.app.integrations import member_api as ma


class R:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def json(self): return self._p
    def raise_for_status(self): pass


def _mock(monkeypatch, payload):
    monkeypatch.setattr(ma.httpx, "post", lambda url, **k: R(payload), raising=False)


def test_missing_session():
    out = ma.fetch_current_member("")
    assert out["found"] is False and out["reason"] == "missing_session"

def test_found_and_safe_member(monkeypatch):
    _mock(monkeypatch, {"data": {"memberLevelName": "钻石", "point": 1200,
                                 "endTime": "2026-12-31", "mobile": "13800138000"}})
    out = ma.fetch_current_member("SESS_FOUND")
    assert out["found"] is True
    m = out["member"]
    assert m["member_level_name"] == "钻石" and m["points"] == 1200
    assert m["membership_end_time"] == "2026-12-31" and m["mobile"] == "13800138000"

def test_invalid_session_no_data(monkeypatch):
    _mock(monkeypatch, {"resultData": {"x": 1}})         # 无 data 段
    out = ma.fetch_current_member("SESS_INVALID")
    assert out["reason"] == "invalid_or_expired_session"

def test_empty_member(monkeypatch):
    _mock(monkeypatch, {"data": {}})
    out = ma.fetch_current_member("SESS_EMPTY")
    assert out["reason"] == "empty_member"

def test_clean_mobile():
    assert ma._clean_mobile("  13800138000  ") == "13800138000"
    assert ma._clean_mobile("") is None
    assert ma._clean_mobile(0) is None
