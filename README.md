# ChatBI / Text-to-SQL / AI Agent 数据分析助手

## 公开演示版说明

- 数据窗口：公开演示版仅包含 `2025-07` 的 App 人群数据。
- 多人访问：公开演示版默认关闭全局 Memory，避免不同访问者的问题互相影响。当前页面内的聊天历史仍由 Streamlit 会话保留。
- 运行日志：仓库不包含历史日志；用户问数后会在服务端追加写入 `logs/query_log.csv`，并生成 `logs/query_debug.jsonl` 供调试复盘。
- 密钥管理：不要提交 `.streamlit/secrets.toml`。部署时通过环境变量或 Streamlit Secrets 配置 `DEEPSEEK_API_KEY`。

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
- RAG 示例库：使用本地 JSON 维护问题-SQL 示例，不引入复杂向量数据库。
- 轻量 Memory：开发版支持记录最近问题、SQL、主题和常用筛选条件；公开演示版默认关闭全局 Memory，避免多人串上下文。
- 日志观测：写入查询日志和调试日志，方便复盘 SQL、工具调用、耗时和结果质量。
- 测试入口：提供不依赖模型的 smoke test 和可选的 Agent 回归测试入口。

## Agent Workflow

当前项目保持单 Agent 结构，避免为了面试强行拆多 Agent。核心流程如下：

1. `retrieve_context`：读取表结构、字段枚举、RAG 规则和 few-shot 示例；公开演示版不读取全局 memory。
2. `generate_sql`：LLM 根据用户问题和上下文生成只读 SQL。
3. `validate_sql`：工具层校验 SQL 安全性、字段枚举、人数口径和结果上限。
4. `execute_sql`：调用 `query_app_data` 查询 SQLite。
5. `generate_answer`：LLM 根据工具返回的 JSON 生成中文业务结论。
6. `log_interaction`：应用层写入 CSV/JSONL 日志；公开演示版不写入全局 memory。

## 技术栈

- Python
- Streamlit
- SQLite
- Pandas / Altair
- LangChain Agent
- DeepSeek Chat API
- 本地 JSON RAG / few-shot 示例库

## 项目结构

```text
.
├── app.py                         # Streamlit ChatBI 前端
├── main.py                        # 命令行单次问数入口
├── create_db.py                   # CSV 导入 SQLite 入口
├── test_graph.py                  # 本地 smoke test，不依赖模型 API
├── config.py                      # 数据库、表名、模型配置
├── deepseek_client.py             # SQL prompt 构造
├── deepseek_langchain.py          # DeepSeek LangChain ChatModel 适配
├── graph/
│   ├── agent.py                   # Agent 主流程与 query_app_data 工具
│   ├── workflow.py                # workflow steps 和 build_graph 入口
│   ├── rag.py                     # 轻量 RAG 规则检索
│   ├── sql_examples.py            # 读取 data/sql_examples.json
│   ├── memory.py                  # 轻量短期 memory
│   └── prompts/
│       ├── sql_generation_prompt.md
│       └── answer_generation_prompt.md
├── sql/
│   └── executor.py                # SQL 校验、枚举校验、SQLite 查询
├── data/
│   ├── app_data.csv               # 演示数据
│   ├── import_csv_to_db.py        # CSV 导入脚本
│   └── sql_examples.json          # 问题-SQL few-shot 示例库
├── logs/
│   ├── query_log.csv              # 查询日志，运行后生成/追加
│   └── query_debug.jsonl          # 调试日志，运行后生成/追加
├── tests/
│   └── run_agent_tests.py         # 需要模型 API 的回归测试
└── docs/
    └── ...                        # 架构与评审说明
```

## 数据说明

当前数据表：`app_data`

公开演示版当前只有一个活跃月份：`2025-07`。

核心字段：

- `app_name`：App 名称
- `category` / `category_new`：App 品类
- `active_month`：活跃月份，当前只有 `2025-07`
- `city_tier`、`income`、`gender`、`province`、`age`：用户画像维度
- `ppl_cnt`：用户数，数据库中已是可直接使用的实际人数

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
- 用户问题
- 生成 SQL
- 是否校验通过
- 查询结果摘要
- 最终回答

调试日志：`logs/query_debug.jsonl`

公开演示版默认关闭全局 Memory，不生成 `logs/lightweight_memory.json`，避免多人访问时互相影响上下文。如需在开发环境恢复全局 Memory，可设置环境变量：

```bash
CHATBI_ENABLE_GLOBAL_MEMORY=true
```

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
- 做简单的评测集和自动化质量看板。

面试后继续做：

- 接入向量检索或企业知识库。
- 支持多轮追问和更完整的上下文管理。
- 做权限、审计、部署和多用户隔离。

Conventional Commit summary:
- `docs(readme): add interview-oriented chatbi overview`
