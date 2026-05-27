# AI Agent / ChatBI 项目面试准备

## 1. 项目介绍话术

### 30 秒版本

这个项目是一个 ChatBI / Text-to-SQL 的 AI Agent 原型。我之前做 BI 和数据分析，经常遇到业务方用自然语言问数据、分析师再手写 SQL 的场景，所以我把这个流程拆成 Agent workflow：理解问题、生成 SQL、校验 SQL、查询 SQLite、总结结果、记录日志。项目重点不是训练模型，而是把 LLM 用在真实 BI 问数流程里，并通过 RAG 示例库、字段枚举、SQL 安全校验和轻量 memory 提高可用性。

### 1 分钟版本

我的项目定位是“BI 工具升级为 AI Agent 数据分析助手”。用户输入类似“年轻女性在娱乐休闲类 App 里最常用的是哪个”，系统会结合表结构、字段枚举、业务口径和 few-shot SQL 示例生成只读 SQL，然后通过工具调用查询 SQLite，最后输出中文结论、图表和明细。

我重点做了三类约束：第一是 prompt 和 RAG 示例，告诉模型字段含义、统计口径和可参考 SQL；第二是工具层 guardrail，只允许 SELECT / WITH，拒绝危险 SQL 和非法枚举；第三是日志和轻量 memory，记录问题、SQL、校验状态、结果摘要和最近上下文。这个项目不是生产级平台，但能完整展示 LLM 应用开发、Tool Calling、Text-to-SQL、SQL 安全和 BI 业务理解。

### 3 分钟版本

我之前主要做 BI、SQL、数据分析和内部数据工具支持，所以我选了一个和背景最贴合的 AI Agent 方向：ChatBI / 智能问数。

项目背景是业务人员经常会问“哪个 App 用户最多”“某类人群偏好什么 App”“某个省份人数是多少”“女性用户占比是多少”这类问题。传统流程是业务方提需求，分析师确认口径、写 SQL、查数、做表和解释结论。这个项目把这条链路做成一个可运行的 AI Agent 原型。

技术上，我用 Python、Streamlit、SQLite、LangGraph、LangChain Agent 和 DeepSeek API。核心流程是 `retrieve_context -> preflight_guardrails -> 条件路由 -> run_sql_agent/query_app_data -> log_interaction`。模型不是直接给答案，而是必须调用 `query_app_data` 工具。工具会校验 SQL 只能是 SELECT / WITH，不能有 DELETE、UPDATE、DROP、PRAGMA 这类危险语句；同时还会检查字段枚举、人数口径和结果上限，避免模型编造字段或输出错误统计。

为了提升 Text-to-SQL 的稳定性，我做了轻量 RAG 和 few-shot 示例库，用 JSON 保存常见问题、SQL、适用表和说明，比如 App Top、画像筛选、宏观人数估算、女性占比 rebase。Prompt 也拆成独立文件，明确表结构、字段含义、安全规则和输出格式。项目还加了轻量 memory，记录最近问题、SQL、主题和筛选条件；日志则记录时间、用户问题、生成 SQL、校验状态、结果摘要和最终回答。

我会把它讲成一个可运行的求职展示项目，而不是生产级系统。它的价值是把我原来的 BI / SQL / 数据分析经验，转化成 LLM 应用开发能力：懂业务问题、懂数据口径、会写 SQL，也能把 Agent workflow、RAG、Tool Calling 和日志评测做成一个闭环。

## 2. 面试可能问题和回答

### 为什么做这个项目？

因为我之前工作偏 BI 和数据分析，日常大量工作是理解业务问题、确认口径、写 SQL、查数和解释结果。AI Agent 最适合落地的方向之一就是把这些重复但有规则的流程工具化，所以我选择 ChatBI，而不是去做和我背景不匹配的模型训练项目。

### 和普通 Text-to-SQL 有什么区别？

普通 Text-to-SQL 重点是把问题转成 SQL。这个项目多了一层 Agent workflow：先检索业务规则和示例，再生成 SQL，然后工具层校验安全性和口径，执行后再总结答案，并写日志复盘。也就是说，它不是只生成 SQL，而是把问数流程做成可解释、可追踪的闭环。

### 为什么用 Agent / Workflow？

因为 BI 问数不是一次简单生成文本。它至少包含理解问题、确认口径、生成 SQL、校验 SQL、查库、解释结果和记录日志。用 workflow 表达这些步骤，可以清楚说明每一步的输入输出，也方便后续加失败重试、人工确认或权限控制。

### 为什么用 LangGraph？

