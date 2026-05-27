# 代码结构优化说明

更新时间：2026-05-28

## 结论

本次没有为了减少行数删除业务能力，而是优先拆分职责、保留功能边界。核心收益是：`app.py` 不再承载数据库、日志、图表、下载等细节；`graph/nodes.py` 重新成为 LangGraph 节点适配层；`graph/agent.py` 从“所有规则都塞一个文件”调整为 Agent 运行时。

## 改了哪里

| 文件/目录 | 改动 | 原因 |
| --- | --- | --- |
| `app.py` | 从千行级入口拆为页面编排入口 | 面试时只需要讲页面流程，细节进入 `ui/`。 |
| `ui/` | 新增数据库、日志、表格、图表、下载、Excel、JPG/SVG 导出、字段字典模块 | 前端辅助能力按职责拆分，避免入口文件和导出文件继续膨胀。 |
| `graph/workflow.py` | 使用 LangGraph `StateGraph` 显式注册节点和条件边 | 让项目层真正体现 state / nodes / edges。 |
| `graph/nodes.py` | 改为节点适配层 | 不再是单个兜底函数，能通过 `build_graph().nodes` 观察节点。 |
| `graph/preflight.py` | 抽出模型前预检规则 | 数据范围、枚举直答、未知字段和不可支持问题不再塞在 Agent 主文件。 |
| `graph/sql_tool.py` | 抽出 `query_app_data` 工具和结果保护 | 工具边界独立，更方便测试和解释。 |
| `graph/vocabulary.py` | 抽出业务词表和保护关键词 | 常量集中维护，减少 Agent 主文件噪音。 |
| `graph/result_summary.py` | 抽出本地兜底总结 | 避免 `nodes.py` 同时承担兜底和节点定义两个含义。 |

## 关于 MCP

当前没有引入 MCP。原因是本项目的数据源是本地 SQLite，核心工具是 `query_app_data`，直接作为 LangChain tool 更简单、更稳定。MCP 更适合接外部资源服务、企业知识库、远程数据库网关或跨应用工具市场；如果现在强行接 MCP，会增加部署复杂度和面试解释成本。

保留的扩展方向是：未来可以把 `query_app_data` 背后的 SQLite 查询封装成 MCP server，再让 Agent 通过 MCP 调用企业数据服务。但这属于部署集成升级，不是当前代码瘦身的必要条件。

## 验证结果

已执行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py main.py graph ui sql data tests
.\.venv\Scripts\python.exe test_graph.py
```

补充冒烟：
- “有哪些城市等级可以问？”命中 `enum_lookup` 分支，不调用模型。
- “最近几个月用户数趋势如何？”命中 `informational` 分支，不生成跨月 SQL。
