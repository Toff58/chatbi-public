import json
import re
import time
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from config import POPULATION_BASE, TABLE_NAME
from deepseek_client import DeepSeekError, build_sql_prompt
from deepseek_langchain import ChatDeepSeek, get_model_call_timings, reset_model_call_timings
from graph.business_terms import build_scope_clarifications, format_scope_context, match_business_scopes
from graph.evaluation import evaluate_run
from graph.memory import build_memory_context, load_memory, update_memory
from graph.nodes import build_local_summary
from graph.rag import format_rag_context, format_sql_examples, retrieve_sql_context, retrieve_sql_examples
from graph.state import ChatBIState
from sql.executor import execute_query, get_schema_profile, validate_enum_filters, validate_select_sql


INTERNAL_RESULT_COLUMN_FRAGMENTS = {
    "numerator",
    "denominator",
    "target_sum",
    "source_sum",
    "valid_total",
    "valid_denominator",
    "ratio_raw",
    "base_population",
    "base_count",
    "calc_",
    "_calc",
    "分子",
    "分母",
    "有效分母",
}
RATIO_COLUMN_FRAGMENTS = {"ratio", "rate", "percent", "pct", "share", "占比", "比例"}
TREND_KEYWORDS = {
    "趋势",
    "走势",
    "变化趋势",
    "月度变化",
    "按月",
    "逐月",
    "每月",
    "各月",
    "环比",
    "同比",
    "近几个月",
    "过去几个月",
    "最近几个月",
}
RELATIVE_MONTH_KEYWORDS = {"本月", "这个月", "当月", "上月", "下月", "今年", "去年"}
APP_ALIAS_TERMS = {
    "微信",
    "支付宝",
    "抖音",
    "快手",
    "淘宝",
    "天猫",
    "京东",
    "拼多多",
    "小红书",
    "微博",
    "qq",
    "百度",
    "高德",
    "美团",
    "饿了么",
    "b站",
    "哔哩哔哩",
}
CROSS_APP_RELATION_KEYWORDS = {
    "同时使用",
    "同时用",
    "共同使用",
    "共同用户",
    "共用用户",
    "都使用",
    "都用",
    "也使用",
    "也用",
    "还使用",
    "还用",
    "重合",
    "重叠",
    "交叉",
    "交集",
    "双装",
    "多装",
    "共现",
}
USER_LEVEL_SET_KEYWORDS = {
    "去重",
    "不重复",
    "覆盖用户",
    "覆盖人数",
    "用户覆盖",
    "独立用户",
    "唯一用户",
    "至少使用",
    "至少用",
    "任一app",
    "任一应用",
    "任意app",
    "任意应用",
    "人均使用",
    "人均安装",
    "平均使用几个",
    "平均安装几个",
}
UNAVAILABLE_BEHAVIOR_KEYWORDS = {
    "使用时长",
    "在线时长",
    "停留时长",
    "使用频次",
    "使用频率",
    "打开次数",
    "启动次数",
    "访问次数",
    "活跃天数",
    "留存",
    "新增",
    "卸载",
    "下载量",
    "安装量",
    "订单",
    "交易金额",
    "支付金额",
    "gmv",
    "转化",
    "漏斗",
    "点击",
    "曝光",
}
UNAVAILABLE_RELATIONSHIP_KEYWORDS = {"相关性", "相关系数", "关联度", "因果", "影响", "导致", "驱动"}
ENUM_LOOKUP_PHRASES = {
    "有哪些",
    "有什么",
    "有哪几种",
    "有哪类",
    "包括哪些",
    "包含哪些",
    "可选值",
    "取值",
    "枚举",
    "穷举",
    "列出",
    "可问范围",
    "能问哪些",
    "可以问哪些",
    "字段字典",
    "指标字典",
}
ENUM_ANALYSIS_KEYWORDS = {
    "用户数",
    "人数",
    "人口",
    "占比",
    "比例",
    "排行",
    "排名",
    "最多",
    "最高",
    "最大",
    "top",
    "前",
    "使用",
    "常用",
    "用得最多",
    "多少",
    "分布",
    "规模",
}
ENUM_DISPLAY_LABELS = {
    "app_name": "App",
    "category": "品类",
    "category_new": "细分品类",
    "active_month": "月份",
    "city_tier": "城市等级",
    "income": "收入段",
    "gender": "性别",
    "province": "省份",
    "age": "年龄段",
}
ENUM_FIELD_TERMS = [
    ("category_new", {"细分品类", "新品类", "新分类", "新类目"}),
    ("category", {"品类", "类别", "类目", "分类", "原始品类"}),
    ("province", {"省份", "省", "地区", "地域"}),
    ("city_tier", {"城市等级", "城市", "几线", "一线", "二线", "三线", "四线", "五线", "下沉", "低线"}),
    ("income", {"收入", "收入段", "薪资", "工资", "高收入", "低收入"}),
    ("gender", {"性别", "男女", "男性", "女性", "男", "女"}),
    ("age", {"年龄", "年龄段", "岁"}),
    ("active_month", {"月份", "时间", "月"}),
    ("app_name", {"app", "应用", "软件"}),
]
ANSWER_PROCESS_LINE_MARKERS = {
    "让我重新理解",
    "重新理解",
    "更合理的理解",
    "这需要先",
    "需要先筛选",
    "需要先找到",
    "所以我们需要",
    "从结果看",
    "分析过程",
    "推导过程",
}

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT = (PROMPT_DIR / "answer_generation_prompt.md").read_text(encoding="utf-8").strip().format(
    table_name=TABLE_NAME,
    population_base=POPULATION_BASE,
)


