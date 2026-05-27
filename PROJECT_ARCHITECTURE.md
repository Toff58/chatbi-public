# ChatBI 项目架构说明

## 产品目标

ChatBI 是面向客户使用的智能问数产品。用户用自然语言提出业务问题，系统生成安全 SQL，查询本地 SQLite 数据，并返回结论、图表和明细数据。

前端只展示客户需要理解的内容：问题输入、会话历史、查询进度、结论、图表和结果明细。模型过程、SQL、RAG 上下文、验收指标和宏观人数计算过程不在前端展示，完整调试信息只写入日志。

## 主要模块

### `app.py`

Streamlit 前端入口。

职责：
- 渲染问数工作台、会话历史、示例问题和 `st.chat_input()` 输入。
- 展示查询进度、结论、图表/明细 tabs、耗时和返回行数。
- 根据结果形态自动选择图表：单值结果不画图，排行默认条形图，占比结果可用环图，多指标小结果可用分组柱状图，跨月结果预留折线图。
- 结果支持下载 CSV 和 Excel；如果本次生成图表，同时支持下载 JPG 图，环境不支持 JPG 时回退 SVG。
- 不展示 SQL、RAG、验收指标、分子、分母、rebase 过程等调试或计算过程。
- 写入查询日志 `query_log.csv` 和调试日志 `query_debug.jsonl`。
- 启动时检查 SQLite 是否与 CSV 行数和导入元数据一致；不一致时自动覆盖导入 CSV。
- 图表使用 Altair 显式指定 x 轴排序，确保柱状图按指标降序从左到右展示。
- 表格和图表会过滤常见中间计算列，避免前端暴露宏观人数估算过程。

调试策略：
- 完整调试信息始终写入 `query_debug.jsonl`，便于开发复盘。
- 客户前端不提供调试信息开关。

### `graph/workflow.py`

对外保留原来的 `build_graph()` 入口。

职责：
- 返回 ChatBI Agent 应用。
- 保持 `app.py`、测试脚本等调用方不需要知道内部实现细节。

### `graph/agent.py`

LangChain Agent 主逻辑。

职责：
- 使用 `langchain.agents.create_agent` 构建底层 LangGraph Agent。
- 定义 `query_app_data` 工具供模型调用。
- 注入 RAG 上下文和固定业务范围映射。
- 在模型调用前拦截 `device_brand` 这类不在表结构中的字段，避免生成假成功空结果。
- 解析最后一次工具调用的 SQL，避免展示 SQL 与最终答案不一致。
- 记录模型调用、SQL 工具、RAG 检索、业务口径说明和验收指标。
- 单个 App 或按 `app_name` 排行的画像人群总用户数直接 `SUM(ppl_cnt)`。
- 固定 base 人数为 6 亿，任何返回给前端的人数都不能超过 6 亿。
- 当前数据只包含 `2025-07` 一个月；用户查询其他月份或趋势、环比、同比时，Agent 会在调用模型前直接说明数据限制，不生成跨月 SQL。
- 省份、城市等级、性别、年龄、收入等宏观人群人数先算有效样本占比，再用 base 乘以占比估算。
- 工具层会阻断 SQL 里对 `ppl_cnt` 的二次放大表达式，避免结果被重复换算。
- 工具层会阻断直接输出宏观 `SUM(ppl_cnt)`、超过 base 的人数结果和中间计算列。

### `graph/rag.py`

轻量本地 RAG 检索。

职责：
- 维护业务规则、人数口径、rebase 规则和字段上下文。
- 根据问题检索相关规则，注入 Agent prompt。
- 从 `graph/sql_examples.py` 读取可检索 SQL 样例。
- 不依赖外部向量库，方便本地直接运行。

### `graph/sql_examples.py`

独立 SQL 样例库。

职责：
- 维护可供 RAG 检索的问题-SQL 样例。
- 标记少量 `include_in_prompt` 样例，让 SQL prompt 保留固定 few-shot。
- 覆盖 App 排行、画像筛选 App 排行、宏观省份人数、女性占比 rebase 等高风险口径。

### `graph/business_terms.py`

固定业务词映射。

