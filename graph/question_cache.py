import json
import re
import time
from pathlib import Path
from typing import Any

from config import POPULATION_BASE, TABLE_NAME
from graph.result_summary import build_local_summary
from graph.sql_tool import query_app_data


CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "frequent_question_cache.json"
_RESULT_CACHE: dict[str, dict[str, Any]] = {}


def lookup_question_cache(question: str) -> dict[str, Any] | None:
    normalized_question = normalize_question(question)
    for entry in load_question_cache_entries():
        candidates = [entry.get("question"), *(entry.get("aliases") or [])]
        if normalized_question in {normalize_question(str(candidate)) for candidate in candidates if candidate}:
            return _prepare_entry(entry)
    return None


def execute_cached_question(entry: dict[str, Any]) -> dict[str, Any]:
    cache_key = normalize_question(str(entry.get("question") or ""))
    started_at = time.perf_counter()
    if cache_key in _RESULT_CACHE:
        cached_payload = _RESULT_CACHE[cache_key]
        return {
            **cached_payload,
            "cache_hit": True,
            "cache_result_reused": True,
            "cache_lookup_ms": _elapsed_ms(started_at),
        }

    sql = str(entry.get("sql") or "")
    try:
        payload = json.loads(query_app_data.invoke({"sql": sql}))
    except Exception as exc:
        payload = {"ok": False, "error": str(exc), "rows": [], "warnings": [], "timings": {}}
    if not isinstance(payload, dict):
        payload = {"ok": False, "error": "query_app_data returned an invalid payload.", "rows": [], "warnings": [], "timings": {}}

    rows = payload.get("rows") or []
    error = payload.get("error")
    answer = str(entry.get("answer") or "").strip()
    if not answer:
        answer = build_local_summary(rows) if not error else f"SQL 查询失败：\n{error}"

    cached_payload = {
        "cache_hit": True,
        "cache_result_reused": False,
        "cache_entry_id": entry.get("id"),
        "sql": sql,
        "rows": rows,
        "error": error,
        "answer": answer,
        "warnings": payload.get("warnings") or [],
        "tool_timings": payload.get("timings") or {},
    }
    if error is None:
        _RESULT_CACHE[cache_key] = cached_payload
    return {**cached_payload, "cache_lookup_ms": _elapsed_ms(started_at)}


def load_question_cache_entries() -> list[dict[str, Any]]:
    if not CACHE_PATH.exists():
        return []
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def normalize_question(question: str) -> str:
    normalized = question.lower().strip()
    normalized = re.sub(r"[\s，,。.?？!！：:；;、]+", "", normalized)
    return normalized


def _prepare_entry(entry: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(entry)
    prepared["sql"] = str(prepared.get("sql") or "").format(
        table_name=TABLE_NAME,
        population_base=POPULATION_BASE,
    )
    return prepared


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)