@tool
def query_app_data(sql: str) -> str:
    """Validate and execute one read-only SQLite SELECT query against the app_data table."""
    tool_started_at = time.perf_counter()
    timings: dict[str, int] = {}

    validation_started_at = time.perf_counter()
    is_valid, error = validate_select_sql(sql)
    timings["sql_validation_ms"] = _elapsed_ms(validation_started_at)
    if not is_valid:
        return _tool_response(False, error, [], timings=timings, started_at=tool_started_at)

    enum_started_at = time.perf_counter()
    has_valid_enums, enum_error = validate_enum_filters(sql)
    timings["enum_validation_ms"] = _elapsed_ms(enum_started_at)
    if not has_valid_enums:
        return _tool_response(False, enum_error, [], timings=timings, started_at=tool_started_at)

    population_started_at = time.perf_counter()
    is_population_safe, population_error = validate_population_sql(sql)
    timings["population_sql_validation_ms"] = _elapsed_ms(population_started_at)
    if not is_population_safe:
        return _tool_response(False, population_error, [], timings=timings, started_at=tool_started_at)

    try:
        execution_started_at = time.perf_counter()
        rows = execute_query(sql)
        timings["sql_execution_ms"] = _elapsed_ms(execution_started_at)
    except Exception as exc:
        return _tool_response(False, str(exc), [], timings=timings, started_at=tool_started_at)

    result_validation_started_at = time.perf_counter()
    has_valid_population_result, result_error = validate_population_result(rows)
    timings["result_validation_ms"] = _elapsed_ms(result_validation_started_at)
    if not has_valid_population_result:
        return _tool_response(False, result_error, [], timings=timings, started_at=tool_started_at)

    return _tool_response(True, None, rows, warnings=[], timings=timings, started_at=tool_started_at)


def _tool_response(
    ok: bool,
    error: str | None,
    rows: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
    timings: dict[str, int] | None = None,
    started_at: float | None = None,
) -> str:
    payload_timings = dict(timings or {})
    if started_at is not None:
        payload_timings["tool_total_ms"] = _elapsed_ms(started_at)
    return json.dumps(
        {
            "ok": ok,
            "error": error,
            "rows": rows,
            "warnings": warnings or [],
            "timings": payload_timings,
        },
        ensure_ascii=False,
    )


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _first_timing_value(items: list[dict[str, Any]], key: str) -> int:
    if not items:
        return 0
    return int(items[0].get(key) or 0)


