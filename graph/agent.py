import json
import re
import time
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from config import POPULATION_BASE, TABLE_NAME
from deepseek_client import DeepSeekError, build_sql_prompt
from deepseek_langchain import ChatDeepSeek, get_model_call_timings, reset_model_call_timings
from graph.business_terms import build_scope_clarifications, format_scope_context, match_business_scopes
from graph.evaluation import evaluate_run
from graph.followup import resolve_followup_question
from graph.memory import build_memory_context, load_memory, update_memory
from graph.preflight import QuestionPreflight
from graph.result_summary import build_local_summary
from graph.sql_tool import query_app_data
from graph.vocabulary import ANSWER_PROCESS_LINE_MARKERS
from graph.rag import format_rag_context, format_sql_examples, retrieve_sql_context, retrieve_sql_examples
from graph.state import ChatBIState
from sql.executor import get_schema_profile


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT = (PROMPT_DIR / "answer_generation_prompt.md").read_text(encoding="utf-8").strip().format(
    table_name=TABLE_NAME,
    population_base=POPULATION_BASE,
)


def _first_timing_value(items: list[dict[str, Any]], key: str) -> int:
    if not items:
        return 0
    return int(items[0].get(key) or 0)


def _last_timing_value(items: list[dict[str, Any]], key: str) -> int:
    if not items:
        return 0
    return int(items[-1].get(key) or 0)


