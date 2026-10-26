# 单元测试说明

按「层」组织的 pytest 测试，覆盖各场景。打 ✅ 的层**不需要 key/网络**，直接跑；
取数层（api_gateway/member_api）用 `monkeypatch` 把 HTTP 替成假响应，也不碰网络。

## 跑法

```bash
cd real_agent_rebuild_NEW
source .venv/bin/activate          # 见 START.md
pip install pytest                 # 只需这一次

# 全部
pytest

# 单个文件 / 单个用例
pytest tests/test_renderer.py
pytest tests/test_member_api.py::test_empty_member -v

# 看每条用例名
pytest -v
```

> `pytest.ini` 已配好 `testpaths=tests`。项目根已在 `sys.path`（见 `tests/conftest.py`），
> 所以 `import real_agent.app.*` 直接可用，不用设 PYTHONPATH。

## 各文件覆盖什么

| 文件 | 层 | 依赖 |
| --- | --- | --- |
| `test_router_l1.py` | L1 关键词路由 deterministic_intents | ✅ 纯逻辑 |
| `test_understanding.py` | 门控 should_route_direct | ✅ 纯逻辑 |
| `test_renderer.py` | payload→成稿 render | ✅ 纯逻辑 |
| `test_response_formatter.py` | 活动卡/商户卡（含溢出、省略、上限） | ✅ 纯逻辑 |
| `test_postprocess.py` | 净化 + 行动卡 + 异常话术 | ✅ 纯逻辑 |
| `test_routing_predicates.py` | 运动适宜性 / 停车路由判定 | ✅ 纯逻辑 |
| `test_table_format.py` | Markdown 表格 | ✅ 纯逻辑 |
| `test_api_gateway.py` | 接口网关（归一化 + 白名单 + 调用） | mock HTTP |
| `test_member_api.py` | 会员信息各返回分支 | mock HTTP |

## 想加自己的场景

照 `test_renderer.py` 的样子，`import` 对应模块的函数，`assert 函数(输入)==期望`。
取数类参照 `test_member_api.py` 的 `monkeypatch.setattr(模块.httpx, "post", 假函数)`。
这些断言的期望值全部来自对编译产物（.so）的字节级对拍，可当"黄金基线"。

> 说明：涉及大模型的 `graph.chat()` 整体端到端没放进 UT（需 key + 网络 + 数据文件），
> 它属于集成测试。确定性那几层的 UT 已能覆盖全部可对拍逻辑。
