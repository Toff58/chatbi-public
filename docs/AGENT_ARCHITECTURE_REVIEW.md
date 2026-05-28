# Agent 架构评审

评审日期：2026-05-28

参考资料：
- OpenAI Agents SDK：<https://developers.openai.com/api/docs/guides/agents>
- OpenAI Agents SDK Guardrails：<https://openai.github.io/openai-agents-python/guardrails/>
- OpenAI Agents SDK Tracing：<https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md>
- LangGraph Overview：<https://docs.langchain.com/oss/python/langgraph/overview>
- Model Context Protocol Resources：<https://modelcontextprotocol.io/docs/concepts/resources>
- Model Context Protocol Prompts：<https://modelcontextprotocol.io/docs/concepts/prompts>

## 结论

当前产品采用“显式 LangGraph workflow + 单 SQL Agent + 单 SQL 工具 + 本地 RAG 规则 + 工具层强校验”的架构，和成熟 Agent 的基本规则是匹配的：LangGraph 负责编排状态、节点和条件路由；模型负责理解和生成候选 SQL；真实数据访问被收口到工具，工具再做安全、枚举、人数口径和结果保护。

对于当前 ChatBI 的产品阶段，不建议马上拆成多 Agent。问数链路是窄任务，拆成 Planner、SQL Writer、Reviewer、Reporter 会增加成本和失败点。更合适的做法是保留单 Agent，把检索、预检、直答和 SQL 执行拆成 LangGraph 节点，继续增强 guardrail、observability、评测集和前端澄清能力。

## 已符合成熟 Agent 规则的部分

| 规则 | 当前实现 | 评价 |
| --- | --- | --- |
| 显式图编排 | `graph/workflow.py` 使用 `StateGraph` 注册节点和条件边 | 符合。项目层能观察 state、nodes、edges。 |
| 工具边界清晰 | `query_app_data` 是唯一数据查询工具 | 符合。模型不能直接访问数据库。 |
| 工具前后校验 | SQL 类型、禁用关键字、真实表引用、枚举值、人数上限、中间列暴露都在工具层校验 | 符合。比单纯 prompt 可靠。 |
| 上下文注入 | `graph/rag.py`、`graph/sql_examples.py`、`graph/business_terms.py` 提供规则、样例和业务映射 | 符合。适合本地、低复杂度 RAG。 |
| 可观测性 | `query_debug.jsonl` 和测试 CSV 记录工具调用、RAG、耗时、指标 | 基本符合。本次新增模型调用和 SQL 工具分段耗时。 |
| 安全拒绝 | 危险 SQL、未知字段、非法枚举、不可支持业务范围都有保护 | 符合。预检层和工具层分工明确。 |
| 评测闭环 | `tests/test_cases.py` 有 50 条产品级回归样例 | 已覆盖核心成功链路、枚举直答、数据边界、安全拒绝和不可支持问题；后续可继续扩到 100 条并接入自动质量看板。 |

## 与成熟 Agent 的差距

| 差距 | 影响 | 建议 |
| --- | --- | --- |
| 没有持久化线程状态 | 刷新页面后会话历史只存在 Streamlit session 内 | 如要支持长期问数，可引入持久化 conversation/thread 表。 |
| 没有人类确认节点 | 高风险查询只能靠拒绝，不能让用户确认口径 | 对“宏观人数估算”“非法枚举”“大范围词”增加澄清/确认交互。 |
| 没有结构化 SQL 输出协议 | 仍依赖模型 tool call 参数里的 SQL 字符串 | 可要求模型输出 `{sql, assumptions, chart_intent}`，工具只接收 `sql`。 |
| 没有专门的 chart planner | 前端只根据第一数值列画柱状图 | 增加图表意图字段或本地 chart selector。 |
| 没有生产级 tracing 后端 | 目前是本地 JSONL/CSV | 可接 LangSmith 或自建 trace 表，按 trace_id 串起模型、工具、前端。 |
| 没有缓存 | 相同问题重复调用模型 | 可缓存 schema profile、RAG 结果和高频问题 SQL。 |
| SQL 校验不是 AST 级 | 目前是正则和 SQLite 执行前校验 | 可引入 SQL parser 或 SQLite authorizer 做更强安全边界。 |

## MCP 判断

当前不建议引入 MCP 替换 `query_app_data`。MCP 适合连接外部资源服务、远程数据库网关、企业知识库或跨应用工具；本项目的数据源是本地 SQLite，直接用 LangChain tool 更轻、更可控。

后续如果要接真实企业数据服务，可以把 SQLite 查询能力封装为 MCP server，再让 `run_sql_agent` 通过 MCP 工具访问；但这属于集成架构升级，不是当前面试展示项目的必要复杂度。

## 架构判断

当前架构适合继续走“显式 workflow + 生产化单 Agent”路线：
- Agent 不需要拆成多个角色，但节点边界要清楚，工具层要更硬。
- RAG 不需要向量库起步，但规则、样例和字段枚举要持续产品化维护。
- 前端不应该暴露 SQL 和推理过程，但需要给用户更自然的上下文、历史和结果切换。
- 测试应从“能跑通”升级为“每条业务口径可回归、可量化、可复盘”。

## 下一步优先级

| 优先级 | 项目 | 原因 |
| --- | --- | --- |
| P0 | 将评测集从 50 条继续扩到 100 条，并按业务主题和风险分层维护 | 当前 50 条已能防主要回归，下一步重点是覆盖更多真实问法变体和多轮追问。 |
| P0 | 增加澄清机制 | 宽泛品类、非法枚举、宏观人数口径需要产品可解释。 |
| P1 | 引入结构化输出和 chart intent | 降低前端猜图表类型的随机性。 |
| P1 | 做 trace_id 串联日志 | 方便从用户问题追到模型调用、SQL、工具和前端结果。 |
| P2 | 引入持久化会话和权限 | 面向真实客户时需要多用户隔离和历史追溯。 |
