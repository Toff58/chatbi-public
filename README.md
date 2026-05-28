# ChatBI / Text-to-SQL / AI Agent 数据分析助手

## 项目定位

这是一个面向面试展示的 ChatBI 原型：把传统 BI / SQL 查询流程升级为可对话的 AI Agent 数据分析助手。用户用自然语言提问，系统生成安全 SQL，查询本地 SQLite 数据，并输出中文结论、图表和明细结果。

项目重点不是模型训练，也不是生产级 Agent 平台，而是展示 BI、SQL、Python、LLM 应用开发、Tool Calling、RAG 示例库、日志和轻量 workflow 的工程闭环。

## 业务背景

业务人员经常需要问类似问题：

- 用户数最多的前 10 个 App 是哪些？
- 年轻女性在娱乐休闲类 App 里最常用的是哪个？
- 广东省总人数是多少？
- 女性用户占比是多少？

传统方式通常需要分析师理解需求、确认口径、写 SQL、查库、整理结论。本项目把这个流程拆成 Agent workflow，帮助非技术用户更快完成问数和初步分析。

## 核心能力

- 自然语言理解：识别 Top、排行、画像筛选、占比、宏观人数估算等常见 BI 问题。
- SQL 生成：根据表结构、字段枚举、业务口径和 few-shot 示例生成 SQLite SELECT SQL。
- SQL 校验：只允许 SELECT / WITH，拒绝 DELETE、UPDATE、DROP、PRAGMA 等危险语句，并校验枚举值和人数口径。
- 数据查询：通过 `query_app_data` 工具读取本地 SQLite 表 `app_data`。
- 结果总结：根据工具返回的 JSON 输出简洁中文结论。
- 展示优化：图表标题、tooltip、图例、明细表和下载文件使用业务名称，避免直接暴露底层字段名。
- 可问范围：侧边栏提供字段字典和指标字典，用户可查看可问维度、可用取值和指标口径。
- 枚举问法：对“有哪些/取值/枚举/可问范围”类问题直接返回维度取值，不改写成人数统计。
- 结果下载：明细支持 CSV / Excel 下载，图表优先支持 JPG 下载并保留 SVG 回退。
- RAG 示例库：使用本地 JSON 维护问题-SQL 示例，不引入复杂向量数据库。
- 高频问题缓存：使用本地 JSON 维护高频问题缓存，示例问题命中后跳过模型生成，直接复用缓存 SQL 并返回结果。
- 轻量 Memory：按 `session_id` 持久化最近问题、SQL、主题和常用筛选条件，用于公开 demo 的多轮上下文参考。
- 会话恢复：Streamlit URL 自动带上 `session_id`，同一 URL 刷新后可恢复最近会话历史。
- 日志观测：写入查询日志和调试日志，方便复盘 SQL、工具调用、耗时和结果质量。
- 测试入口：提供不依赖模型的 smoke test 和可选的 Agent 回归测试入口。

## Agent Workflow

当前项目保持单 Agent，不强行拆 Planner/Reviewer 等多 Agent；但编排层已经使用显式 LangGraph `StateGraph`，让检索、预检、枚举直答和 SQL Agent 执行成为可见节点。核心流程如下：

1. `retrieve_context`：读取表结构、字段枚举、RAG 规则、few-shot 示例和当前 session 的轻量 memory。
2. `resolve_followup_question`：对“湖南省呢？”这类省略追问做确定性补全。
3. `lookup_question_cache`：高频问题精确命中后跳过模型生成，直接复用缓存 SQL 和结果。
4. `preflight_guardrails`：判断数据月份范围、不可支持问题、字段枚举问法和未知字段。
5. 条件路由：缓存/枚举/数据边界/失败分支直接返回；正常分析问题进入 `run_sql_agent`。
6. `run_sql_agent`：LangChain `create_agent` 生成 SQL，并强制调用 `query_app_data`。
7. `query_app_data`：工具层校验 SQL 安全性、字段枚举、人数口径和结果上限，再查询 SQLite。
8. `log_interaction`：应用层写入 CSV/JSONL 日志，SQL Agent 更新当前 session 的轻量 memory。

