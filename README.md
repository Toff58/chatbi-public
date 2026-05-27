# ChatBI

ChatBI 是一个基于 Streamlit、SQLite 和 LLM Agent 的自然语言问数应用。用户可以用中文提出 BI 问题，系统会根据本地 App 人群数据生成安全 SQL，执行查询，并返回中文结论、图表和明细表。

公开演示版默认关闭全局 Memory，避免多人访问时互相影响上下文；当前页面内的聊天历史仍由 Streamlit 会话保留。

## 核心能力

- 自然语言问数：支持 Top 排行、画像筛选、占比、分布和单月统计等常见 BI 问题。
- 安全 SQL 生成：只允许 `SELECT` / `WITH` 查询，并限制访问本地 `app_data` 表。
- 数据口径约束：基于字段枚举、业务规则和 few-shot 示例减少字段编造和错误口径。
- 数据边界保护：对跨 App 重合、共同用户、去重覆盖、留存、频次、时长、订单金额等当前数据不支持的问题直接说明限制，不生成误导性答案。
- 结果呈现：在 Streamlit 页面展示中文结论、自然语言图表标题、业务化列名和明细数据。
- 可问范围：侧边栏提供字段字典和指标字典，用户可查看可问维度、可用取值和指标口径。
- 枚举问法：对“有哪些/取值/枚举/可问范围”类问题直接返回维度取值，不改写成人数统计。
- 结果下载：明细支持 CSV / Excel 下载，图表优先支持 JPG 下载并保留 SVG 回退。
- 日志观测：本地写入 CSV/JSONL 日志；配置 Supabase 后可同步写入云端日志表。

## 数据范围

当前演示数据表为 `app_data`，数据窗口为 `2025-07` 单月。

主要字段：

- `app_name`：App 名称
- `category` / `category_new`：App 品类
- `active_month`：活跃月份，当前只有 `2025-07`
- `city_tier`、`income`、`gender`、`province`、`age`：用户画像维度
- `ppl_cnt`：用户数，数据库中已是可直接使用的实际人数

用户界面不会直接展示底层字段名。常见展示名包括：`app_name` 展示为“App”，`user_count` 展示为“用户数”，`estimated_user_count` 展示为“估算用户数”，`city_tier` 展示为“城市等级”。

字段取值类问题会走枚举逻辑，例如“有哪些城市等级可以问”“省份有哪些取值”“有哪些品类”。这类问题只返回对应维度的可用取值，不会改写成人数统计、排行或占比。

数据是 App × 品类 × 月份 × 城市等级 × 收入 × 性别 × 省份 × 年龄 的聚合切片，不包含用户 ID、设备 ID、订单、访问日志或跨 App 关联关系。因此可以回答 App 规模、画像分布和聚合排行，但不能回答同一批用户在多个 App 之间的交叉重合、去重覆盖、留存、转化或行为频次。

## Agent Workflow

当前项目保持单 Agent，不强行拆 Planner/Reviewer 等多 Agent；但编排层已经使用显式 LangGraph `StateGraph`，让检索、预检、枚举直答和 SQL Agent 执行成为可见节点。公开演示版默认关闭全局 Memory 写入，页面内聊天历史仍由 Streamlit session 保留。核心流程如下：

1. `retrieve_context`：读取表结构、字段枚举、RAG 规则、few-shot 示例和可选轻量 memory。
2. `preflight_guardrails`：判断数据月份范围、不可支持问题、字段枚举问法和未知字段。
3. 条件路由：枚举/数据边界/失败分支直接返回；正常分析问题进入 `run_sql_agent`。
4. `run_sql_agent`：LangChain `create_agent` 生成 SQL，并强制调用 `query_app_data`。
5. `query_app_data`：工具层校验 SQL 安全性、字段枚举、人数口径和结果上限，再查询 SQLite。
6. `log_interaction`：应用层写入 CSV/JSONL 日志，配置 Supabase 后同步云端日志。

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
│   ├── memory.py                  # 可选轻量短期 memory
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
│   ├── excel_export.py            # Excel 文件生成
│   ├── chart_image_export.py      # JPG 图表导出
│   ├── chart_svg_export.py        # SVG 图表导出
│   └── dictionary.py              # 可问范围页面
├── data/
│   ├── app_data.csv               # 演示数据
│   ├── import_csv_to_db.py        # CSV 导入脚本
│   └── sql_examples.json          # 问题-SQL few-shot 示例库
├── tests/
│   └── run_agent_tests.py         # 需要模型 API 的回归测试
└── docs/                          # 架构、产品和工程说明
```

## 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

首次运行或数据更新后导入 SQLite：

```bash
python create_db.py
```

启动 Streamlit 页面：

```bash
streamlit run app.py
```

命令行单次问数需要配置 `DEEPSEEK_API_KEY`：

```bash
python main.py "用户数最多的前 10 个 App 是哪些？"
```

运行不依赖模型 API 的 smoke test：

```bash
python test_graph.py
```

运行 Agent 回归测试需要配置 `DEEPSEEK_API_KEY`：

```bash
python tests/run_agent_tests.py
```

## 配置

本地开发可以通过环境变量或 Streamlit Secrets 配置密钥：

```toml
DEEPSEEK_API_KEY = "your-deepseek-api-key"
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

不要提交 `.streamlit/secrets.toml`。

公开演示版默认关闭全局 Memory，不生成 `logs/lightweight_memory.json`。如需在开发环境开启：

```bash
CHATBI_ENABLE_GLOBAL_MEMORY=true
```

## 日志

- 本地查询日志：`logs/query_log.csv`
- 本地调试日志：`logs/query_debug.jsonl`
- 可选云端日志：Supabase 表 `chatbi_query_logs`

日志会记录用户问题、生成 SQL、工具调用、耗时、结果摘要和最终回答，方便排查 SQL 质量和口径问题。

## 示例问题

- 用户数最多的前 10 个 App 是哪些？
- 年轻女性在娱乐休闲类 App 里最常用的是哪个？
- 广东省总人数是多少？
- 女性用户占比是多少？
- 一线城市里网络购物类 App 用户数最多的前 5 个是哪些？

## 后续方向

- 补充更多业务问题-SQL 示例和回归评测集。
- 接入更多数据表和表关系说明。
- 增加 SQL 重试、澄清问题和权限控制。
- 将 Streamlit 原型扩展为 API 服务与多用户部署形态。
