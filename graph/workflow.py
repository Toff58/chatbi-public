from langgraph.graph import END, START, StateGraph

from graph.nodes import ChatBIWorkflowNodes, route_after_preflight
from graph.state import ChatBIState


WORKFLOW_STEPS = [
    {
        "name": "retrieve_context",
        "description": "读取表结构、业务口径、few-shot 示例、字段枚举和当前 session 的轻量 memory。",
    },
    {
        "name": "preflight_guardrails",
        "description": "先判断数据范围、不可支持问题、枚举查询和明显不存在的字段。",
    },
    {
        "name": "run_sql_agent",
        "description": "通过 LangChain create_agent 驱动模型生成 SQL，并强制调用 query_app_data 工具。",
    },
    {
        "name": "query_app_data",
        "description": "工具层校验只读 SQL、字段枚举、危险关键字和人数口径，再查询 SQLite。",
    },
    {
        "name": "respond_enum_lookup",
        "description": "对字段字典、枚举取值类问题直接返回可用取值，不绕到 LLM 统计。",
    },
    {
        "name": "respond_informational",
        "description": "对超出数据边界的问题直接给出边界说明和可改问方向。",
    },
    {
        "name": "log_interaction",
        "description": "应用层写入 CSV/JSONL 日志，SQL Agent 更新当前 session 的轻量 memory；配置 Supabase 后同步云端日志。",
    },
]


def describe_workflow() -> list[dict[str, str]]:
    return [dict(step) for step in WORKFLOW_STEPS]


def build_graph():
    nodes = ChatBIWorkflowNodes()
    workflow = StateGraph(ChatBIState)
    workflow.add_node("retrieve_context", nodes.retrieve_context)
    workflow.add_node("preflight_guardrails", nodes.preflight_guardrails)
    workflow.add_node("respond_informational", nodes.respond_informational)
    workflow.add_node("respond_enum_lookup", nodes.respond_enum_lookup)
    workflow.add_node("respond_failure", nodes.respond_failure)
    workflow.add_node("run_sql_agent", nodes.run_sql_agent)

    workflow.add_edge(START, "retrieve_context")
    workflow.add_edge("retrieve_context", "preflight_guardrails")
    workflow.add_conditional_edges(
        "preflight_guardrails",
        route_after_preflight,
        {
            "informational": "respond_informational",
            "enum_lookup": "respond_enum_lookup",
            "failure": "respond_failure",
            "run_agent": "run_sql_agent",
        },
    )
    workflow.add_edge("respond_informational", END)
    workflow.add_edge("respond_enum_lookup", END)
    workflow.add_edge("respond_failure", END)
    workflow.add_edge("run_sql_agent", END)
    return workflow.compile()