职责：
- 将“休闲娱乐”等大范围词固定映射到已有数据库品类。
- 将“年轻用户”“下沉城市”“高收入”“低收入”等模糊画像词映射为默认口径，并通过前端口径说明告知用户。
- 避免模型创造不存在的品类。
- 当前“休闲娱乐”固定为 `category IN ('娱乐休闲')`。

### `graph/evaluation.py`

单次运行验收指标计算。

职责：
- 记录 `accuracy`、`precision`、`recall`、`sql_valid`、`execution_success`、`tool_called`、`result_count`、`latency_ms`。
- 指标用于开发验收和回归观察，不直接面向客户展示。

### `graph/nodes.py`

本地兜底总结。

职责：
- 当前 LangChain Agent 主流程不再使用旧节点流水线。
- 只保留 `build_local_summary()`，在模型没有最终回答时提供最小兜底结论。

### `deepseek_langchain.py`

DeepSeek 到 LangChain ChatModel 的适配层。

职责：
- 让项目在不额外安装 `langchain_openai` 或 `langchain_deepseek` 的情况下使用 LangChain Agent。
- 支持 tool calling。
- 记录每次模型调用的耗时、HTTP 状态和 token 使用量，供测试日志和调试日志分析。

### `deepseek_client.py`

SQL prompt 构造逻辑和 DeepSeek 异常类型。

职责：
- 为 Agent 构造 SQL 生成规则、字段枚举和 few-shot 上下文。
- 补充 6 亿 base、宏观人数比例估算、NA/空白 rebase、固定品类映射等规则。
- 从 `graph/sql_examples.py` 注入少量固定 few-shot。
- 旧的直连 DeepSeek HTTP 调用已移除，模型调用统一由 `deepseek_langchain.py` 负责。

### `sql/executor.py`

SQLite 查询执行层。

职责：
- 只允许安全的 `SELECT` / `WITH` 查询。
- 阻断写入、删除、建表、PRAGMA 等危险操作。
- 要求 SQL 真实 `FROM` 或 `JOIN` `app_data`，避免仅在字符串里出现表名时被误判合法。
- 提供 schema profile 供 prompt 和 RAG 使用。

### `tests/run_agent_tests.py`

正式回归测试入口。

职责：
- 运行 `tests/test_cases.py` 中的 12 条高风险样例。
- 写入 latest 测试 CSV `logs/agent_test_results.csv` 和时间戳 CSV。
- 记录总耗时、两次模型调用耗时、SQL 工具校验/执行耗时、结果数量和失败原因。

## 数据与日志

### 数据

- SQLite 数据库：`app_user_distribution.db`
- 数据表：`app_data`
- 原始 CSV：`data/app_data.csv`
- 数据月份：当前仅包含 `active_month = 2025-07`
- 导入脚本：`data/import_csv_to_db.py`
- 启动触发入口：`app.py` 的 `ensure_database()`
- 导入元数据表：`chatbi_import_metadata`

启动时会对比 CSV 行数、CSV 修改时间和导入元数据。如果数据库缺失、表缺失、行数不一致或元数据缺失，会自动用 CSV 覆盖导入 `app_data`。

### 查询日志

文件：`query_log.csv`

用途：
- 记录每次用户问题、SQL、答案、错误和验收指标。
- 适合做运行质量统计。

### 调试日志

文件：`query_debug.jsonl`

用途：
- 记录完整模型过程相关信息，包括 SQL、RAG、工具调用、耗时和匹配到的业务口径。
- 前端调试开关展示的是该信息的子集。

## 当前运行链路

1. 用户在 `app.py` 输入问题。
2. `app.py` 调用 `graph.workflow.build_graph()`。
3. `build_graph()` 返回 `ChatBIAgentApp`。
4. `ChatBIAgentApp` 检索 RAG 规则和固定业务词映射。
5. Agent 生成 SQL 并调用 `query_app_data` 工具。
6. 工具校验 SQL，执行 SQLite 查询，并阻断超过 6 亿的人数结果、宏观直接求和和中间计算列。
7. Agent 根据工具结果生成中文结论。
8. `app.py` 展示结论、图表和明细，并写入日志。

## 文档维护规则

