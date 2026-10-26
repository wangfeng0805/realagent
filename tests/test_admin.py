"""/admin 后台接口测试（依据线上 http://47.116.7.1/admin 实测对齐）。

跑法： pytest tests/test_admin.py -v
断言各接口的响应结构/键名/数据计数，与线上一致。渲染/写入细节绑定部署目录，不在此断言。
"""
from real_agent.app import admin as A


def test_docs_items_shape():
    r = A.list_docs()
    assert "items" in r
    for it in r["items"]:
        assert set(("name", "size", "mtime")) <= set(it)


def test_data_lists_14_domains_with_counts():
    names = [i["name"] for i in A.list_data()["items"]]
    assert names == ["attractions", "events", "malls", "members", "parking", "pois",
                     "products", "realtime", "routes", "stores", "ticket_sessions",
                     "transactions", "transport", "user_behavior"]
    counts = {i["name"]: i["count"] for i in A.list_data()["items"]}
    assert counts["parking"] == 6 and counts["realtime"] == 5 and counts["transport"] == 1


def test_data_count_is_toplevel_len():
    assert A._data_count({"a": 1, "b": 2}) == 2
    assert A._data_count([1, 2, 3]) == 3
    assert A._data_count(None) == 0


def test_get_data_content_or_absent():
    d = A.get_data("parking")
    assert set(d.keys()) == {"name", "content"} and d["content"].strip().startswith("{")


def test_logs_shape():
    r = A.get_logs()
    assert set(r.keys()) == {"items", "total"} and isinstance(r["items"], list)


def test_list_envelopes_use_items():
    for r in (A.list_docs(), A.list_data(), A.list_images(), A.list_tools()):
        assert "items" in r