## 技术栈

- Python
- Streamlit
- SQLite
- Pandas / Altair
- LangChain Agent
- LangGraph StateGraph
- DeepSeek Chat API
- 本地 JSON RAG / few-shot 示例库

## 项目结构

```text
.
├── app.py                         # Streamlit 页面入口，只保留页面流程和会话交互
├── main.py                        # 命令行单次问数入口
├── session_ids.py                 # session_id 规范化，避免文件路径注入
├── create_db.py                   # CSV 导入 SQLite 入口
├── test_graph.py                  # 本地 smoke test，不依赖模型 API
├── config.py                      # 数据库、表名、模型配置
├── deepseek_client.py             # SQL prompt 构造
├── deepseek_langchain.py          # DeepSeek LangChain ChatModel 适配
├── graph/
│   ├── workflow.py                # LangGraph StateGraph 和 build_graph 入口
│   ├── nodes.py                   # LangGraph 节点适配层
│   ├── agent.py                   # Agent 运行时：prompt、模型调用、结果解析
│   ├── preflight.py               # 数据范围、枚举问法、未知字段等预检规则
│   ├── sql_tool.py                # query_app_data 工具和 SQL/结果保护
│   ├── vocabulary.py              # 业务词表、枚举问法和保护关键字
│   ├── rag.py                     # 轻量 RAG 规则检索
│   ├── sql_examples.py            # 读取 data/sql_examples.json
│   ├── question_cache.py           # 高频问题缓存命中和缓存结果执行
│   ├── memory.py                  # 轻量短期 memory
│   └── prompts/
│       ├── sql_generation_prompt.md
│       └── answer_generation_prompt.md
├── sql/
│   └── executor.py                # SQL 校验、枚举校验、SQLite 查询
├── ui/
│   ├── database.py                # 启动时数据库一致性检查和 CSV 导入
│   ├── query_logging.py           # 查询日志和调试日志
│   ├── dataframe.py               # 结果表展示名和中间列过滤
│   ├── charts.py                  # 图表类型选择和 Altair 渲染
│   ├── downloads.py               # 下载按钮组织
│   ├── session_history.py         # 按 session_id 持久化页面会话历史
│   ├── excel_export.py            # Excel 文件生成
│   ├── chart_image_export.py      # JPG 图表导出
│   ├── chart_svg_export.py        # SVG 图表导出
│   └── dictionary.py              # 可问范围页面
├── data/
│   ├── app_data.csv               # 演示数据
│   ├── import_csv_to_db.py        # CSV 导入脚本
│   ├── sql_examples.json          # 问题-SQL few-shot 示例库
│   └── frequent_question_cache.json # 高频问题缓存种子
├── logs/
│   ├── query_log.csv              # 查询日志，运行后生成/追加
│   ├── memory/                    # 按 session_id 隔离的轻量 memory，运行后生成
│   └── chat_sessions/             # 按 session_id 隔离的页面会话历史，运行后生成
├── tests/
│   ├── test_cases.py              # 50 条产品级回归评测样例
│   └── run_agent_tests.py         # 需要模型 API 的回归测试
└── docs/
    ├── resume_ai_agent.md
    ├── resume_bi_data.md
    └── interview_preparation.md
```

## 数据说明

当前数据表：`app_data`

核心字段：

- `app_name`：App 名称
- `category` / `category_new`：App 品类
- `active_month`：活跃月份，当前只有 `2025-07`
- `city_tier`、`income`、`gender`、`province`、`age`：用户画像维度
- `ppl_cnt`：用户数，数据库中已是可直接使用的实际人数

用户界面不会直接展示底层字段名。常见展示名包括：`app_name` 展示为“App”，`user_count` 展示为“用户数”，`estimated_user_count` 展示为“估算用户数”，`city_tier` 展示为“城市等级”。

字段取值类问题会走枚举逻辑，例如“有哪些城市等级可以问”“省份有哪些取值”“有哪些品类”。这类问题只返回对应维度的可用取值，不会改写成人数统计、排行或占比。

## 如何运行

