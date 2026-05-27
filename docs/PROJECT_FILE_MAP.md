# ChatBI 项目文件地图

更新时间：2026-05-28

## 阅读顺序

1. `PROJECT_ARCHITECTURE.md`：项目主文档和变更记录。
2. `app.py`：Streamlit 页面流程和聊天交互。
3. `graph/workflow.py`、`graph/nodes.py`：LangGraph StateGraph、节点和条件边。
4. `graph/agent.py`、`graph/preflight.py`、`graph/sql_tool.py`：Agent 运行时、预检规则和 SQL 工具。
5. `ui/`：数据库准备、日志、表格、图表、下载和字段字典。
6. `deepseek_langchain.py`：DeepSeek 与 LangChain ChatModel 的适配层。
7. `sql/executor.py`：SQLite 只读执行与 SQL 安全校验。
8. `tests/run_agent_tests.py`、`tests/test_cases.py`：回归测试入口和验收样例。

## 根目录

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `.gitignore` | Git 忽略规则 | 已忽略 `.venv/`、`__pycache__/`、`.streamlit/secrets.toml`、`*.log` 等本地文件。 |
| `PROJECT_ARCHITECTURE.md` | 项目主架构文档 | 本次已更新最新架构、测试与变更记录。 |
| `app.py` | Streamlit 问数工作台入口 | 只保留页面、会话历史、示例问题和聊天交互，具体展示/日志能力由 `ui/` 提供。 |
| `config.py` | 全局配置 | 数据库路径、CSV 路径、表名、DeepSeek API 参数、字段列表。 |
| `deepseek_client.py` | SQL prompt 构造与异常类型 | 已移除旧直连 DeepSeek 的冗余函数，只保留 Agent 仍使用的 prompt 构造。 |
| `deepseek_langchain.py` | DeepSeek ChatModel 适配器 | 支持 LangChain tool calling，并记录每次模型调用耗时和 token 使用量。 |
| `app_user_distribution.db` | 本地 SQLite 数据库 | 由 `data/app_data.csv` 导入，表名为 `app_data`。 |
| `query_log.csv` | 查询摘要日志 | 记录用户问题、SQL、答案、错误、指标和总耗时；当前工作区已有历史改动。 |
| `query_debug.jsonl` | 查询调试日志 | 记录工具调用、RAG、模型过程摘要、耗时等；当前工作区已有历史改动。 |

## Streamlit 配置

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `.streamlit/secrets.example.toml` | secrets 示例 | 说明 `DEEPSEEK_API_KEY` 配置格式。 |
| `.streamlit/secrets.toml` | 本地密钥 | 被 `.gitignore` 忽略；本次没有展开或写入该文件内容。 |

## 数据目录

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `data/app_data.csv` | 原始业务数据 | 146466 行，字段包括 App、品类、城市、收入、性别、省份、年龄和人数。 |
| `data/import_csv_to_db.py` | CSV 导入 SQLite | 校验必要字段、清洗 `ppl_cnt`、写入导入元数据、创建索引。 |

## Agent 与业务规则

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `graph/workflow.py` | LangGraph 对外入口 | 构建 `StateGraph`，注册节点、条件边并返回 `CompiledStateGraph`。 |
| `graph/nodes.py` | LangGraph 节点适配层 | 包装 Agent 运行时方法，并提供 `route_after_preflight()`。 |
| `graph/state.py` | 状态结构 | 定义问题、SQL、结果、指标、clarifications、timings、debug_info 和图内部路由字段。 |
| `graph/agent.py` | Agent 运行时 | 检索上下文、构造 prompt、调用 DeepSeek、解析工具调用、记录耗时和 debug 信息。 |
| `graph/preflight.py` | 模型前预检规则 | 处理数据月份范围、枚举直答、不可支持问题和未知字段。 |
| `graph/sql_tool.py` | SQL 查询工具 | 定义 `query_app_data`，集中处理 SQL 安全、枚举、人数口径和结果保护。 |
| `graph/vocabulary.py` | 业务词表 | 集中维护枚举问法、趋势词、不可支持关键词、App 别名和内部列名。 |
| `graph/result_summary.py` | 兜底总结 | 模型没有最终回答时生成最小本地总结。 |
| `graph/rag.py` | 轻量本地 RAG | 维护业务规则、字段上下文、SQL 示例检索和格式化输出。 |
| `graph/sql_examples.py` | SQL few-shot 示例 | 覆盖 App 排行、宏观人数估算、rebase、非法枚举空结果等高风险口径。 |
| `graph/business_terms.py` | 固定业务词映射 | 如“休闲娱乐”固定映射到 `category IN ('娱乐休闲')`。 |
| `graph/evaluation.py` | 单次运行指标 | 计算 SQL 合法性、工具调用、结果数量、RAG precision/recall、耗时等。 |

## UI 辅助模块

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `ui/database.py` | 数据库准备 | 检查 SQLite 与 CSV 行数、mtime 和导入元数据，不一致时自动导入。 |
| `ui/query_logging.py` | 查询与调试日志 | 写入 `query_log.csv` 和 `query_debug.jsonl`，配置 Supabase 后同步云端日志。 |
| `ui/dataframe.py` | 结果表展示 | 过滤中间计算列，并把底层字段名映射为业务展示名。 |
| `ui/charts.py` | 图表选择与渲染 | 根据结果形态构造图表规格并渲染 Altair。 |
| `ui/downloads.py` | 下载按钮 | 组织 CSV、Excel、图表下载按钮。 |
| `ui/excel_export.py` | Excel 导出 | 生成 xlsx 文件内容。 |
| `ui/chart_image_export.py` | JPG 图表导出 | 按图表规格绘制 JPG。 |
| `ui/chart_svg_export.py` | SVG 图表导出 | 生成 SVG 回退图。 |
| `ui/chart_export_utils.py` | 图表导出工具 | 复用颜色、数值格式化和浮点转换。 |
| `ui/dictionary.py` | 可问范围页面 | 展示指标字典和字段枚举。 |

## SQL 执行

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `sql/executor.py` | SQLite 执行与校验 | 只允许单条 `SELECT`/`WITH`，阻断写操作，要求真实 `FROM/JOIN app_data`，校验枚举筛选值。 |

## 测试与日志

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `tests/test_cases.py` | 12 条正式回归样例 | 覆盖排行、画像筛选、宏观人数、安全 SQL、非法枚举和不存在字段。 |
| `tests/run_agent_tests.py` | 回归测试入口 | 写入 latest CSV 和时间戳 CSV，包含模型、工具、SQL 执行等分段耗时。 |
| `tests/run_generated_question_tests.py` | 批量生成问题测试脚本 | 当前为未跟踪文件；用于更大范围探索测试。 |
| `logs/agent_test_results.csv` | 最新 12 条回归结果 | 本次最终结果为 12/12 通过。 |
| `logs/agent_test_results_20260519_183409.csv` | 本次最终时间戳测试日志 | 保留每条样例的分段耗时。 |
| `logs/generated_questions_test_results*` | 历史批量问题测试结果 | 当前为未跟踪文件，本次未删除。 |

## 本地生成目录

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `.venv/` | Python 虚拟环境 | 不纳入代码审计，不应提交。 |
| `.git/` | Git 元数据 | 不纳入业务代码审计。 |
| `__pycache__/`、`graph/__pycache__/`、`tests/__pycache__/`、`sql/__pycache__/` | Python 编译缓存 | 可再生成，已被忽略。 |
| `logs/streamlit_8503.*.log` | 本次启动 Streamlit 8503 的本地运行日志 | `*.log` 已被忽略。 |