def _last_timing_value(items: list[dict[str, Any]], key: str) -> int:
    if not items:
        return 0
    return int(items[-1].get(key) or 0)


def validate_population_sql(sql: str) -> tuple[bool, str | None]:
    if _sql_scales_population(sql):
        return (
            False,
            "ppl_cnt 在数据库里已经是实际人数，不要再乘以 10000。"
            "请直接使用 SUM(ppl_cnt) AS user_count 或原始 ppl_cnt。",
        )
    if _sql_uses_direct_macro_population_sum(sql):
        return (
            False,
            f"固定 base 人数是 {POPULATION_BASE}。宏观人群人数不能直接输出 SUM(ppl_cnt)，"
            "请先计算有效样本占比，再用 base * 占比得到 estimated_user_count；"
            "如果是某个 App 的总人数或按 app_name 排行，请在 SQL 中明确使用 app_name。",
        )
    return True, None


def validate_population_result(rows: list[dict[str, Any]]) -> tuple[bool, str | None]:
    for row_index, row in enumerate(rows, start=1):
        for column, value in row.items():
            column_name = str(column)
            normalized_column = column_name.lower()
            if any(fragment in normalized_column for fragment in INTERNAL_RESULT_COLUMN_FRAGMENTS):
                return (
                    False,
                    "最终结果不能返回 numerator、denominator、source_sum、valid_total、base "
                    "等中间计算列；请只返回用户要看的维度和最终指标。",
                )

            number = _coerce_number(value)
            if number is None or _is_ratio_column(column_name):
                continue
            if number > POPULATION_BASE:
                return (
                    False,
                    f"结果第 {row_index} 行字段 {column_name} 的人数超过 {POPULATION_BASE}。"
                    "任何人数都不能超过 base；宏观人群人数请用 base * 有效样本占比估算，"
                    "并且不要返回中间计算过程。",
                )
    return True, None


def _sql_scales_population(sql: str) -> bool:
    compact = re.sub(r"\s+", "", sql.lower())
    return bool(
        re.search(r"(?:sum\(\s*ppl_cnt\s*\)|max\(\s*ppl_cnt\s*\)|ppl_cnt)\)*\*10000(?:\.0+)?", compact)
        or re.search(r"10000(?:\.0+)?\*\(?(?:sum\(\s*ppl_cnt\s*\)|max\(\s*ppl_cnt\s*\)|ppl_cnt)", compact)
    )


def _sql_uses_direct_macro_population_sum(sql: str) -> bool:
    lowered = sql.lower()
    if not re.search(r"\bsum\s*\(\s*ppl_cnt\s*\)", lowered, flags=re.IGNORECASE):
        return False
    if "/" in lowered:
        return False
    if re.search(r"\bapp_name\b", lowered, flags=re.IGNORECASE):
        return False
    return True


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _is_ratio_column(column: str) -> bool:
    lowered = column.lower()
    return any(fragment in lowered for fragment in RATIO_COLUMN_FRAGMENTS)