每次修改本项目文档时，在对应变更记录末尾输出一条 Conventional Commit 风格摘要，字段名固定为 `Conventional Commit summary`。摘要前缀必须使用官方常见类型，例如 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`，格式示例：`feat(agent): add schema guard and timing logs`。

## 重要业务口径

### 人数口径

`ppl_cnt` 在数据库中已经是可直接使用的实际人数，不需要在 SQL、工具层、图表或结论里再次放大。

固定 base 人数为 6 亿。任何返回给前端的人数、用户数、人口数都不能超过 6 亿。

数据已按 App、类别、年龄段、城市、性别、收入等维度切分，每条记录代表唯一人群切片。计算某个 App 或按 `app_name` 排行的画像条件 App 总用户数时，直接对 `ppl_cnt` 求和。

推荐 SQL：

```sql
-- 单个 App、App 排行、带画像筛选后的 App 排行
SUM(ppl_cnt) AS user_count
```

如果问题问宏观人数，而不是某个 App 的总人数，例如“广东省总人数”“女性用户人数”“各年龄段人数”，不能直接输出 `SUM(ppl_cnt)`。正确做法是先算目标人群在有效样本中的比例，再用 6 亿 base 乘以比例，并且最终结果只暴露用户要看的维度和最终指标。

```sql
-- 例：广东省总人数估算，最终不输出分子、分母或比例
SELECT
  '广东省' AS province,
  ROUND(
    600000000.0
    * SUM(CASE WHEN province = '广东省' THEN ppl_cnt ELSE 0 END)
    / NULLIF(SUM(CASE WHEN province IS NOT NULL AND TRIM(province) != '' AND province != 'NA' THEN ppl_cnt ELSE 0 END), 0)
  ) AS estimated_user_count