现在项目层使用显式 LangGraph `StateGraph`。我没有拆成多个 Agent，而是把单 Agent 问数链路拆成几个清晰节点：`retrieve_context` 负责取 schema、RAG、few-shot 和 memory；`preflight_guardrails` 负责数据范围、枚举直答、未知字段和不支持问题；条件边决定直接回答还是进入 `run_sql_agent`；真正生成 SQL 时再用 LangChain `create_agent` 和 `query_app_data` 工具。

这样既保留单 Agent 的简单性，又体现 LangGraph 的优势：状态统一流转、节点职责可测试、条件路由清楚，后续要加 SQL 修正重试、人工确认或多工具路由时，不需要推翻入口。

### SQL 如何生成？

模型会收到用户问题、表结构、字段枚举、业务口径、few-shot 示例和轻量 memory。Prompt 里明确要求只输出 SQLite SELECT SQL，并说明各字段含义和统计口径。对于 Top、画像筛选、占比、宏观人数等高风险问题，会用 RAG 示例和规则进行约束。

### 如何防止错误 SQL？

有两层防护。第一层是 prompt 约束：只允许 SELECT / WITH，禁止危险操作，筛选值必须来自字段枚举。第二层是工具校验：`validate_select_sql` 会拒绝危险关键字和非目标表查询，`validate_enum_filters` 会拦截不存在的枚举值，工具层还会检查人数口径和返回结果是否异常。

### RAG 怎么用？

这里没有引入向量数据库，而是使用轻量本地 RAG。`graph/rag.py` 维护业务规则，`data/sql_examples.json` 维护问题-SQL 示例，系统根据用户问题做关键词检索，把相关规则和 SQL 示例拼进 prompt。这样面试展示更稳定，也符合最小可行优化。

### Memory 是什么？存在哪里？

Memory 是轻量短期记忆，不是长期用户画像。公开 demo 里会按 `session_id` 隔离保存：页面首次打开会生成 `session_id` 并放到 URL，Agent memory 存到 `logs/memory/<session_id>.json`，页面会话历史存到 `logs/chat_sessions/<session_id>.json`。它记录最近几次问题、SQL、主题和筛选条件，作用是给后续问题提供上下文参考，同时避免不同访客的上下文互相污染。后续可以升级为长期用户偏好记忆或企业知识库记忆。

### 日志怎么做？

查询日志写入 `logs/query_log.csv`，使用 `utf-8-sig`，避免中文乱码。字段包括时间、`session_id`、用户问题、生成 SQL、是否校验通过、查询结果摘要和最终回答。调试日志写入 `logs/query_debug.jsonl`，包含 RAG 命中、工具调用、模型耗时等更详细信息。

### SQL 执行失败怎么办？

当前会把错误写入 state 和日志，并在前端给用户提示查询失败。工具层会返回错误信息，Agent 有机会改写 SQL。后续可以进一步做自动重试策略，比如把失败原因重新注入模型，让它生成修正后的 SQL。

### 如何评估回答质量？

当前有基础评测：测试用例会检查 SQL 是否包含关键模式、是否拒绝危险 SQL、是否命中 RAG 规则、结果行数是否合理、是否暴露中间计算列。日志里也记录 `sql_valid`、`execution_success`、`tool_called`、`result_count`、`latency_ms` 等指标。后续可以做人工标注评测集。

### 如何降低 token 成本？

可以从三方面做：第一，字段枚举和 RAG 只注入相关内容，不把所有文档塞进 prompt；第二，few-shot 示例控制数量；第三，对常见问题做缓存或模板化 SQL。当前项目已经只取 top_k RAG 和少量 few-shot，属于轻量方案。

### 你以前是 BI，为什么转 AI Agent？

我的转向不是跨到算法训练，而是把 BI 和数据分析经验延伸到 LLM 应用开发。AI Agent 在企业里很重要的一类落地场景就是连接业务流程、数据库和内部工具。我懂业务问数、SQL 和数据口径，这些正好是 ChatBI / Text-to-SQL 成败的关键。

### 你和算法工程师相比有什么优势？

算法工程师可能更擅长模型训练和模型优化。我优势在业务数据场景、SQL、指标口径、工具落地和跨团队沟通。我更适合做 LLM 应用工程、数据智能应用、ChatBI、内部效率工具这类岗位，把模型能力接到业务系统里。

### 这个项目的业务价值是什么？

它能减少业务方等待分析师取数的时间，让常见问题可以自助查询；同时保留 SQL、口径说明和日志，分析师可以复核和优化。对企业内部来说，它是从传统 BI 到 AI 数据助手的一个低成本过渡方案。

## 3. 项目修改记录

