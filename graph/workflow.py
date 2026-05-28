from langgraph.graph import END, START, StateGraph

from graph.nodes import ChatBIWorkflowNodes, route_after_cache_lookup, route_after_preflight
from graph.state import ChatBIState


WORKFLOW_STEPS = [
    {
        "name": "retrieve_context",
        "description": "读取当前 session 的轻量 memory，并保留原始问题。",
    },
    {
        "name": "resolve_followup_question",
        "description": "识别省略追问，基于上一轮问题和 SQL filters 补全为完整问数问题。",
    },
    {
        "name": "lookup_question_cache",
        "description": "高频问题精确命中后跳过模型生成，直接复用缓存 SQL 和结果。"
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
        "description": "应用层写入 CSV/JSONL 日志，SQL Agent 更新当前 session 的轻量 memory。",
    },
]


def describe_workflow() -> list[dict[str, str]]:
    return [dict(step) for step in WORKFLOW_STEPS]


def build_graph():
    nodes = ChatBIWorkflowNodes()
    workflow = StateGraph(ChatBIState)
    workflow.add_node("retrieve_context", nodes.retrieve_context)
    workflow.add_node("resolve_followup_question", nodes.resolve_followup_question)
    workflow.add_node("lookup_question_cache", nodes.lookup_question_cache)
    workflow.add_node("respond_question_cache", nodes.respond_question_cache)
    workflow.add_node("preflight_guardrails", nodes.preflight_guardrails)
    workflow.add_node("respond_informational", nodes.respond_informational)
    workflow.add_node("respond_enum_lookup", nodes.respond_enum_lookup)
    workflow.add_node("respond_failure", nodes.respond_failure)
    workflow.add_node("run_sql_agent", nodes.run_sql_agent)

    workflow.add_edge(START, "retrieve_context")
    workflow.add_edge("retrieve_context", "resolve_followup_question")
    workflow.add_edge("resolve_followup_question", "lookup_question_cache")
    workflow.add_conditional_edges(
        "lookup_question_cache",
        route_after_cache_lookup,
        {
            "question_cache": "respond_question_cache",
            "preflight": "preflight_guardrails",
        },
    )
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
    workflow.add_edge("respond_question_cache", END)
    workflow.add_edge("respond_informational", END)
    workflow.add_edge("respond_enum_lookup", END)
    workflow.add_edge("respond_failure", END)
    workflow.add_edge("run_sql_agent", END)
    return workflow.compile()

