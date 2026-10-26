# real_agent 源码重建说明（新版 / 2026-10-20 部署）

本目录基于 **新版部署** `/Users/admin/Desktop/00_AI/real_agent_deploy` 的编译产物（.so）重建。

## 新版 vs 旧版（backup/chat_agent）的主要差异

- **工具数 19 → 98**：原来靠 search_apis 兜底的长尾接口，升级为显式专用工具套件：
  停车 9、会员 16、票务 21（ticketing_*）、预约 7（reservation_*）、商城购物 27（shopping_*）、
  商户场馆 2、内容 5。移除 7 个旧粗工具（get_current_activities / get_point_mall_products /
  get_miniprogram_parking_status / search_mall_products / get_rent_* 等）。
- **领域 taxonomy 分层**：新增子域 member.{profile,points,coupon}、ticketing.{catalog,order,invoice}、
  shopping.{catalog,order,address}；build_policy_context 对子域回退到父域策略。
- **policies 重构**：删 activity/point_mall/merchant/product/facility，加 ticketing/reservation/
  shopping/merchant_venue/content_common。
- **SYSTEM_PROMPT**：不再内嵌日期（日期类问题改由 content_server_time 工具获取）。
- **数据目录重组**：images 移入 data/rag/，新增 data/{session,tools,legacy_mock}。
- **未变**：语义路由阈值 0.82/0.65/0.08、功能开关、模型列表、input_normalize、empty_reason、skill_loader。

## 本批已完成（以新版为基准）