FROM app_data;
```

计算占比时，NA、NULL 或空白只表示该字段未取到值，不代表这部分人不存在。分母只用该字段有有效值的部分；例如男性占比 50%、女性占比 48%、其余 2% 未取到值时，女性最终占比按 `48% / (50% + 48%)` rebase。

工具层规则：
- SQL 里不能写 `ppl_cnt * 10000`、`SUM(ppl_cnt) * 10000` 或 `10000 * ppl_cnt`。
- 工具会阻断非 App 宏观人数直接 `SUM(ppl_cnt)`、超过 6 亿的人数字段和常见中间计算列。
- 工具返回的行、前端图表、明细表格和最终结论只使用最终指标，不展示计算过程。

### 大范围品类

模型不能创造数据库里不存在的品类。遇到大范围词时，必须使用固定映射。

当前固定映射：

| 用户词 | 字段 | 固定取值 |
| --- | --- | --- |
| 休闲娱乐、娱乐休闲、泛娱乐、娱乐、休闲 | `category` | 娱乐休闲 |
| 社交、聊天、沟通 | `category` | 社交沟通 |
| 本地生活、生活服务、外卖 | `category` | 生活类、美食外卖 |
| 年轻、青年、年轻人、低龄 | `age` | 小于20岁、20-24岁、25-29岁 |
| 下沉、低线、三线及以下 | `city_tier` | 三线城市、四线城市、五线城市 |
| 高收入、高薪、高净值 | `income` | 20K+ |
| 低收入、低薪 | `income` | 3000元以下、3000到5000 |

如果前端命中固定映射，会向用户展示口径说明，例如“口径说明：已按默认口径将‘休闲娱乐’理解为：娱乐休闲。”

### 数据时间范围

当前 CSV 和 SQLite 只包含 `2025-07` 一个月的数据。

处理规则：
- 用户明确查询 `2025-07` 或“7月”时，可以继续查询，并按当前单月数据输出。
- 用户查询其他月份，例如 `2024-01`、`2025-06`、`8月`，系统直接说明当前没有对应月份数据。
- 用户查询趋势、走势、环比、同比、近几个月、按月变化时，系统直接说明只有一个月数据，无法提供趋势。

### 结果展示与下载

前端根据查询结果决定是否生成图表：
- 只有一个数或单行结果时，不生成图表，只展示结论和明细。
- 单指标多行结果默认使用条形图，适合 Top、排行、分布。
- 占比类字段且行数较少时使用环图。
- 多指标小结果使用分组柱状图。
- 如果后续接入多月数据，`active_month` 多点结果可使用折线图。

每次有结果返回时，前端提供 CSV 和 Excel 下载；如果生成了图表，同时提供 JPG 图下载。JPG 由服务端按图表数据重新绘制，会预留标题、坐标标签和数值标签边距；如果当前运行环境缺少位图能力，则回退提供 SVG 图下载。

## 变更记录

### 2026-05-13

改动：
- 将手写 LangGraph 状态机入口重构为 `langchain.agents.create_agent` 写法。
- 新增 DeepSeek LangChain ChatModel 适配器。
- 新增 SQL 查询工具 `query_app_data`。
- 补充用户人数口径处理。
- 图表和表格默认按数值列降序展示。
- 新增轻量本地 RAG，提高 SQL 生成准确性。
- 新增运行验收指标和日志记录。
- 前端改成客户视角页面，默认隐藏数据源、SQL、RAG 和指标。
- 新增调试日志 `query_debug.jsonl`。
- 修复展示 SQL 可能取到第一次工具调用、与最终答案不一致的问题。
- 新增固定业务词映射，避免“休闲娱乐”等范围词被模型临场创造品类。

原因：
- 客户使用时应关注业务答案，而不是模型内部过程。
- 调试信息需要保留，但应从客户界面剥离到日志和临时调试开关。
- SQL 和答案必须来自同一次最终工具调用，保证可解释性和可验收。
- 大范围业务词需要稳定口径，避免同一个问题每次包含的品类不一致。

### 2026-05-14 00:43

改动：
- 修复数据库导入逻辑：原来只要 DB 文件存在就跳过导入，可能一直使用 `create_db.py` 写入的 11 行样例库；现在启动时会检查 CSV 行数和导入元数据，不一致就覆盖导入。
- `data/import_csv_to_db.py` 新增导入元数据表和常用字段索引，并显式提交事务。
- 已将当前 SQLite 的 `app_data` 覆盖导入为 `data/app_data.csv` 的 146466 行数据。
- 图表从 `st.bar_chart` 改为 Altair，并显式传入 x 轴排序顺序，保证柱状图最高值在最左边。
- 当时调整了 SQL 人数口径和工具层校验；该口径已被 2026-05-18 的直接求和规则替换。
- 固定业务词映射按当前 CSV 的真实品类更新：“休闲娱乐”映射为 `category = '娱乐休闲'`。

原因：
- 当前数据表是 App、类别、画像、人数的明细结构，需要用清晰口径约束模型生成 SQL。
- 前端图表排序必须和表格/结论一致，避免客户看到“最大值不在左侧”的反直觉结果。
- 数据导入必须可追踪、可覆盖、可验证，避免样例库和真实 CSV 混用。
- 人数口径需要和上游数据处理方式保持一致。

### 2026-05-14 00:59

改动：
- 修正画像筛选后的 App 排行口径：例如“年轻女性在娱乐休闲用的最多的是哪个 app？”应先筛选年龄、性别和品类，再按 `app_name` 使用 `SUM(ppl_cnt)` 汇总，最后取最大值。
- `graph/rag.py` 和 `deepseek_client.py` 补充画像筛选排行规则，减少模型生成错误聚合口径的概率。

原因：
- 带画像筛选的问题需要先统计每个 App 中满足画像条件的总人数，再比较哪个 App 最大。

Conventional Commit summary:
- `fix(sql): sum profile-filtered app rankings by app`

### 2026-05-18

需求识别：
- 需要在 SQL 生成前给模型完整字段枚举，排除计算口径字段 `ppl_cnt`；模型做筛选时只能使用这些枚举值。
- 需要给模型可直接参考的问题-SQL 示例，补充模型不一定理解的业务逻辑。
- 需要记录字段枚举、业务规则和 SQL 示例是否在本次生成链路中应用。

现状对比：
- 原有 `sql/executor.py#get_schema_profile()` 只提供每个字段前 30 个样例值，不是完整枚举。
- 原有 `graph/rag.py` 已有业务规则和 SQL 提示，但没有结构化的问题-SQL 示例库。
- 原有 `query_debug.jsonl` 记录了 RAG 和工具调用，但没有单独记录字段枚举和 SQL 示例是否应用。

