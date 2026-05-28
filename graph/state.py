from typing import Any, TypedDict


class ChatBIState(TypedDict, total=False):
    session_id: str | None
    original_question: str
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
    _started_at: float
    _memory: dict[str, Any]
    _memory_context: str
    _followup_resolution: dict[str, Any]
    _matched_scopes: list[dict[str, Any]]
    _sql_examples: list[dict[str, Any]]
    _context_usage: dict[str, Any]
    _retrieval_ms: int
    _route: str
    _guardrail_issue: dict[str, Any]
    _enum_lookup: dict[str, Any]
    _failure_error: str
    _failure_answer: str