| 修改文件 | 为什么修改 | 对应 JD 能力点 | 面试时怎么讲 |
|---|---|---|---|
| `README.md` | 补充面试化项目定位、业务背景、workflow、运行方式和示例。 | 项目表达、业务理解、工程说明 | 这是项目的一页式说明，面试官可以快速理解项目价值。 |
| `graph/prompts/sql_generation_prompt.md` | 把 SQL 生成 prompt 从代码中抽离。 | Prompt Engineering、Text-to-SQL、安全约束 | Prompt 里明确表结构、字段含义、输出格式和危险 SQL 禁止规则。 |
| `graph/prompts/answer_generation_prompt.md` | 把 Agent 系统 prompt 和回答规则独立出来。 | Agent workflow、Tool Calling、回答约束 | Agent 不是直接回答，而是必须调用工具后基于结果总结。 |
| `data/sql_examples.json` | 用 JSON 维护问题-SQL 示例库。 | RAG、Few-shot、Context Engineering | 不上复杂向量库，先用轻量示例库解决面试展示和稳定性。 |
| `graph/sql_examples.py` | 从 JSON 读取 SQL 示例并注入 prompt/RAG。 | Python 工程能力、可维护性 | 示例库和代码分离，后续新增案例不用改核心逻辑。 |
| `graph/memory.py` | 新增轻量 memory。 | Memory、上下文工程 | 只做短期上下文记忆，不夸大成长期用户画像。 |
| `graph/agent.py` | 接入 prompt 文件、memory context 和 memory 更新。 | Agent workflow、Tool Calling、Context Engineering | 生成 SQL 前结合上下文，成功后记录最近交互。 |
| `graph/workflow.py` | 构建显式 LangGraph StateGraph。 | Workflow / LangGraph 表达 | 用节点和条件边解释单 Agent 流程，后续可加重试/人工确认。 |
| `graph/nodes.py` | 新增 LangGraph 节点适配层。 | LangGraph Nodes、Graph orchestration | 节点可以被观察和单独测试，不再只是一个兜底函数。 |
| `graph/preflight.py` | 抽出模型调用前预检规则。 | Guardrails、业务边界 | 数据范围、枚举问法和不可支持问题在模型前就被处理。 |
| `graph/sql_tool.py` | 抽出 SQL 查询工具。 | Tool Calling、SQL 安全 | `query_app_data` 是唯一数据访问入口，工具层做强校验。 |
| `ui/` | 拆出前端辅助模块。 | Python 工程化、可维护性 | `app.py` 只讲页面流程，日志/图表/下载分别讲。 |
| `app.py` | 查询日志改为 `logs/query_log.csv`，补足字段。 | Observability、日志、AgentOps | 每次问数可追踪问题、SQL、校验、摘要和回答。 |
| `create_db.py` | 增加数据库导入入口。 | 工程化、运行部署 | 面试前可以一条命令重建 SQLite 数据库。 |
| `test_graph.py` | 增加无 API Key 的 smoke test。 | 测试入口、可运行性 | 即使现场没有模型 key，也能验证数据、SQL 校验和查询。 |
| `main.py` | 增加命令行单次问数入口。 | API/CLI 调用、工程可演示 | 除了 Streamlit，也能在命令行跑一条问题。 |
| `docs/resume_ai_agent.md` | 生成 AI Agent 方向简历。 | 求职匹配 | 突出 BI + SQL + LLM 应用 + Agent workflow。 |
| `docs/resume_bi_data.md` | 生成 BI 数据方向简历。 | 求职匹配 | 突出数据分析、SQL、报表、内部工具和业务理解。 |

## 4. 后续优化路线

### 1 天内可做

- 补充更多真实业务问题-SQL 示例。
- 为 SQL 执行失败增加一次自动修正重试。
- 在前端增加开发者模式，按需查看 SQL、RAG 命中和日志摘要。
- 给 `logs/query_log.csv` 增加一次简单统计脚本，查看成功率和高频问题。

### 1 周内可做

- 把 Streamlit 原型拆出 FastAPI 服务层，方便接前端或企业内部系统。
- 增加多表 schema 和表关系说明，让 Text-to-SQL 支持 join。
- 建立 30-50 条人工评测集，记录 SQL 准确率、执行成功率、回答可用性。
- 增加缓存机制，降低重复问题的 token 成本。

### 面试后继续做

- 接入向量检索或企业知识库，把字段口径、指标文档、FAQ 纳入 RAG。
- 在现有显式 LangGraph workflow 上增加失败重试、澄清问题、多工具路由。
- 增加权限、审计、多用户隔离和部署方案。
- 接入真实 BI 数据库或指标平台，但仍保留 SQL 安全边界和日志追踪。

Conventional Commit summary:
- `docs(interview): add agent project preparation guide`