改动结果：
- `sql/executor.py` 新增 `enum_values`，对除 `ppl_cnt` 外的字段读取完整 `DISTINCT` 枚举，同时保留 `sample_values` 兼容旧逻辑。
- `deepseek_client.py` 的 SQL prompt 改为注入完整枚举，并明确要求筛选值必须来自枚举；不存在的筛选值不能写入 `WHERE`。
- `sql/executor.py` 新增 `validate_enum_filters()`，工具层会拦截简单 `=` / `IN` / `LIKE` 中不属于枚举的筛选值，让 Agent 有机会改写 SQL。
- `graph/rag.py` 新增轻量问题-SQL 示例检索，覆盖整体 App Top、画像筛选 App Top、一线城市网络购物 Top、下沉高收入男性 Top 等高风险口径。
- `graph/agent.py` 在模型生成 SQL 前同时注入字段完整枚举、RAG 业务规则、固定业务映射和问题-SQL 示例。
- `app.py` 的调试日志新增顶层 `context_usage`，记录 `field_enums_applied`、`business_rules_applied`、`sql_examples_applied` 及命中的字段枚举数量、RAG id、示例 id。

原因：
- 让模型在生成 SQL 前先被约束到真实数据取值范围，降低编造字段值和品类的概率。
- 用少量示例补足人数口径、画像筛选和排行类问题的业务逻辑，避免大范围重构。
- 通过调试日志可以复盘每次 SQL 质量变化是否真的使用了枚举和示例上下文。

### 2026-05-18 人数口径更新

改动：
- 明确数据导入链路：启动入口 `app.py#ensure_database()` 调用 `data/import_csv_to_db.py`，从 `data/app_data.csv` 导入 SQLite。
- `ppl_cnt` 按数据库中的实际人数直接使用，移除工具层结果放大逻辑。
- App、品类、城市、性别、收入等维度的总用户数统一使用 `SUM(ppl_cnt)`。
- 其中品类、城市、性别、收入等非 App 宏观维度的直接求和口径已被 2026-05-19 的 6 亿 base 比例估算规则替换；App 维度仍直接求和。
- 工具层保留二次放大保护：如果 SQL 写出 `ppl_cnt * 10000`、`SUM(ppl_cnt) * 10000` 或同类表达式，会返回错误要求改写。
- 回归测试用例更新为 10 条，覆盖直接求和、固定品类映射、非法枚举、安全 SQL 和不存在字段。

原因：
- 数据库中的数据已经完成上游放大处理，查询结果不应再次乘以 `10000`。
- 数据已切分到唯一人群切片，计算某个 App 的总用户数时直接 `SUM(ppl_cnt)` 即可。

Conventional Commit summary:
- `fix(data): use direct ppl count sum`

### 2026-05-19 RAG 样例与 6 亿 base 口径更新

需求识别：
- SQL 样例需要从 `graph/rag.py` 抽到独立文件，方便 RAG 检索和后续维护。
- prompt 仍需要保留少量固定 few-shot，避免模型在高风险口径上完全依赖检索命中。
- 固定 base 人数为 6 亿，任何人数结果不能超过 6 亿。
- 宏观人数不是某个 App 的总人数时，必须先算有效样本占比，再用 base 乘以占比估算。
- NA、NULL、空白只是字段未取到值，计算占比时要排除这些缺失值后 rebase。
- 前端不能展示宏观人数计算过程。

改动结果：
- 新增 `graph/sql_examples.py`，集中维护问题-SQL 样例，并用 `include_in_prompt` 标记少量固定 few-shot。
- `graph/rag.py` 改为从独立样例文件检索 SQL 示例，同时新增 6 亿 base、宏观人数估算和 NA/空白 rebase 的 RAG 规则。
- `deepseek_client.py` 和 `graph/agent.py` 的 prompt 补充 base 上限、宏观人数比例估算、有效值 rebase 和不暴露中间计算列的规则。
- `graph/agent.py#query_app_data()` 增加结果保护：阻断直接输出宏观 `SUM(ppl_cnt)`、超过 6 亿的人数字段和常见中间计算列。
- `app.py` 移除前端调试信息开关，并在图表/表格展示前过滤常见中间计算列；调试信息仍写入日志。
- 回归用例补充广东省总人数、女性占比 rebase，并将性别宏观人数用例改为 base 比例估算口径。