class ChatBIAgentApp:
    """State-compatible wrapper around a LangChain create_agent graph."""

    def __init__(self) -> None:
        self.schema_profile = get_schema_profile()
        self.agent = create_agent(
            model=ChatDeepSeek(temperature=0),
            tools=[query_app_data],
            system_prompt=SYSTEM_PROMPT,
        )

    def invoke(self, state: ChatBIState) -> ChatBIState:
        started_at = time.perf_counter()
        question = state["question"]
        memory = load_memory()
        memory_context = build_memory_context(memory)
        matched_scopes = match_business_scopes(question)
        rag_items = retrieve_sql_context(question, self.schema_profile)
        sql_examples = retrieve_sql_examples(question)
        context_usage = self._build_context_usage(rag_items, matched_scopes, sql_examples)
        context_usage["memory_applied"] = bool(memory.get("recent_interactions"))
        context_usage["memory_item_count"] = len(memory.get("recent_interactions") or [])
        retrieval_ms = int((time.perf_counter() - started_at) * 1000)
        data_issue = self._detect_data_availability_issue(question)
        if data_issue:
            reset_model_call_timings()
            return self._informational_state(
                state,
                rag_items,
                matched_scopes,
                sql_examples,
                context_usage,
                started_at,
                retrieval_ms,
                data_issue["answer"],
                data_issue["clarifications"],
                data_issue,
            )

        data_scope_issue = self._detect_data_scope_issue(question)
        if data_scope_issue:
            reset_model_call_timings()
            return self._informational_state(
                state,
                rag_items,
                matched_scopes,
                sql_examples,
                context_usage,
                started_at,
                retrieval_ms,
                data_scope_issue["answer"],
                data_scope_issue["clarifications"],
                data_scope_issue,
            )

        enum_lookup = self._detect_enum_lookup(question)
        if enum_lookup:
            reset_model_call_timings()
            return self._enum_lookup_state(
                state,
                rag_items,
                matched_scopes,
                sql_examples,
                context_usage,
                started_at,
                retrieval_ms,
                enum_lookup,
            )

        unknown_fields = self._detect_unknown_field_tokens(question)
        if unknown_fields:
            reset_model_call_timings()
            fields = ", ".join(unknown_fields)
            return self._failure_state(
                state,
                rag_items,
                matched_scopes,
                sql_examples,
                context_usage,
                started_at,
                retrieval_ms,
                f"数据表 {TABLE_NAME} 不包含字段：{fields}",
                f"当前数据表不包含字段：{fields}。请换成已有字段后再查询。",
            )
        user_prompt = self._build_user_prompt(
            question,
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
                    question=question,
                    sql=parsed["sql"],
                    answer=parsed["answer"],
                    result=parsed["result"],
                )
            except OSError:
                pass
            total_ms = int((time.perf_counter() - started_at) * 1000)
            metrics = evaluate_run(
                question=question,
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
                    "context_usage": context_usage,
                    "data_window": self._available_months(),
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
                "context_usage": context_usage,
                "data_issue": data_issue,
                "guardrail_issue": data_issue,
                "data_window": self._available_months(),
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
                "context_usage": context_usage,
                "data_window": self._available_months(),
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
                "context_usage": context_usage,
                "enum_lookup": enum_lookup,
                "data_window": self._available_months(),
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
            "available_months": self._available_months(),
        }

    def _detect_data_availability_issue(self, question: str) -> dict[str, Any] | None:
        available_months = self._available_months()
        if not available_months:
            return None

        requested_months = self._extract_requested_months(question)
        unsupported_months = [
            month["display"]
            for month in requested_months
            if not self._month_is_available(month, available_months)
        ]

        asks_for_trend = self._asks_for_trend(question)
        if asks_for_trend and len(available_months) < 2:
            month_text = "、".join(available_months)
            return {
                "type": "trend_unavailable",
                "available_months": available_months,
                "requested_months": [month["display"] for month in requested_months],
                "answer": (
                    f"当前数据只包含 {month_text} 一个月，无法提供趋势、环比、同比或跨月变化。"
                    "可以查询 2025 年 7 月内的排行、分布、占比或单月统计。"
                ),
                "clarifications": [f"数据范围说明：当前只可查询 {month_text} 单月数据。"],
            }

        if unsupported_months:
            month_text = "、".join(available_months)
            requested_text = "、".join(dict.fromkeys(unsupported_months))
            return {
                "type": "month_unavailable",
                "available_months": available_months,
                "requested_months": [month["display"] for month in requested_months],
                "answer": (
                    f"当前数据只包含 {month_text}，无法查询 {requested_text} 的数据。"
                    "可以改问 2025 年 7 月内的单月问题。"
                ),
                "clarifications": [f"数据范围说明：当前只可查询 {month_text} 单月数据。"],
            }

        return None

    def _detect_data_scope_issue(self, question: str) -> dict[str, Any] | None:
        compact = _compact_question(question)
        app_mentions = self._mentioned_app_terms(question)

        if self._asks_for_cross_app_overlap(question, compact, app_mentions):
            return self._unsupported_scope_issue(
                "unsupported_cross_app_overlap",
                "这个问题需要知道同一个用户是否同时使用多个 App，但当前表只有 App × 画像切片的聚合人数，没有用户级 ID 或跨 App 关联字段，因此不能计算交叉重合、共同用户或某 App 用户里的其他 App 分布。",
                [
                    "可以改问“支付宝和抖音短视频分别有多少用户”",
                    "也可以改问“某类画像人群中哪些 App 用户数最多”",
                ],
            )

        if self._asks_for_user_level_set_metric(compact, app_mentions):
            return self._unsupported_scope_issue(
                "unsupported_user_level_set_metric",
                "这个问题需要用户级去重或集合关系，但当前数据只有聚合切片人数，不能判断任一/至少使用、去重覆盖、人均使用几个 App、双装或多装。",
                [
                    "可以改问“各 App 的用户规模排行”",
                    "也可以按画像条件查询 App Top 或分布",
                ],
            )

        if self._asks_for_unavailable_behavior_metric(compact):
            return self._unsupported_scope_issue(
                "unsupported_behavior_metric",
                "这个问题需要行为日志、订单或设备级明细，但当前表没有使用时长、打开次数、频次、留存、新增、卸载、下载量、订单或交易金额等字段。",
                [
                    "可以改问“某个 App 的用户数”",
                    "也可以改问“某个 App 在年龄、性别、城市等级等画像上的分布”",
                ],
            )

        if self._asks_for_unavailable_relationship_analysis(compact, app_mentions):
            return self._unsupported_scope_issue(
                "unsupported_relationship_analysis",
                "这个问题需要用户级关系、实验或时间链路数据。当前聚合切片表只能做人数、占比、画像分布和 App 排行，不能证明因果、影响、转化或相关性。",
                [
                    "可以改问“不同画像下 App 用户数如何分布”",
                    "也可以改问“某类人群里 App 用户数排名”",
                ],
            )

        return None

    def _detect_enum_lookup(self, question: str) -> dict[str, Any] | None:
        if not self._asks_for_enum_lookup(question):
            return None

        field = self._pick_enum_field(question)
        if not field:
            if self._asks_for_dictionary_lookup(question):
                return self._build_dictionary_lookup()
            return None
        return self._build_field_enum_lookup(question, field)

    def _asks_for_enum_lookup(self, question: str) -> bool:
        compact = _compact_question(question)
        has_lookup_phrase = any(_compact_question(phrase) in compact for phrase in ENUM_LOOKUP_PHRASES)
        if not has_lookup_phrase:
            return False

        strong_lookup = any(
            phrase in compact
            for phrase in {
                "取值",
                "枚举",
                "可选值",
                "可问范围",
                "字段字典",
                "指标字典",
                "能问哪些",
                "可以问哪些",
                "穷举",
                "列出",
            }
        )
        if strong_lookup:
            return True
        return not any(keyword in compact for keyword in ENUM_ANALYSIS_KEYWORDS)

    def _asks_for_dictionary_lookup(self, question: str) -> bool:
        compact = _compact_question(question)
        return any(
            phrase in compact
            for phrase in {
                "可问范围",
                "字段字典",
                "指标字典",
                "能问哪些",
                "可以问哪些",
                "有哪些字段",
                "有哪些指标",
                "有哪些维度",
            }
        )

    def _pick_enum_field(self, question: str) -> str | None:
        compact = _compact_question(question)
        for field, terms in ENUM_FIELD_TERMS:
            if any(_compact_question(term) in compact for term in terms):
                return field
        return None

    def _build_dictionary_lookup(self) -> dict[str, Any]:
        enum_values = self.schema_profile.get("enum_values") or {}
        rows = []
        for field in ENUM_DISPLAY_LABELS:
            values = _public_enum_values(enum_values.get(field, []))
            if not values:
                continue
            rows.append(
                {
                    "可问维度": ENUM_DISPLAY_LABELS[field],
                    "可用取值数": len(values),
                    "示例取值": "、".join(map(str, values[:8])),
                }
            )
        dimension_text = "、".join(row["可问维度"] for row in rows)
        return {
            "type": "dictionary_lookup",
            "sql": None,
            "rows": rows,
            "answer": f"当前可问维度包括：{dimension_text}。页面左侧的“可问范围”里可以查看完整取值。",
        }

    def _build_field_enum_lookup(self, question: str, field: str) -> dict[str, Any]:
        enum_values = self.schema_profile.get("enum_values") or {}
        all_values = _public_enum_values(enum_values.get(field, []))
        matched_values = self._mentioned_enum_values(question, all_values)
        selected_values = matched_values or all_values
        label = ENUM_DISPLAY_LABELS.get(field, field)
        sql = self._build_enum_sql(field, label, matched_values)

        try:
            rows = execute_query(sql)
        except Exception:
            rows = [{label: value} for value in selected_values]

        value_text = "、".join(str(value) for value in selected_values[:30])
        if len(selected_values) > 30:
            value_text += f"等 {len(selected_values)} 个取值"

        if field == "city_tier":
            prefix = "当前数据记录的是城市等级，不包含具体城市名称；"
        else:
            prefix = ""

        return {
            "type": "field_enum_lookup",
            "field": field,
            "display_label": label,
            "matched_values": matched_values,
            "sql": sql,
            "rows": rows,
            "answer": f"{prefix}当前可查询的{label}包括：{value_text}。",
        }

    def _mentioned_enum_values(self, question: str, values: list[Any]) -> list[Any]:
        compact = _compact_question(question)
        matched = []
        for value in values:
            if _compact_question(str(value)) in compact:
                matched.append(value)
        return matched

    def _build_enum_sql(self, field: str, label: str, matched_values: list[Any]) -> str:
        conditions = [
            f"{field} IS NOT NULL",
            f"TRIM({field}) != ''",
            f"{field} != 'NA'",
        ]
        if matched_values:
            literal_values = ", ".join(_sql_literal(value) for value in matched_values)
            conditions.append(f"{field} IN ({literal_values})")
        where_clause = " AND ".join(conditions)
        return (
            f'SELECT DISTINCT {field} AS "{label}"\n'
            f"FROM {TABLE_NAME}\n"
            f"WHERE {where_clause}\n"
            f"ORDER BY {field};"
        )

    def _mentioned_app_terms(self, question: str) -> set[str]:
        compact = _compact_question(question)
        enum_values = self.schema_profile.get("enum_values") or {}
        app_values = enum_values.get("app_name", [])
        mentions: set[str] = set()
        for app_name in app_values:
            normalized = str(app_name).strip().lower()
            if normalized and normalized in compact:
                mentions.add(str(app_name))
        for alias in APP_ALIAS_TERMS:
            if alias.lower() in compact:
                mentions.add(alias)
        return mentions

    def _asks_for_cross_app_overlap(self, question: str, compact: str, app_mentions: set[str]) -> bool:
        has_app_or_category_context = self._has_app_or_category_context(compact, app_mentions)
        if has_app_or_category_context and _contains_any_compact(compact, CROSS_APP_RELATION_KEYWORDS):
            return True

        if len(app_mentions) >= 2 and re.search(
            r"(使用|用|打开|安装|装).{0,30}(的人|用户|人群).{0,30}(使用|用|打开|安装|装)",
            compact,
        ):
            return True

        if app_mentions and re.search(
            r"(使用|用|打开|安装|装)?[^，。？！?]*?(用户|的人|人群)(中|里|里面|当中)"
            r"[^，。？！?]*(其他|其它|别的|还|也|同时|共同|哪个app|哪些app|哪款app|app最多|应用最多)",
            compact,
        ):
            return True

        if app_mentions and re.search(
            r"(使用|用|打开|安装|装)[^，。？！?]*(的人|用户|人群)[^，。？！?]*"
            r"(哪个app|哪些app|其他app|其它app|别的app|应用)",
            compact,
        ):
            return True

        return False

    def _asks_for_user_level_set_metric(self, compact: str, app_mentions: set[str]) -> bool:
        if self._has_app_or_category_context(compact, app_mentions) and _contains_any_compact(
            compact,
            USER_LEVEL_SET_KEYWORDS,
        ):
            return True

        return bool(
            re.search(r"(使用|用|安装|装).{0,8}(几个|多少个).{0,8}(app|应用)", compact)
            or re.search(r"(几个|多少个).{0,8}(app|应用).{0,8}(用户|人数)", compact)
        )

    def _asks_for_unavailable_behavior_metric(self, compact: str) -> bool:
        return _contains_any_compact(compact, UNAVAILABLE_BEHAVIOR_KEYWORDS)

    def _asks_for_unavailable_relationship_analysis(self, compact: str, app_mentions: set[str]) -> bool:
        if not _contains_any_compact(compact, UNAVAILABLE_RELATIONSHIP_KEYWORDS):
            return False
        return self._has_app_or_category_context(compact, app_mentions) or any(
            term in compact for term in {"年龄", "收入", "性别", "城市", "省份", "画像", "人群"}
        )

    def _has_app_or_category_context(self, compact: str, app_mentions: set[str]) -> bool:
        return bool(app_mentions) or any(
            term in compact
            for term in {
                "app",
                "应用",
                "品类",
                "类别",
                "类目",
                "社交",
                "购物",
                "娱乐",
                "短视频",
                "金融",
            }
        )

    def _unsupported_scope_issue(
        self,
        issue_type: str,
        reason: str,
        suggestions: list[str],
    ) -> dict[str, Any]:
        suggestion_text = "；".join(suggestions)
        return {
            "type": issue_type,
            "answer": f"当前数据不支持这个问题。{reason}可支持的问法包括：{suggestion_text}。",
            "clarifications": [f"数据边界说明：{reason}"],
        }

    def _available_months(self) -> list[str]:
        enum_values = self.schema_profile.get("enum_values") or {}
        return sorted(str(month) for month in enum_values.get("active_month", []) if month)

    def _extract_requested_months(self, question: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        seen = set()
        normalized_question = _normalize_chinese_month_text(question)

        for match in re.finditer(r"(?<!\d)(20\d{2}|\d{2})[-/.](0?[1-9]|1[0-2])(?!\d)", normalized_question):
            raw_year = int(match.group(1))
            year = raw_year if raw_year >= 100 else 2000 + raw_year
            month = int(match.group(2))
            self._append_month_match(matches, seen, year, month, f"{year:04d}-{month:02d}", False)

        for match in re.finditer(r"(?<!\d)(20\d{2}|\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月?", normalized_question):
            raw_year = int(match.group(1))
            year = raw_year if raw_year >= 100 else 2000 + raw_year
            month = int(match.group(2))
            self._append_month_match(matches, seen, year, month, f"{year:04d}-{month:02d}", False)

        for match in re.finditer(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)", normalized_question):
            year = int(match.group(1))
            month = int(match.group(2))
            self._append_month_match(matches, seen, year, month, f"{year:04d}-{month:02d}", False)

        for match in re.finditer(r"(?<!年)(?<!\d)(0?[1-9]|1[0-2])\s*月", normalized_question):
            month = int(match.group(1))
            display = f"{month}月"
            self._append_month_match(matches, seen, None, month, display, True)

        return matches

    def _append_month_match(
        self,
        matches: list[dict[str, Any]],
        seen: set[tuple[int | None, int, bool]],
        year: int | None,
        month: int,
        display: str,
        month_only: bool,
    ) -> None:
        key = (year, month, month_only)
        if key in seen:
            return
        seen.add(key)
        matches.append(
            {
                "year": year,
                "month": month,
                "display": display,
                "month_only": month_only,
            }
        )

    def _month_is_available(self, month: dict[str, Any], available_months: list[str]) -> bool:
        if month["month_only"]:
            return any(int(available_month[-2:]) == int(month["month"]) for available_month in available_months)
        requested = f"{int(month['year']):04d}-{int(month['month']):02d}"
        return requested in available_months

    def _asks_for_trend(self, question: str) -> bool:
        lowered = question.lower()
        if any(keyword in question for keyword in TREND_KEYWORDS):
            return True
        if any(keyword in question for keyword in RELATIVE_MONTH_KEYWORDS):
            return True
        return "active_month" in lowered and any(keyword in question for keyword in {"分布", "变化", "统计"})

    def _detect_unknown_field_tokens(self, question: str) -> list[str]:
        known_columns = {
            str(column.get("name", "")).lower()
            for column in self.schema_profile.get("columns", [])
            if column.get("name")
        }
        allowed_terms = {
            "app",
            "top",
            "sql",
            "select",
            "where",
            "group",
            "by",
            "order",
            "limit",
            "sum",
            "count",
            "avg",
            "max",
            "min",
            "ppl",
            "cnt",
            TABLE_NAME.lower(),
        }
        tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", question)
        unknown = []
        for token in tokens:
            normalized = token.lower()
            if normalized in known_columns or normalized in allowed_terms:
                continue
            if "_" in normalized and normalized not in unknown:
                unknown.append(normalized)
        return unknown

    def _parse_agent_result(self, agent_result: dict[str, Any]) -> dict[str, Any]:
        messages = agent_result.get("messages", [])
        tool_calls = self._extract_query_tool_calls(messages)
        sql = tool_calls[-1]["sql"] if tool_calls else self._extract_sql_from_messages(messages)
        tool_payload = self._extract_last_tool_payload(messages)
        final_answer = self._extract_final_answer(messages)

        rows = tool_payload.get("rows") if tool_payload else None
        error = tool_payload.get("error") if tool_payload else None
        sql_valid = bool(sql) and not error

        if not final_answer:
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
            "tool_called": self._has_query_tool_call(messages),
            "tool_calls": tool_calls,
            "tool_timings": tool_payload.get("timings", {}) if tool_payload else {},
            "warnings": tool_payload.get("warnings", []) if tool_payload else [],
        }

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
        return "" if _contains_backend_only_text(answer) else answer


def build_agent_app() -> ChatBIAgentApp:
    return ChatBIAgentApp()


def _normalize_chinese_month_text(text: str) -> str:
    month_map = {
        "十一": "11",
        "十二": "12",
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
        "十": "10",
    }
    normalized = text
    for chinese_month, month in month_map.items():
        normalized = normalized.replace(f"{chinese_month}月", f"{month}月")
    return normalized


def _compact_question(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _contains_any_compact(text: str, keywords: set[str]) -> bool:
    return any(keyword.lower().replace(" ", "") in text for keyword in keywords)


def _public_enum_values(values: list[Any]) -> list[Any]:
    hidden_values = {"", "NA", "N/A", "NULL", "NONE", "None", "null", "nan"}
    return [value for value in values if str(value).strip() not in hidden_values]


def _sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


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
