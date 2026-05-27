import csv
import json
import math
import os
from datetime import datetime
from typing import Any

import requests
import streamlit as st

from ui.constants import DEBUG_LOG_FILE, QUERY_LOG_FILE


SUPABASE_LOG_TABLE = "chatbi_query_logs"
SUPABASE_TIMEOUT_SECONDS = 5
APP_VERSION = "public-demo"
DATA_WINDOW = "2025-07"


def save_logs(question: str, state: dict[str, Any]) -> None:
    save_query_log(question, state)
    save_debug_log(question, state)
    save_supabase_log(question, state)


def save_query_log(question: str, state: dict[str, Any]) -> None:
    metrics = state.get("metrics") or {}
    QUERY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = _should_write_log_header()
    with open(QUERY_LOG_FILE, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=_log_fieldnames())
        if should_write_header:
            writer.writeheader()
        writer.writerow(
            {
                "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "session_id": state.get("session_id") or "",
                "用户问题": question,
                "生成SQL": state.get("sql") or "",
                "是否校验通过": state.get("sql_valid", ""),
                "查询结果摘要": summarize_result_for_log(state),
                "最终回答": state.get("answer") or "",
                "错误信息": state.get("error") or "",
                "accuracy": metrics.get("accuracy", ""),
                "precision": metrics.get("precision", ""),
                "recall": metrics.get("recall", ""),
                "sql_valid": metrics.get("sql_valid", ""),
                "execution_success": metrics.get("execution_success", ""),
                "tool_called": metrics.get("tool_called", ""),
                "answer_nonempty": metrics.get("answer_nonempty", ""),
                "result_count": metrics.get("result_count", ""),
                "rag_context_count": metrics.get("rag_context_count", ""),
                "latency_ms": metrics.get("latency_ms", ""),
            }
        )


def save_debug_log(question: str, state: dict[str, Any]) -> None:
    debug_info = state.get("debug_info") or {}
    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "session_id": state.get("session_id"),
        "question": question,
        "sql": state.get("sql"),
        "answer": state.get("answer"),
        "error": state.get("error"),
        "metrics": state.get("metrics"),
        "timings": state.get("timings"),
        "clarifications": state.get("clarifications"),
        "context_usage": debug_info.get("context_usage"),
        "debug_info": debug_info,
    }
    with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def save_supabase_log(question: str, state: dict[str, Any]) -> None:
    supabase_url = _get_config_value("SUPABASE_URL").rstrip("/")
    service_role_key = _get_config_value("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        return

    metrics = state.get("metrics") or {}
    payload = {
        "session_id": state.get("session_id") or "",
        "question": question,
        "generated_sql": state.get("sql") or "",
        "sql_valid": _optional_bool(state.get("sql_valid")),
        "result_summary": summarize_result_for_log(state),
        "answer": state.get("answer") or "",
        "error": state.get("error") or "",
        "accuracy": _optional_number(metrics.get("accuracy")),
        "precision_score": _optional_number(metrics.get("precision")),
        "recall_score": _optional_number(metrics.get("recall")),
        "execution_success": _optional_bool(metrics.get("execution_success")),
        "tool_called": _optional_bool(metrics.get("tool_called")),
        "answer_nonempty": _optional_bool(metrics.get("answer_nonempty")),
        "result_count": _optional_int(metrics.get("result_count")),
        "rag_context_count": _optional_int(metrics.get("rag_context_count")),
        "latency_ms": _optional_int(metrics.get("latency_ms")),
        "app_version": APP_VERSION,
        "data_window": DATA_WINDOW,
    }
    headers = {
        "apikey": service_role_key,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    if service_role_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {service_role_key}"

    try:
        response = requests.post(
            f"{supabase_url}/rest/v1/{SUPABASE_LOG_TABLE}",
            headers=headers,
            json=payload,
            timeout=SUPABASE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Supabase log sync failed: {exc}", flush=True)


def _get_config_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in {"True", "true", "1", 1}:
        return True
    if value in {"False", "false", "0", 0}:
        return False
    return None


def _optional_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _optional_int(value: Any) -> int | None:
    number = _optional_number(value)
    if number is None:
        return None
    return int(number)


def _log_fieldnames() -> list[str]:
    return [
        "时间",
        "session_id",
        "用户问题",
        "生成SQL",
        "是否校验通过",
        "查询结果摘要",
        "最终回答",
        "错误信息",
        "accuracy",
        "precision",
        "recall",
        "sql_valid",
        "execution_success",
        "tool_called",
        "answer_nonempty",
        "result_count",
        "rag_context_count",
        "latency_ms",
    ]


def summarize_result_for_log(state: dict[str, Any]) -> str:
    if state.get("error"):
        return "查询失败"

    rows = state.get("result")
    if rows is None:
        return "未执行查询"
    if not rows:
        return "返回 0 行"

    first_row = rows[0] if isinstance(rows[0], dict) else {}
    columns = list(first_row.keys())
    column_text = "、".join(columns[:6]) if columns else "无字段"
    return f"返回 {len(rows)} 行；字段：{column_text}"


def _should_write_log_header() -> bool:
    if not os.path.exists(QUERY_LOG_FILE) or os.path.getsize(QUERY_LOG_FILE) == 0:
        return True

    with open(QUERY_LOG_FILE, "r", encoding="utf-8-sig", newline="") as file:
        first_row = next(csv.reader(file), [])
    return first_row != _log_fieldnames()