原因：
- 单个 App 总人数与宏观人群人数的口径不同，不能继续把所有维度都当作 App 总量直接求和。
- 6 亿 base 是前端可展示人数的硬上限，需要 prompt 和工具层同时保护。
- 缺失字段值不能从人群中删除，只能在该字段的占比计算中排除后重算比例。
- SQL 样例独立维护后，新增高风险口径不需要继续膨胀 RAG 规则文件。

Conventional Commit summary:
- `feat(agent): add rag sql examples and population base rules`

### 2026-05-19 架构巡检、体验升级与测试日志

需求识别：
- 需要扫描项目文件并形成可查阅的文件地图。
- 需要对照成熟 Agent 架构评估当前产品设计，尤其是 Agent 编排、工具边界、guardrail、观测和评测闭环。
- 需要清理临时脚本和旧流程代码，避免后续维护误用。
- 需要把前端从单次表单升级为更适合连续问数的工作台。
- 需要记录每条测试样例的模型调用、SQL 工具、执行和总耗时。

改动结果：
- 新增 `docs/PROJECT_FILE_MAP.md`，记录项目每个主要文件/目录的作用和阅读顺序。
- 新增 `docs/AGENT_ARCHITECTURE_REVIEW.md`，对照 OpenAI Agents SDK、LangGraph 和 MCP 的成熟 Agent 规则输出评估。
- 新增 `docs/CODE_SIMPLIFICATION_NOTES.md`、`docs/REMOVED_FILES_LOG.md`、`docs/UX_IMPROVEMENT_NOTES.md`、`docs/PRODUCT_MANAGER_REVIEW.md`。
- `app.py` 改为问数工作台：支持会话历史、侧边栏示例问题、`st.chat_input()`、图表/明细 tabs、耗时和返回行数展示。
- `deepseek_langchain.py` 新增模型调用耗时与 token 使用记录。
- `graph/agent.py` 新增 SQL 工具分段耗时、模型调用明细、未知字段 schema guard 和更完整 debug_info。
- `sql/executor.py` 修复表名校验，要求 SQL 真实 `FROM/JOIN app_data`。
- `graph/sql_examples.py` 新增非法枚举空结果示例，提升“火星省”等无效枚举问题的稳定性。
- `graph/nodes.py` 精简为本地兜底总结函数。
- `deepseek_client.py` 删除旧 DeepSeek 直连调用函数，模型调用统一由 `deepseek_langchain.py` 负责。
- 删除 `check_env.py`、`check_query.py`、`test_graph.py`、`create_db.py`。
- `tests/run_agent_tests.py` 增加 latest 和时间戳测试 CSV，并记录分段耗时。
- 启动新的 Streamlit 服务：`http://localhost:8503`。

测试结果：
- 最终执行 `.\.venv\Scripts\python.exe tests\run_agent_tests.py`。
- 12 条回归样例全部通过，pass rate 为 100%。
- 最新测试日志：`logs/agent_test_results.csv`。
- 本次最终时间戳日志：`logs/agent_test_results_20260519_183409.csv`。
- 平均总耗时约 4057 ms；平均首轮模型调用约 2114 ms；平均末轮模型调用约 1946 ms；平均 SQL 工具耗时约 216 ms。

原因：
- 当前阶段更适合“生产化单 Agent”而不是拆多 Agent：工具边界、口径规则、评测和可观测性比复杂编排更关键。
- 前端问数场景天然需要连续上下文、示例入口和结果分层展示。
- 旧脚本和旧节点流水线会增加误用风险，清理后主链路更清晰。
- 分段耗时能帮助判断优化重点，目前主要耗时来自两次模型调用，SQL 工具本身耗时较低。

Conventional Commit summary:
- `feat(agent): improve chat workspace guardrails and timing logs`

### 2026-05-20 口径确认、数据范围和下载能力

需求识别：
- 用户给出模糊词或大范围词时，需要默认口径说明，避免客户误以为系统按未声明口径统计。
- 当前数据只有 `2025-07` 一个月，查询其他月份或趋势时不能生成误导性结果。
- 图表不应对所有结果一律展示；单值结果不需要图表，多行结果应按形态选择合适图表。
- 问数结果需要支持下载 CSV、Excel；如果生成图表，也需要下载图片格式。