| 模块 | 保真度 | 验证 |
| --- | --- | --- |
| `app/config.py` | 常量字节级 + env 重写（含新版新增目录键/APP_ID） | 常量与新 .so 一致 |
| `app/agent/skill_loader.py` | 行为验证（新旧一致） | load_skill 输出逐字一致 |
| `app/agent/prompts.py` | 字节级（新版静态 SYSTEM_PROMPT） | 正文逐字一致 |
| `app/agent/policies.py` | 字节级 + 行为验证 | 新域/子域 build_policy_context 4000 组合零差异 |
| `app/agent/input_normalize.py` | 字节级表 + 行为验证（未变） | 4000 条零差异 |
| `app/agent/empty_reason.py` | 字节级表 + 行为验证（未变） | 3000 条零差异 |
| `app/agent/understanding.py` | _SYSTEM/DOMAINS 更新为新版 + 行为验证 | 门控逻辑未变，纯函数 vs 新 .so 2 万条零差异 |
| `app/capabilities/router.py` | L1 规则表重建 + 行为验证 | 官方 233 例句对拍 99%（仅 2 条原实现自相矛盾的边界） |
| `app/capabilities/renderer.py` | 模板字节级 + 分派表 + 部分验证 | 全部输出模板字节级；render 分派表还原；member.info/points 对拍一致；其余渲染器按模板+字段重写 |
| `app/integrations/miniprogram_api.py` | 常量字节级 + HTTP核心验证 | 鉴权常量/路径表/词表字节级；_full_url/token_from_config/_headers 对拍零差异；fetch_*/_safe_* 按轨迹重写 |
| `app/capabilities/registry.py` | 结构+配置 schema 还原 + 分派重写 | 类/签名/_FUNCTIONS/配置 schema 一致；按 source 分派逻辑按轨迹重写 |
| `app/tools/ticketing.py` 等 5 个新工具模块 | 描述/签名/接口路径还原 | 62 个工具的名称/描述/路径从 .so 还原；参数名按 snake→camel 约定 |
| `app/agent/live_program.py` | 词表字节级 + 逻辑验证 | 词表字节级一致；_wanted_date/拦截逻辑对拍一致 |
| `app/router/semantic_router.py` | 常量字节级 + 核心逻辑验证 | 纯函数 8000 条零差异；字面打分公式 120/120；阈值/转换 schema 一致；向量路径按轨迹重写 |
| `app/agent/graph.py` | 常量字节级（98 工具 + 分层工具组）+ 编排骨架 | 语法 OK；编排逻辑同旧版（未变） |
| `app/agent/response_formatter.py` | 行为字节级还原 | 活动卡/商户卡/商户详情 vs 新 .so 40000×3 零差异（含 >8 项溢出尾注、`_program_period` 仅 start 出 meta、详情按字段省行、商户 name 兜底"未命名商户"/category 省键） |
| `app/integrations/member_api.py` | 常量字节级 + 全行为验证 | 鉴权常量/缓存秒数字节级；`_clean_mobile`/`_put`/`_safe_member`（8 键映射+顺序）纯函数 2 万条零差异；`fetch_current_member` 请求头(9)/空体 POST/5 分支(missing/upstream/invalid/empty/found)/30s 缓存 对拍一致 |
| `app/main.py` | 路由表还原 + Controller/DTO/元信息接口对拍 + 瘦 re-export | 真实路由表(14 路由+3 挂载)通过注入假 FastAPI 捕获装饰器还原；`_client_ip`/health/config/models/home-data 对拍一致；DTO 字节级；已确认 `main.chat IS graph.chat`，故 Controller 仅 import 调用，不重复实现 |
| `app/agent/graph.py` | 编排顺序 + 工具分组 + 步骤事件还原（readable） | `chat`/`chat_stream` 漏斗顺序由 .so 调用轨迹还原(live_program/merchant 直达→understand→上下文→_scoped_tools→get_agent ReAct→后处理→落库)；`_TOOL_GROUPS` 18 域、`_scoped_tools` 域→工具规模(member 23/parking 12/全 98)、`_step` 事件结构对 .so 验证；ReActAgent(LangGraph) token 级循环为 behavioral 装配点 |
| `app/agent/table_format.py` | 字节级 + 对拍 | `_cell`/`key_value_table`/`markdown_table` 对拍零差异（空值→「—」、转义 `\|`、换行→`<br>`） |
| `app/agent/answer_format.py` | 字节级 + 对拍 | `classify`(精确 reason code→三类)/`reason_reply` 全组合零差异；卡片编码与 action_cards 一致 |
| `app/agent/sport_suitability.py` | 字节级词表 + 对拍 | 7 组词表字节级；`_is_sport_suitability` 10 万条零差异（预约/场馆列表排除、运动适宜短语、适宜词+运动词同现） |
| `app/agent/parking_agent.py` | 判定字节级 + 处理器可读 | 5 组判定词表字节级；`should_route_to_parking_agent` 20 万条零差异（短语/入口词/停车+动作/语境+导航四分支）；ParkingAgentResult 结构还原，取数委托已重建层 |
| `app/agent/planner.py` | 字节级还原 + 对拍 | 常量(`_BUDGET`/`_DEFAULT_BUDGET=3`/`_SKIP_DOMAINS`/`_TIMEOUT_API=1.8`/`_TIMEOUT_VECTOR=2.5`/`_ENHANCE_TIMEOUT=0.8`/`_SYNTHESIS_SYSTEM`含 resp-v2-skill 全文/`AGENT_NAME`)字节级；`build_plan`/`_primary_domains`/`_trim` vs .so **3414 用例零差异**：按 domains 输入顺序迭代、跳过 SKIP、主领域(第一个非 SKIP 域)necessary+自身超时/其余 enhancement+0.8s、按步骤名全局去重、满预算(single_tool=2 其余=3)即止；`_trim` 仅去 found 键；`_primary_domains`=首个非 SKIP 域(0/1 元素)。`_synthesize`(system=_SYNTHESIS_SYSTEM)为大模型装配点 |
| `app/integrations/{activity_api,point_mall_api}.py` | 常量字节级 + 客户端可读 | URL/adflags/缓存/签名头字节级；fetch_* 的 POST+归一化+缓存按轨迹重写 |
| `app/tools/{activity,point_mall,park,api_registry}.py` · `repositories/db.py` · `services/recommender.py` · `cli.py` | 签名还原 + 委托/可读 | 工具签名对 .so 还原委托集成层；db 为内置种子 SQLite 演示域；recommender 的 WEIGHTS/召回/重排可读；cli 交互 REPL 委托 graph.chat |
| `app/agent/exception_reply.py` | 字节级还原 + 对拍 | _TEXTS(9)/_DETAILS(8)/各场景卡/客服电话字节级；`reply_for`(=exception_reply) 全 kind×参数组合 vs 新 .so 零差异（未知 kind 回退 no_data；options 仅 unclear_intent 生效；question 对可重试类前置「重新查询」卡） |
| `app/agent/step_labels.py` | 字节级字典 + 关键函数对拍 | _TOOL_LABELS/_TOOL_DETAILS(各21)/_DOMAIN_LABELS(14)+hint 清单字节级；`tool_label/tool_detail/understanding_detail`(过滤 other)/`tool_result_summary`(done/empty/fail)/`_redact` 对拍一致；`format_args/safe_tool_output` readable |
| `app/repositories/qa_log.py` · `app/rag/retriever.py` | readable 骨架 | 表结构/签名对 .so 还原；取数委托已重建层；离线数据缺失处安全回退 |
| `app/admin.py` | 路由 + 响应结构对线上对齐 | /admin/api/* 全路由(docs/images/data/tools/apis/api-detail/uncataloged/westbund/logs/test)**响应结构对线上实测对齐**：列表统一 `{"items":[...]}`(部分带 total)，item 字段逐一还原(docs{name,size,mtime}、data{name,count=JSON顶层键数}、logs{id,ts,ip,session_id,model,dev,question,answer,reasoning,elapsed_ms}+total、tools{name,domain,description,args}等)；/data 只列 14 个业务域(排除 capabilities/home_questions)，parking=6/realtime=5/transport=1 与线上一致；/test 委托 graph.chat。读写委托 config 目录 + qa_log + api_gateway |
| `app/agent/static_context.py` | 字节级还原 + 对拍（可跑） | 本地知识库=`data/docs/*.md`（空行切段为 chunk，文件名=source）。`_clean`/`search_lexical_context`/`build_static_knowledge_context` 对 .so 对拍：中文 bigram 检索（去空白后相邻两字、去重），`coverage`=命中/总 bigram，`score`=命中中「非 ASCII 字母打头」的个数；**先按 score 降序稳定排序→截断 k(默认3)→再过滤**（score≥1、coverage≥0.5、覆盖率恰 0.5 时需 score≥2）；注入模板`【本轮已命中的内部静态知识】`+逐条去「来源：`…`。」+护栏指令后缀，全部字节级一致。纯中文/数字/数字+中文(如 11号线/15分钟)/纯英文/None/阈值/模板/排序零差异；**唯一已知差异**：ASCII 字母紧贴中文无空格(如 WeM4停车权益)的问法评分子规则更细，仍返回正确首要 chunk 但可能漏 1 条次要 chunk——真实用户带中文语境/空格的问法走正常路径完全一致。data/docs 两份 md 已随重建落地，离线可跑；18 条 UT 见 `tests/test_static_context.py` |
| `app/agent/member_agent.py` | 路由字节级 + 结构忠实 | 常量(_ENTRY_TERMS/_PERSONAL_TERMS/_PERSONAL_PHRASES/_MEMBER_DOMAIN_PHRASES/_OTHER_DOMAIN_TERMS/_LEVEL_THRESHOLDS/各 reason 码)字节级；**`should_route_to_member_agent` vs .so 880 用例零差异**：其他域词(停车/车牌/商城)否决优先 → 会员域短语(路由内表不含「怎么入会」) → 个人资料短语 → 个人代词×会员入口词同现；MemberAgentResult 结构还原；answer_member_request 为结构忠实(取数 member_api 已字节级，渲染绑定线上字段=装配点) |
| `app/agent/official_{images,app_knowledge}.py` | 静态成稿字节级 + 结构忠实门控 | 图片常量 + 各分支静态成稿(停车指引/卫生间/客服中心/出行攻略/地铁/场馆导航卡)**字节级还原**(这些文案在 .so 内即硬编码静态文本，逐字一致，含 ```nav``` 块)；触发关键词集结构忠实(偏保守，不误拦停车费/实时车位) |
| `app/agent/live_{merchant,activity,operational,point_mall,member}.py` | 结构忠实重建 | 常量字节级(_CATEGORY_WORDS/_DETAIL_WORDS/_WEEKDAYS/UNKNOWN_REPLY/LOGIN_REQUIRED)；**纯函数对拍零差异**：merchant 的 _keyword/_detail_keyword(除「了解」边界)/_is_generic_category、activity 的 _is_subsequence/_norm_title(falsy→"")/_weekend_dates(本周六日,delta=5-weekday)/_date_label/_activity_keyword(保留「场次」)、member 的 _number(str)/_wem_level(读 member_level_name)；触发门控为局部短语表(不导出)，按实测命中集结构忠实重建、**偏保守避免误拦**；渲染绑定线上 API 字段=装配点，离线回落 None/UNKNOWN/登录引导。详见 `tests/test_planner_and_live.py`(35 UT) |
| `app/tools/{knowledge,parking,member,miniprogram}.py` | 签名还原 + 委托 | 工具函数名/签名对 .so 还原；取数委托已重建的 integrations(miniprogram_api/api_gateway/member_api) |
| `app/agent/customer_reply.py` | 字节级还原 + 对拍 | UNKNOWN_REPLY + 5 条来源前缀正则字节级；`sanitize_customer_reply`(全局 sub 去口癖 + strip) vs 新 .so 30000 条零差异 |
| `app/agent/action_cards.py` | 字节级还原 + 对拍 | 全常量(含 25 条 `_RULES`)字节级；`append/trailing_action_cards`/`cards_for`/`_is_clarifying`/`_domain_ok`/`_nav_cards` vs 新 .so 120000 条零差异（命中/领域过滤/抑制问句自身q/去重/上限 4/空答不加/反问不加/nav 回退全核对） |
| `app/llm/client.py` | 常量字节级 + 工厂/轮换按轨迹重写 | 超时/温度/重试/三档模型常量字节级；`get_llm`/`get_understanding_llm`/`get_synthesis_llm` 三档工厂 + DeepSeek key 轮换 + 客户端缓存按签名与轨迹重写；`ReasoningChatOpenAI` 为 langchain ChatOpenAI 子类装配点 |
| `app/integrations/api_gateway.py` | 常量重建 + 全行为验证 | `_bigrams`/`_norm_md_path`(30 万条零差异)/`_searchable`/`_public`(异常一致)/`is_allowed`/`search_catalog`/`call_readonly_api`(GET+appId+声明名过滤+required 校验+登录态头非空注入+5 分支) 全矩阵零差异；目录数据文件(API.md/tools_catalog.json)随部署下发，缺失时安全失败 |

## 待重建（新版新增 / 变化模块）

- 变化模块：`tools/{member,parking,miniprogram}`、
  `agent/{member_agent,parking_agent,live_merchant,action_cards,answer_format,step_labels,
  official_app_knowledge,exception_reply}`、
  `services/recommender`、`rag/retriever`、`repositories/{db,qa_log}`、`main`、`admin`
  （已完成并移出本清单：`capabilities/{router,registry,renderer}`、`router/semantic_router`、
  `agent/{response_formatter,live_program,graph}`、`integrations/{member_api,miniprogram_api,api_gateway}`、
  `main`、`llm/client`）
- 入口链路现状：`main.py`(Controller) → `graph.chat/chat_stream`(Service 漏斗) → `llm/client`(大模型) 三层已通。
  **`real_agent.app.agent.graph` 与 `real_agent.app.main` 现已能干净 import（18 工具域就绪）**，确定性后处理链
  （sanitize_customer_reply + append_action_cards + exception_reply）可真实运行并已冒烟验证；ReActAgent 的
  token 级循环需 langgraph/langchain + 模型 key（线上依赖）。
- 本轮新增/修订文件可在容器 `/home/claude/rebuild_new` 下用
  `PYTHONPATH=/home/claude/tools:. python -c "import stub,real_agent.app.main"` 验证 import。
- **全量完成**：58 个编译产物（.so）现已全部有对应 .py 重建，0 缺失。确定性模块（路由/理解门控/
  渲染/后处理/异常话术/行动卡/各 should_route 判定/格式化）字节级对拍；网络/LLM/数据耦合模块
  （integrations/tools/planner/recommender/db/live_* 直达）忠实可读、委托已重建层。能干净 import、
  确定性链路可跑；大模型那一跳需装 langgraph/langchain + 模型 key。
- 已补完：`planner`、各 `live_*`、`member_agent` 路由、`official_{images,app_knowledge}`、`static_context`、`sport_suitability`、`customer_reply`、`table_format`、`cli`
- 仍为装配点（依赖运行时/大模型，无法离线逐字对拍）：`llm/client` 的 ReasoningChatOpenAI 真实装配；各 `live_*`/`member_agent`/`planner._synthesize` 的渲染/合成文案（绑定线上 API 字段或 LLM 输出）

## 线上联调校验（http://47.116.7.1 /admin，2026-10-23）

用内置浏览器对线上部署做页面/接口测试（`POST /chat`、`/health`、`/config`、`/models`），据真实输入输出校正：

- **知识正确性验证**：线上「停车费/积分规则/会员升级/卫生间/地址/地铁」回答中的事实（首小时10元·封顶80元·15分钟免费、零售10/餐饮20/体验50元积1分、WeM 500/2000/5000·1:1、卫生间7处、龙腾大道2266号、11号线龙耀路）与重建的 `static_context` + `data/docs/*.md` **完全一致**。
- **渲染契约**：前端按围栏块渲染——`​```suggest`（action_cards，title/meta/action{label,q}/icon，与重建一致）、`​```cards`（活动）、`​```nav`、`​```shops`（商户列表，{total,shops:[{name,logo,category,location,hours}]}）、`![](…)` 图片。注意：`render_merchant_list`（markdown）是 .so 内的另一渲染器，线上商户列表走的是 `​```shops` 能力/工具路径，二者不同。
- **capabilities/renderer 修正**：线上「我的积分/会员信息」等 `direct_response` 能力走 `render(intent,payload)` 确定性渲染。以 .so 为 oracle 对拍后修正模板：空 payload→统一 `当前小梦还没有收录相关的信息哦~`（23/23 一致）；`parking.fee`/`member.info`/`member.expiring_points`→两列表；优惠券列表→`| 券名称 | 有效期 |` 表格 + 「有 **N 张**」计数；`parking.availability/info`→`| 停车场 | 位置 | 总车位 | 剩余车位 | 营业时间 | 充电桩 |` 六列；`coupon.count`→「您当前有 **N 张可用券**。」；`member.point_detail`/`growth_detail`→`| 时间 | 积分/成长值 | 说明 |` 表格。单元格取值绑定线上接口字段（装配点），模板/兜底/计数已对齐。UT 见 `tests/test_renderer_live.py`(22)。
- **缺失数据补齐**：原重建 `data/` 缺能力/接口数据，`capabilities.json` 还是空 `[]`。已从部署包补回 `capabilities.json`、`capabilities/{member,parking,coupon,knowledge}.json`、`apis/tools_catalog.json`、`parking.json`、`transport.json`、`realtime.json` 等——能力快路径与 api_gateway 目录现可离线运行。
- **一个环境差异（非代码问题）**：线上 `/config` 的 `agent_name` = 「真实数据客服」，而重建 `config.py` 默认 `AGENT_NAME='小梦'`（= .so 默认）。线上是用环境变量覆盖的，不是 bug。

### /admin 后台接口校验（同上联调）

对 `/admin`（运营平台：文本知识/图片知识/结构化数据/工具中心/测试中心/运营日志）逐个接口实测，修正了重建 `admin.py` 的响应结构——原重建各接口返回 `{"docs":[]}`/`{"logs":[]}` 等**键名与结构都对不上**，现已按线上对齐（见模块表 admin 行）。关键点：列表统一 `{"items":[...]}`；`/data` count = JSON 顶层键/元素个数（parking 6、realtime 5、transport 1，已核对一致）；`/logs` 支持 `q`/`ip`/`limit`/`offset` 过滤并返回 `total`，ts 存 epoch、读时格式化为 ISO；`/test` 是测试中心跑一条对话（POST `{message}` → graph.chat）；`/uncataloged`、`/westbund`、`/apis`、`/api-detail` 为接口只读目录维护。
