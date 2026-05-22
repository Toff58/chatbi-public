# ChatBI 项目文件地图

更新时间：2026-05-19

## 阅读顺序

1. `PROJECT_ARCHITECTURE.md`：项目主文档和变更记录。
2. `app.py`：Streamlit 前端入口和用户交互。
3. `graph/agent.py`：Agent 编排、工具调用、保护规则和耗时记录。
4. `deepseek_langchain.py`：DeepSeek 与 LangChain ChatModel 的适配层。
5. `sql/executor.py`：SQLite 只读执行与 SQL 安全校验。
6. `graph/rag.py`、`graph/sql_examples.py`、`graph/business_terms.py`：业务口径、RAG 规则和 SQL 示例。
7. `tests/run_agent_tests.py`、`tests/test_cases.py`：回归测试入口和验收样例。

## 根目录

| 路径 | 作用 | 备注 |
| --- | --- | --- |
| `.gitignore` | Git 忽略规则 | 已忽略 `.venv/`、`__pycache__/`、`.streamlit/secrets.toml`、`*.log` 等本地文件。 |
| `PROJECT_ARCHITECTURE.md` | 项目主架构文档 | 本次已更新最新架构、测试与变更记录。 |
| `app.py` | Streamlit 问数工作台 | 负责页面、会话历史、示例问题、结果图表/明细展示、查询日志写入。 |
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
| `graph/agent.py` | Agent 主流程 | 检索上下文、构造 prompt、调用 DeepSeek、执行 SQL 工具、记录耗时和 debug 信息。 |
| `graph/workflow.py` | 对外入口 | 保留 `build_graph()`，避免调用方依赖内部实现。 |
| `graph/state.py` | 状态结构 | 定义问题、SQL、结果、指标、clarifications、timings、debug_info 等字段。 |
| `graph/nodes.py` | 本地兜底总结 | 旧节点流水线已精简，仅保留 `build_local_summary()`。 |
| `graph/rag.py` | 轻量本地 RAG | 维护业务规则、字段上下文、SQL 示例检索和格式化输出。 |
| `graph/sql_examples.py` | SQL few-shot 示例 | 覆盖 App 排行、宏观人数估算、rebase、非法枚举空结果等高风险口径。 |
| `graph/business_terms.py` | 固定业务词映射 | 如“休闲娱乐”固定映射到 `category IN ('娱乐休闲')`。 |
| `graph/evaluation.py` | 单次运行指标 | 计算 SQL 合法性、工具调用、结果数量、RAG precision/recall、耗时等。 |

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