改动结果：
- `graph/business_terms.py` 扩展默认口径：年轻用户、下沉城市、高收入、低收入会映射到固定枚举，并通过前端 `st.info()` 展示口径说明。
- `graph/agent.py` 新增数据时间范围前置检查：只有 `2025-07` 可查；其他月份、趋势、环比、同比、近几个月等问题会直接返回数据限制说明，不调用模型生成 SQL。
- `graph/agent.py` 补强月份识别，覆盖 `25/6`、`25年三月`、`202506` 等写法，并对最终客户答案清洗 `base`、人数上限、后端校验等后端逻辑表述。
- `deepseek_client.py` 的 SQL prompt 补充当前可用月份和模糊词默认口径规则，作为模型侧兜底约束。
- `app.py` 将图表逻辑从固定柱状图改为结果形态识别：单行结果不画图，排行/分布用条形图，占比小结果用环图，多指标小结果用分组柱状图，保留多月折线图能力。
- `app.py` 新增下载按钮：所有非空结果可下载 CSV 和 Excel；生成图表时额外提供 SVG 图下载。

原因：
- 客户可见的口径说明比隐式假设更可解释，也便于后续业务方确认或调整。
- 单月数据不能支撑跨月趋势，必须在模型生成前阻断，避免 SQL 合法但业务结论错误。
- `base` 和人数上限属于后端保护规则，不应作为客户结论的一部分输出。
- 下载能力是 BI 场景的基础闭环，客户需要把结果表和图表继续带到汇报或二次分析中。

验证：
- 执行 `.\.venv\Scripts\python.exe -m py_compile app.py graph\agent.py graph\business_terms.py graph\rag.py deepseek_client.py` 通过。
- 轻量验证月份保护：`25年6月`、`25年3月`、`2024-01` 查询返回“当前数据只包含 2025-07”，`2025-07` 单月查询不拦截，趋势问题返回无法提供趋势。
- 轻量验证口径命中：“年轻女性在娱乐休闲类 App...”会提示休闲娱乐和年轻用户口径；“下沉城市里高收入男性...”会提示下沉城市和高收入口径。
- 执行 `.\.venv\Scripts\python.exe tests\run_agent_tests.py`，12 条正式回归样例全部通过，pass rate 为 100%。最新日志：`logs/agent_test_results.csv`；本次时间戳日志：`logs/agent_test_results_20260520_152445.csv`。

Conventional Commit summary:
- `feat(app): add scope notices data window guard and downloads`

### 2026-05-27 图表标题与 JPG 下载优化

需求识别：
- 下载图表边缘出现截断，主要风险来自导出画布留白不足，而不是 SVG 格式本身。
- 页面图表和下载图片都需要明确标题，便于截图、汇报和二次传播。
- 下载图片优先使用更通用的 JPG 格式，减少 SVG 在部分查看器或文档软件中的显示差异。

改动结果：
- `app.py` 为自动生成的条形图、折线图、环图和分组柱状图补充标题，并同步展示在 Altair 页面图表上。
- `app.py` 新增 JPG 图表生成逻辑，按图表类型重新绘制位图，预留标题、左侧类目标签、右侧数值标签和底部轴标签空间。
- 下载按钮由“下载图表 SVG”改为优先“下载图表 JPG”；如果运行环境缺少 Pillow，则自动回退 SVG 下载。
- 继续保留 SVG 生成能力，并扩大 SVG 画布和边距，避免内部调用时右侧数值或长标签被 `viewBox` 裁切。

原因：
- JPG 不能天然修复布局问题；如果原始画布尺寸不足，换格式仍可能截断。正确做法是在生成图片时重新计算边距和可用绘图区。
- JPG 更适合直接插入文档、PPT 或聊天工具，SVG 作为回退能保持兼容性。

验证：
- 执行 `app.py` 语法编译检查通过。
- 使用条形图、折线图、环图和分组柱状图样例分别生成 JPG 与 SVG，JPG 均返回合法 JPEG 文件头，SVG 均正常生成。

Conventional Commit summary:
- `fix(app): export titled chart jpg without clipped edges`
