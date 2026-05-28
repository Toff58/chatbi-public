import json
import re
import time
from typing import Any

from langchain_core.tools import tool

from config import POPULATION_BASE
from graph.vocabulary import INTERNAL_RESULT_COLUMN_FRAGMENTS, RATIO_COLUMN_FRAGMENTS
from sql.executor import execute_query, normalize_gender_share_sql, validate_enum_filters, validate_select_sql


@tool
def query_app_data(sql: str) -> str:
    """Validate and execute one read-only SQLite SELECT query against the app_data table."""
    tool_started_at = time.perf_counter()
    timings: dict[str, int] = {}
    warnings: list[str] = []

    sql, normalization_warning = normalize_gender_share_sql(sql)
    if normalization_warning:
        warnings.append(normalization_warning)

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

    return _tool_response(True, None, rows, warnings=warnings, timings=timings, started_at=tool_started_at, effective_sql=sql)

def _tool_response(
    ok: bool,
    error: str | None,
    rows: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
    timings: dict[str, int] | None = None,
    started_at: float | None = None,
    effective_sql: str | None = None,
) -> str:
    payload_timings = dict(timings or {})
    if started_at is not None:
        payload_timings["tool_total_ms"] = _elapsed_ms(started_at)
    payload = {
        "ok": ok,
        "error": error,
        "rows": rows,
        "warnings": warnings or [],
        "timings": payload_timings,
    }
    if effective_sql:
        payload["effective_sql"] = effective_sql
    return json.dumps(
        payload,
        ensure_ascii=False,
    )

def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)

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
