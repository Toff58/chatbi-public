from typing import TypedDict, Any


class ChatBIState(TypedDict):
    question: str
    sql: str | None
    sql_valid: bool
    summary: str | None
    result: list[dict[str, Any]] | None
    error: str | None
    answer: str | None
    rag_context: list[dict[str, Any]] | None
    metrics: dict[str, Any] | None
    clarifications: list[str] | None
    timings: dict[str, Any] | None
    debug_info: dict[str, Any] | None


