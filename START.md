# 小梦（real_agent）重建版 · 启动说明

本目录是对编译产物（Cython `.so`）的**可读重建**，用于读懂逻辑与二次开发。58 个模块已全部重建，
`real_agent.app.main` / `real_agent.app.agent.graph` 可干净 import。

> 保真度分层见 `REBUILD_NOTES.md`：确定性模块（路由/理解门控/渲染/后处理/异常话术/行动卡/
> 各 should_route 判定/格式化）为**字节级对拍**；网络/LLM/数据耦合模块（integrations/tools/
> planner/recommender/db/live_\* 直达）为**忠实可读**、委托已重建层。

---

## 1. 环境

- Python **3.12**（与 .so 的 ABI 一致；用其它小版本跑纯 .py 重建也行，但别混用 .so）
- 建议用虚拟环境：

```bash
cd real_agent_rebuild_NEW
python3.12 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

RAG 向量检索是可选的：`requirements.txt` 里 `sentence-transformers / pymilvus / numpy` 默认注释掉，
不装则知识库召回返回空，不影响路由/取数/成稿主链路。需要时取消注释再装。

## 2. 配置

```bash
cp .env.example .env
# 编辑 .env，至少填一个大模型 key：
#   REAL_DEEPSEEK_API_KEY=sk-xxx     （DeepSeek V4，默认模型）
#   或 REAL_OPENAI_API_KEY=...        （Kimi / OpenAI 兼容）
```

所有变量以 `REAL_` 前缀，`config.py` 启动时用 python-dotenv 自动加载 `.env`。
地图 key 不填则 `/config` 返回 `map_enabled=false`，不影响对话。

## 3. 冒烟自检（不连大模型也能过）

```bash
# 确认整树能 import（确定性链路已可跑）
PYTHONPATH=. python -c "import real_agent.app.main; print('import OK')"

# 后处理链真跑一遍（口癖净化 + 行动卡）
PYTHONPATH=. python -c "
from real_agent.app.agent.graph import _postprocess, exception_reply
print(_postprocess('根据截图可知，停车费30元。','有哪些停车场',['parking']))
print(exception_reply('unclear_intent'))
"
```

## 4. 启动服务

```bash
# 开发（热重载）
PYTHONPATH=. uvicorn real_agent.app.main:app --reload --host 0.0.0.0 --port 8000

# 生产（多 worker）
PYTHONPATH=. uvicorn real_agent.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

起来后：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET  | `/health` | 健康检查 |
| GET  | `/config` `/models` `/home-data` | 前端启动拉取 |
| POST | `/chat` | 一问一答，body = `{"message":"...","session_id":"...","mpsessid":"...","model":"deepseek-v4-flash"}` |
| POST | `/chat/stream` | 流式 SSE（前端步骤条 + 成稿） |
| GET  | `/admin` + `/admin/api/*` | 运营后台 |

快速验证（需已配 key）：
```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"有哪些停车场","session_id":"t1"}'
```

## 5. 命令行调试（不走 HTTP）

```bash
PYTHONPATH=. python -m real_agent.app.cli
# 进入交互 REPL，直接输入问题
```

## 6. 需要的运行期数据（随部署下发，不在本重建包内）

以下目录/文件缺失时相关功能安全降级（返回空/未命中），不影响 import 与主链路：

- `real_agent/data/tools/capabilities.json` 与 `tools/capabilities/*.json` —— 能力注册表（直达路由用）
- `real_agent/data/tools/apis/tools_catalog.json`、`real_agent/API.md` —— 只读接口目录/白名单
- `real_agent/data/rag/{images,app_images}/` —— 图片资源
- `real_agent/data/milvus.db` + BGE 模型 —— RAG 向量检索
- `real_agent/web/` —— 前端静态页（`/` 与 `/admin` 挂载）

## 7. 常见问题

- **ImportError: langgraph / langchain_openai** —— 只在真正调用大模型那一跳才需要；`import main` 本身不需要（都是惰性 import）。装上 requirements 即可。
- **对话总是走 ReAct、直达不生效** —— 缺 `capabilities.json` 等注册表数据，补上即可。
- **想换模型** —— 请求里带 `"model"`：`kimi-k3` / `kimi-k2.6` / `deepseek-v4-pro` / `deepseek-v4-flash`。