首次或数据更新后导入数据库：

```bash
python create_db.py
```

运行本地 smoke test，不需要模型 API：

```bash
python test_graph.py
```

运行 Streamlit 页面：

```bash
streamlit run app.py
```

页面首次打开会自动生成 `session_id` 并写入 URL 查询参数；刷新或再次打开同一 URL 时，会读取同一个 session 的会话历史和轻量 memory。侧边栏“清空会话”会同时清除当前 session 的页面历史和 memory。

命令行单次问数，需要配置 `DEEPSEEK_API_KEY`：

```bash
python main.py "用户数最多的前 10 个 App 是哪些？"
```

运行 Agent 回归测试，需要配置 `DEEPSEEK_API_KEY`：

```bash
python tests/run_agent_tests.py
```

## 示例输出

问题：

```text
用户数最多的前 10 个 App 是哪些？
```

可能生成的 SQL：

```sql
SELECT app_name, SUM(ppl_cnt) AS user_count
FROM app_data
GROUP BY app_name
ORDER BY user_count DESC
LIMIT 10;
```

回答形态：

```text
用户数最多的 App 主要集中在若干头部应用，系统会返回前 10 名 App 及对应用户数，并在页面中展示表格和图表。
```

## 日志与 Memory

查询日志：`logs/query_log.csv`

字段包括：

- 时间
- session_id
- 用户问题
- 生成 SQL
- 是否校验通过
- 查询结果摘要
- 最终回答

调试日志：`logs/query_debug.jsonl`

轻量 Memory：`logs/memory/<session_id>.json`

页面会话历史：`logs/chat_sessions/<session_id>.json`

高频问题缓存种子：`data/frequent_question_cache.json`

当前先把侧边栏示例问题加入缓存。命中缓存时系统会在追问补全后直接执行缓存 SQL，不再调用模型生成 SQL；客户前端只展示业务结论，不展示缓存命中文案。执行结果会写入调试日志的 `question_cache` 和 `context_usage.question_cache_hit`，便于复盘命中情况。

如果配置了 Supabase 日志同步，`chatbi_query_logs` 也会写入 `question_cache_hit`、`question_cache_entry_id`、`model_call_count` 和 `question_cache_result_reused`，可以直接在云端筛选缓存命中记录。

Memory 只记录当前 session 最近几次交互的问题、SQL、主题和筛选条件，用于短期上下文参考。公开 demo 中不同访客的上下文不会混在同一个 memory 文件里；面试时可以解释为“按 session 隔离的轻量上下文记忆”，后续可升级为用户偏好记忆或企业知识库记忆。

## 面试展示重点

- 这个项目不是算法训练项目，而是 LLM 应用工程项目。
- 我的优势是 BI / SQL / 数据分析背景，知道业务问数里的口径、字段、筛选和结果表达问题。
- Agent 的价值不只是生成 SQL，而是把生成、校验、执行、总结、日志复盘串成可解释流程。
- RAG 在这里不是复杂向量库，而是把业务口径和 SQL 示例注入上下文，降低模型编造字段和错误口径的概率。
- SQL 安全通过 prompt 约束和工具层校验双保险完成。

## 后续优化方向

1 天内可做：

- 增加更多业务问题-SQL 示例。
- 补充失败 SQL 的重试策略。
- 在页面上增加“查看 SQL”开发调试开关。

1 周内可做：

- 增加 FastAPI 服务层。
- 接入更多数据表和表关系说明。
- 将 50 条回归评测接入自动化质量看板，并继续扩充真实问法变体。

面试后继续做：

- 接入向量检索或企业知识库。
- 支持多轮追问和更完整的上下文管理。
- 做权限、审计、部署和多用户隔离。

Conventional Commit summary:
- `docs(readme): add interview-oriented chatbi overview`

Conventional Commit summary:
- `feat(memory): persist demo memory by session id`

Conventional Commit summary:
- `feat(cache): add frequent question cache for examples`

Conventional Commit summary:
- `feat(logging): sync question cache fields to supabase`

Conventional Commit summary:
- `fix(cache): hide cache hit wording from customer answers`