class ChatBIAgentApp:
    """State-compatible wrapper around a LangChain create_agent graph."""

    def __init__(self) -> None:
        self.schema_profile = get_schema_profile()
        self.preflight = QuestionPreflight(self.schema_profile)
        self.agent = create_agent(
            model=ChatDeepSeek(temperature=0),
            tools=[query_app_data],
            system_prompt=SYSTEM_PROMPT,
        )

    def invoke(self, state: ChatBIState) -> ChatBIState:
        """Compatibility entry point for callers that do not need graph metadata."""
        prepared_state = {**state, **self.retrieve_context(state)}
        resolved_state = {**prepared_state, **self.resolve_followup_question(prepared_state)}
        routed_state = {**resolved_state, **self.preflight_guardrails(resolved_state)}
        route = routed_state.get("_route") or "run_agent"
        if route == "informational":
            return self.respond_informational(routed_state)
        if route == "enum_lookup":
            return self.respond_enum_lookup(routed_state)
        if route == "failure":
            return self.respond_failure(routed_state)
        return self.run_sql_agent(routed_state)

    def retrieve_context(self, state: ChatBIState) -> dict[str, Any]:
        started_at = time.perf_counter()
        session_id = state.get("session_id")
        memory = load_memory(session_id=session_id)
        memory_context = build_memory_context(memory)
        retrieval_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "original_question": state.get("original_question") or state["question"],
            "_started_at": started_at,
            "_memory": memory,
            "_memory_context": memory_context,
            "_retrieval_ms": retrieval_ms,
        }

    def resolve_followup_question(self, state: ChatBIState) -> dict[str, Any]:
        started_at = float(state.get("_started_at") or time.perf_counter())
        question = state["question"]
        session_id = state.get("session_id")
        memory = state.get("_memory") or load_memory(session_id=session_id)
        memory_context = state.get("_memory_context") or build_memory_context(memory)
        resolution = resolve_followup_question(question, memory, self.schema_profile)
        resolved_question = str(resolution.get("resolved_question") or question)
        matched_scopes = match_business_scopes(resolved_question)
        rag_items = retrieve_sql_context(resolved_question, self.schema_profile)
        sql_examples = retrieve_sql_examples(resolved_question)
        context_usage = self._build_context_usage(rag_items, matched_scopes, sql_examples)
        context_usage["memory_session_id"] = session_id or "default"
        context_usage["memory_applied"] = bool(memory.get("recent_interactions"))
        context_usage["memory_item_count"] = len(memory.get("recent_interactions") or [])
        context_usage["followup_resolved"] = bool(resolution.get("is_followup"))
        context_usage["original_question"] = question
        context_usage["resolved_question"] = resolved_question
        context_usage["followup_reason"] = resolution.get("reason")
        retrieval_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "question": resolved_question,
            "original_question": state.get("original_question") or question,
            "rag_context": rag_items,
            "_memory_context": memory_context,
            "_followup_resolution": resolution,
            "_matched_scopes": matched_scopes,
            "_sql_examples": sql_examples,
            "_context_usage": context_usage,
            "_retrieval_ms": retrieval_ms,
        }

    def preflight_guardrails(self, state: ChatBIState) -> dict[str, Any]:
        question = state["question"]
        data_issue = self.preflight.detect_data_availability_issue(question)
        if data_issue:
            reset_model_call_timings()
            return {"_route": "informational", "_guardrail_issue": data_issue}

        data_scope_issue = self.preflight.detect_data_scope_issue(question)
        if data_scope_issue:
            reset_model_call_timings()
            return {"_route": "informational", "_guardrail_issue": data_scope_issue}

        enum_lookup = self.preflight.detect_enum_lookup(question)
        if enum_lookup:
            reset_model_call_timings()
            return {"_route": "enum_lookup", "_enum_lookup": enum_lookup}

        unknown_fields = self.preflight.detect_unknown_field_tokens(question)
        if unknown_fields:
            reset_model_call_timings()
            fields = ", ".join(unknown_fields)
            return {
                "_route": "failure",
                "_failure_error": f"数据表 {TABLE_NAME} 不包含字段：{fields}",
                "_failure_answer": f"当前数据表不包含字段：{fields}。请换成已有字段后再查询。",
            }

        return {"_route": "run_agent"}

    def respond_informational(self, state: ChatBIState) -> ChatBIState:
        rag_items, matched_scopes, sql_examples, context_usage, started_at, retrieval_ms, _ = self._prepared_context(state)
        issue = state.get("_guardrail_issue") or {}
        return self._informational_state(
            state,
            rag_items,
            matched_scopes,
            sql_examples,
            context_usage,
            started_at,
            retrieval_ms,
            issue.get("answer") or "当前数据不支持这个问题。",
            issue.get("clarifications") or [],
            issue,
        )

    def respond_enum_lookup(self, state: ChatBIState) -> ChatBIState:
        rag_items, matched_scopes, sql_examples, context_usage, started_at, retrieval_ms, _ = self._prepared_context(state)
        return self._enum_lookup_state(
            state,
            rag_items,
            matched_scopes,
            sql_examples,
            context_usage,
            started_at,
            retrieval_ms,
            state.get("_enum_lookup") or {},
        )

    def respond_failure(self, state: ChatBIState) -> ChatBIState:
        rag_items, matched_scopes, sql_examples, context_usage, started_at, retrieval_ms, _ = self._prepared_context(state)
        return self._failure_state(
            state,
            rag_items,
            matched_scopes,
            sql_examples,
            context_usage,
            started_at,
            retrieval_ms,
            str(state.get("_failure_error") or "Agent preflight failed."),
            str(state.get("_failure_answer") or "Agent 预检失败，请换一种问法。"),
        )

    def run_sql_agent(self, state: ChatBIState) -> ChatBIState:
        rag_items, matched_scopes, sql_examples, context_usage, started_at, retrieval_ms, memory_context = self._prepared_context(state)
        user_prompt = self._build_user_prompt(
            state["question"],
            rag_items,
            matched_scopes,
            sql_examples,
            memory_context,
        )

        try:
            reset_model_call_timings()
            model_started_at = time.perf_counter()
            agent_result = self.agent.invoke({"messages": [{"role": "user", "content": user_prompt}]})
            model_ms = int((time.perf_counter() - model_started_at) * 1000)
            model_call_timings = get_model_call_timings()
            parsed = self._parse_agent_result(agent_result)
            try:
                update_memory(
                    question=state["question"],
                    sql=parsed["sql"],
                    answer=parsed["answer"],
                    result=parsed["result"],
                    session_id=state.get("session_id"),
                )
            except OSError:
                pass
            total_ms = int((time.perf_counter() - started_at) * 1000)
            metrics = evaluate_run(
                question=state["question"],
                sql=parsed["sql"],
                result=parsed["result"],
                answer=parsed["answer"],
                error=parsed["error"],
                rag_items=rag_items,
                latency_ms=total_ms,
                tool_called=parsed["tool_called"],
            )
            timings = {
                "retrieval_ms": retrieval_ms,
                "agent_model_and_tools_ms": model_ms,
                "model_call_count": len(model_call_timings),
                "first_model_call_ms": _first_timing_value(model_call_timings, "duration_ms"),
                "final_model_call_ms": _last_timing_value(model_call_timings, "duration_ms"),
                "model_calls_total_ms": sum(
                    int(item.get("duration_ms") or 0) for item in model_call_timings
                ),
                "sql_tool_total_ms": parsed["tool_timings"].get("tool_total_ms", 0),
                "sql_execution_ms": parsed["tool_timings"].get("sql_execution_ms", 0),
                "total_ms": total_ms,
            }
            return {
                **state,
                "sql": parsed["sql"],
                "sql_valid": parsed["sql_valid"],
                "result": parsed["result"],
                "error": parsed["error"],
                "summary": parsed["answer"],
                "answer": parsed["answer"],
                "rag_context": rag_items,
                "metrics": metrics,
                "clarifications": build_scope_clarifications(matched_scopes),
                "timings": timings,
                "debug_info": {
                    "timings": timings,
                    "model_calls": model_call_timings,
                    "tool_calls": parsed["tool_calls"],
                    "tool_timings": parsed["tool_timings"],
                    "warnings": parsed["warnings"],
                    "rag_context": rag_items,
                    "matched_scopes": matched_scopes,
                    "sql_examples": sql_examples,
                    "memory_context": memory_context,
                    "original_question": state.get("original_question"),
                    "resolved_question": state.get("question"),
                    "followup_resolution": state.get("_followup_resolution"),
                    "session_id": state.get("session_id"),
                    "context_usage": context_usage,
                    "data_window": self.preflight.available_months(),
                },
            }
        except DeepSeekError as exc:
            return self._failure_state(
                state,
                rag_items,
                matched_scopes,
                sql_examples,
                context_usage,
                started_at,
                retrieval_ms,
                str(exc),
                f"模型调用失败：{exc}",
            )
        except Exception as exc:
            return self._failure_state(
                state,
                rag_items,
                matched_scopes,
                sql_examples,
                context_usage,
                started_at,
                retrieval_ms,
                str(exc),
                f"Agent 执行失败：{exc}",
            )

    def _prepared_context(
        self,
        state: ChatBIState,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], float, int, str]:
        return (
            state.get("rag_context") or [],
            state.get("_matched_scopes") or [],
            state.get("_sql_examples") or [],
            state.get("_context_usage") or {},
            float(state.get("_started_at") or time.perf_counter()),
            int(state.get("_retrieval_ms") or 0),
            str(state.get("_memory_context") or ""),
        )

    def _informational_state(
        self,
        state: ChatBIState,
        rag_items: list[dict[str, Any]],
        matched_scopes: list[dict[str, Any]],
        sql_examples: list[dict[str, Any]],
        context_usage: dict[str, Any],
        started_at: float,
        retrieval_ms: int,
        answer: str,
        extra_clarifications: list[str],
        data_issue: dict[str, Any],
    ) -> ChatBIState:
        model_call_timings = get_model_call_timings()
        total_ms = int((time.perf_counter() - started_at) * 1000)
        metrics = evaluate_run(
            question=state["question"],
            sql=None,
            result=[],
            answer=answer,
            error=None,
            rag_items=rag_items,
            latency_ms=total_ms,
            tool_called=False,
        )
        timings = {
            "retrieval_ms": retrieval_ms,
            "agent_model_and_tools_ms": 0,
            "model_call_count": 0,
            "first_model_call_ms": 0,
            "final_model_call_ms": 0,
            "model_calls_total_ms": 0,
            "sql_tool_total_ms": 0,
            "sql_execution_ms": 0,
            "total_ms": total_ms,
        }
        return {
            **state,
            "sql": None,
            "sql_valid": False,
            "result": [],
            "error": None,
            "summary": answer,
            "answer": answer,
            "rag_context": rag_items,
            "metrics": metrics,
            "clarifications": [
                *build_scope_clarifications(matched_scopes),
                *extra_clarifications,
            ],
            "timings": timings,
            "debug_info": {
                "timings": timings,
                "model_calls": model_call_timings,
                "tool_calls": [],
                "tool_timings": {},
                "rag_context": rag_items,
                "matched_scopes": matched_scopes,
                "sql_examples": sql_examples,
                "original_question": state.get("original_question"),
                "resolved_question": state.get("question"),
                "followup_resolution": state.get("_followup_resolution"),
                "session_id": state.get("session_id"),
                "context_usage": context_usage,
                "data_issue": data_issue,
                "guardrail_issue": data_issue,
                "data_window": self.preflight.available_months(),
            },
        }

    def _failure_state(
        self,
        state: ChatBIState,
        rag_items: list[dict[str, Any]],
        matched_scopes: list[dict[str, Any]],
        sql_examples: list[dict[str, Any]],
        context_usage: dict[str, Any],
        started_at: float,
        retrieval_ms: int,
        error: str,
        answer: str,
    ) -> ChatBIState:
        model_call_timings = get_model_call_timings()
        total_ms = int((time.perf_counter() - started_at) * 1000)
        metrics = evaluate_run(
            question=state["question"],
            sql=None,
            result=None,
            answer=None,
            error=error,
            rag_items=rag_items,
            latency_ms=total_ms,
            tool_called=False,
        )
        timings = {
            "retrieval_ms": retrieval_ms,
            "agent_model_and_tools_ms": sum(
                int(item.get("duration_ms") or 0) for item in model_call_timings
            ),
            "model_call_count": len(model_call_timings),
            "first_model_call_ms": _first_timing_value(model_call_timings, "duration_ms"),
            "final_model_call_ms": _last_timing_value(model_call_timings, "duration_ms"),
            "model_calls_total_ms": sum(
                int(item.get("duration_ms") or 0) for item in model_call_timings
            ),
            "sql_tool_total_ms": 0,
            "sql_execution_ms": 0,
            "total_ms": total_ms,
        }
        return {
            **state,
            "sql_valid": False,
            "error": error,
            "answer": answer,
            "rag_context": rag_items,
            "metrics": metrics,
            "clarifications": build_scope_clarifications(matched_scopes),
            "timings": timings,
            "debug_info": {
                "timings": timings,
                "model_calls": model_call_timings,
                "tool_calls": [],
                "tool_timings": {},
                "rag_context": rag_items,
                "matched_scopes": matched_scopes,
                "sql_examples": sql_examples,
                "original_question": state.get("original_question"),
                "resolved_question": state.get("question"),
                "followup_resolution": state.get("_followup_resolution"),
                "session_id": state.get("session_id"),
                "context_usage": context_usage,
                "data_window": self.preflight.available_months(),
            },
        }

    def _enum_lookup_state(
        self,
        state: ChatBIState,
        rag_items: list[dict[str, Any]],
        matched_scopes: list[dict[str, Any]],
        sql_examples: list[dict[str, Any]],
        context_usage: dict[str, Any],
        started_at: float,
        retrieval_ms: int,
        enum_lookup: dict[str, Any],
    ) -> ChatBIState:
        total_ms = int((time.perf_counter() - started_at) * 1000)
        sql = enum_lookup.get("sql")
        rows = enum_lookup.get("rows") or []
        answer = enum_lookup.get("answer") or build_local_summary(rows)
        tool_called = bool(sql)
        metrics = evaluate_run(
            question=state["question"],
            sql=sql,
            result=rows,
            answer=answer,
            error=None,
            rag_items=rag_items,
            latency_ms=total_ms,
            tool_called=tool_called,
        )
        timings = {
            "retrieval_ms": retrieval_ms,
            "agent_model_and_tools_ms": 0,
            "model_call_count": 0,
            "first_model_call_ms": 0,
            "final_model_call_ms": 0,
            "model_calls_total_ms": 0,
            "sql_tool_total_ms": 0,
            "sql_execution_ms": 0,
            "total_ms": total_ms,
        }
        return {
            **state,
            "sql": sql,
            "sql_valid": bool(sql),
            "result": rows,
            "error": None,
            "summary": answer,
            "answer": answer,
            "rag_context": rag_items,
            "metrics": metrics,
            "clarifications": build_scope_clarifications(matched_scopes),
            "timings": timings,
            "debug_info": {
                "timings": timings,
                "model_calls": [],
                "tool_calls": [],
                "tool_timings": {},
                "rag_context": rag_items,
                "matched_scopes": matched_scopes,
                "sql_examples": sql_examples,
                "original_question": state.get("original_question"),
                "resolved_question": state.get("question"),
                "followup_resolution": state.get("_followup_resolution"),
                "session_id": state.get("session_id"),
                "context_usage": context_usage,
                "enum_lookup": enum_lookup,
                "data_window": self.preflight.available_months(),
            },
        }

    def _build_user_prompt(
        self,
        question: str,
        rag_items: list[dict[str, Any]],
        matched_scopes: list[dict[str, Any]],
        sql_examples: list[dict[str, Any]],
        memory_context: str,
    ) -> str:
        sql_context = build_sql_prompt(question, self.schema_profile)
        rag_context = format_rag_context(rag_items)
        scope_context = format_scope_context(matched_scopes)
        example_context = format_sql_examples(sql_examples)
        return f"""
请按系统要求完成一次数据分析。

用户问题：
{question}

固定业务范围映射：
{scope_context}

轻量上下文记忆：
{memory_context}

RAG 检索到的业务规则：
{rag_context}

可参考的问题-SQL 示例：
{example_context}

可用数据表、字段完整枚举和 SQL 生成规则：
{sql_context}
""".strip()

    def _build_context_usage(
        self,
        rag_items: list[dict[str, Any]],
        matched_scopes: list[dict[str, Any]],
        sql_examples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        enum_values = self.schema_profile.get("enum_values") or {}
        enum_counts = {column: len(values) for column, values in enum_values.items()}
        return {
            "field_enums_applied": bool(enum_counts),
            "field_enum_source": "schema_profile.enum_values",
            "field_enum_columns": list(enum_counts.keys()),
            "field_enum_counts": enum_counts,
            "field_enum_total_values": sum(enum_counts.values()),
            "business_rules_applied": bool(rag_items or matched_scopes),
            "rag_item_ids": [item.get("id") for item in rag_items],
            "business_scope_ids": [scope.get("id") for scope in matched_scopes],
            "sql_examples_applied": bool(sql_examples),
            "sql_example_ids": [item.get("id") for item in sql_examples],
            "available_months": self.preflight.available_months(),
        }


    def _parse_agent_result(self, agent_result: dict[str, Any]) -> dict[str, Any]:
        messages = agent_result.get("messages", [])
        tool_calls = self._extract_query_tool_calls(messages)
        sql = tool_calls[-1]["sql"] if tool_calls else self._extract_sql_from_messages(messages)
        tool_payload = self._extract_last_tool_payload(messages)
        final_answer = self._extract_final_answer(messages)
        used_local_fallback = False

        if (
            (not tool_payload or tool_payload.get("error") == "Agent did not call query_app_data.")
            and sql
        ):
            tool_payload = self._execute_sql_without_agent_tool(sql)
            tool_calls = [*tool_calls, {"id": "local_sql_fallback", "sql": sql}]
            used_local_fallback = True

        rows = tool_payload.get("rows") if tool_payload else None
        error = tool_payload.get("error") if tool_payload else None
        if tool_payload and tool_payload.get("effective_sql"):
            sql = str(tool_payload["effective_sql"])
        sql_valid = bool(sql) and not error

        if not final_answer or (used_local_fallback and _contains_sql_answer(final_answer)):
            final_answer = build_local_summary(rows or []) if not error else f"SQL 查询失败：\n{error}"
        final_answer = self._sanitize_customer_answer(final_answer)
        if not final_answer:
            final_answer = build_local_summary(rows or []) if not error else f"SQL 查询失败：\n{error}"

        return {
            "sql": sql,
            "sql_valid": sql_valid,
            "result": rows or [],
            "error": error,
            "answer": final_answer,
            "tool_called": self._has_query_tool_call(messages) or used_local_fallback,
            "tool_calls": tool_calls,
            "tool_timings": tool_payload.get("timings", {}) if tool_payload else {},
            "warnings": tool_payload.get("warnings", []) if tool_payload else [],
        }

    def _execute_sql_without_agent_tool(self, sql: str) -> dict[str, Any]:
        try:
            payload = json.loads(query_app_data.invoke({"sql": sql}))
        except Exception as exc:
            return {"ok": False, "error": str(exc), "rows": [], "timings": {}}
        if isinstance(payload, dict):
            return payload
        return {"ok": False, "error": "query_app_data returned an invalid payload.", "rows": [], "timings": {}}

    def _extract_sql_from_messages(self, messages: list[Any]) -> str | None:
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            for tool_call in reversed(message.tool_calls):
                if tool_call.get("name") == "query_app_data":
                    sql = tool_call.get("args", {}).get("sql")
                    if isinstance(sql, str):
                        return sql.strip()

        for message in messages:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                match = re.search(r"```sql\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
                if match:
                    return match.group(1).strip()
        return None

    def _extract_query_tool_calls(self, messages: list[Any]) -> list[dict[str, Any]]:
        tool_calls = []
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for tool_call in message.tool_calls:
                if tool_call.get("name") != "query_app_data":
                    continue
                sql = tool_call.get("args", {}).get("sql")
                if isinstance(sql, str):
                    tool_calls.append({"id": tool_call.get("id"), "sql": sql.strip()})
        return tool_calls

    def _extract_last_tool_payload(self, messages: list[Any]) -> dict[str, Any]:
        for message in reversed(messages):
            if isinstance(message, ToolMessage):
                try:
                    payload = json.loads(str(message.content))
                except json.JSONDecodeError:
                    return {"ok": False, "error": str(message.content), "rows": [], "timings": {}}
                if isinstance(payload, dict):
                    return payload
        return {"ok": False, "error": "Agent did not call query_app_data.", "rows": [], "timings": {}}

    def _extract_final_answer(self, messages: list[Any]) -> str | None:
        for message in reversed(messages):
            if isinstance(message, AIMessage) and message.content:
                return str(message.content).strip()
        return None

    def _has_query_tool_call(self, messages: list[Any]) -> bool:
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            if any(tool_call.get("name") == "query_app_data" for tool_call in message.tool_calls):
                return True
        return False

    def _sanitize_customer_answer(self, answer: str) -> str:
        sanitized = answer.strip()
        sanitized = _strip_sql_from_answer(sanitized)
        sanitized = _strip_reasoning_process_text(sanitized)
        sanitized = re.sub(r"（[^（）]*(?:base|后端|上限|校验|系统约束)[^（）]*）", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\([^()]*(?:base|后端|上限|校验|系统约束)[^()]*\)", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(
            r"[，,；;]\s*[^。！？\n]*(?:base|backend|后端|工具规则|系统约束|校验规则|上限)[^。！？\n]*",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\s*(?:不超过|未超过|没有超过)[^。！？\n]*(?:base|上限)[^。！？\n]*[。！？]?",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized_lines = [
            line for line in sanitized.splitlines()
            if not _contains_backend_only_text(line) and not re.fullmatch(r"\s*(注|说明|备注)[:：]?\s*(结果)?\s*", line)
        ]
        sanitized = "\n".join(sanitized_lines).strip()
        if sanitized:
            return sanitized
        if _contains_backend_only_text(answer) or _contains_sql_answer(answer):
            return ""
        return answer


def build_agent_app() -> ChatBIAgentApp:
    return ChatBIAgentApp()


def _looks_like_sql_only_answer(answer: str | None) -> bool:
    if not answer:
        return False
    stripped = answer.strip().lower()
    return stripped.startswith(("```sql", "select", "with"))


def _contains_sql_answer(answer: str | None) -> bool:
    if not answer:
        return False
    return bool(
        re.search(r"```sql\s*.*?```", answer, flags=re.IGNORECASE | re.DOTALL)
        or re.search(r"(?im)^\s*(select|with)\b", answer)
    )


def _strip_sql_from_answer(answer: str) -> str:
    cleaned = re.sub(r"```sql\s*.*?```", "", answer, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"(?ims)^\s*(?:select|with)\b[\s\S]*\Z", "", cleaned)
    return cleaned.strip()


def _compact_question(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _strip_reasoning_process_text(text: str) -> str:
    if not text:
        return text

    conclusion_matches = list(re.finditer(r"(?:^|\n)\s*(?:\*\*)?结论\s*[:：]", text))
    if conclusion_matches and _contains_reasoning_process_text(text[: conclusion_matches[-1].start()]):
        text = text[conclusion_matches[-1].start() :].strip()

    lines = []
    for line in text.splitlines():
        if _contains_reasoning_process_text(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _contains_reasoning_process_text(text: str) -> bool:
    compact = _compact_question(text)
    return any(marker.lower().replace(" ", "") in compact for marker in ANSWER_PROCESS_LINE_MARKERS)


def _contains_backend_only_text(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in {"base", "backend"}):
        return True
    if any(keyword in text for keyword in {"后端", "工具规则", "系统约束", "校验规则"}):
        return True
    return "上限" in text and any(marker in text for marker in {"6亿", "六亿", "600000000"})
