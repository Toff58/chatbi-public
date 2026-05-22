from graph.agent import build_agent_app


WORKFLOW_STEPS = [
    {
        "name": "retrieve_context",
        "description": "读取表结构、业务口径和 few-shot 示例；公开演示版不读取全局 memory。",
    },
    {
        "name": "generate_sql",
        "description": "由 LLM 根据用户问题和上下文生成安全 SELECT SQL。",
    },
    {
        "name": "validate_sql",
        "description": "校验只读 SQL、字段枚举、危险关键字和人数口径。",
    },
    {
        "name": "execute_sql",
        "description": "通过 query_app_data 工具查询 SQLite 数据。",
    },
    {
        "name": "generate_answer",
        "description": "根据工具返回的 JSON 生成中文业务结论。",
    },
    {
        "name": "log_interaction",
        "description": "应用层写入 CSV 查询日志和 JSONL 调试日志；公开演示版不写入全局 memory。",
    },
]


def describe_workflow() -> list[dict[str, str]]:
    return [dict(step) for step in WORKFLOW_STEPS]


def build_graph():
    return build_agent_app()

