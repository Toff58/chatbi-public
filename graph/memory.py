import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import BASE_DIR


MEMORY_PATH = BASE_DIR / "logs" / "lightweight_memory.json"
GLOBAL_MEMORY_ENV = "CHATBI_ENABLE_GLOBAL_MEMORY"
MAX_RECENT_INTERACTIONS = 5
FILTER_COLUMNS = [
    "app_name",
    "category",
    "category_new",
    "active_month",
    "city_tier",
    "income",
    "gender",
    "province",
    "age",
]


def global_memory_enabled() -> bool:
    return os.getenv(GLOBAL_MEMORY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def load_memory(path: Path = MEMORY_PATH) -> dict[str, Any]:
    if not global_memory_enabled():
        return {"recent_interactions": []}

    if not path.exists():
        return {"recent_interactions": []}

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {"recent_interactions": []}

    interactions = data.get("recent_interactions")
    if not isinstance(interactions, list):
        return {"recent_interactions": []}
    return {"recent_interactions": interactions[:MAX_RECENT_INTERACTIONS]}


def build_memory_context(memory: dict[str, Any]) -> str:
    interactions = memory.get("recent_interactions") or []
    if not interactions:
        return "无历史上下文。"

    lines = []
    for index, item in enumerate(interactions[:MAX_RECENT_INTERACTIONS], start=1):
        filters = item.get("filters") or {}
        filter_text = _format_filters(filters)
        lines.append(
            f"{index}. 最近问题：{item.get('question', '')}\n"
            f"   最近 SQL：{item.get('sql', '') or '无'}\n"
            f"   主题：{item.get('topic', '未识别')}\n"
            f"   常用筛选：{filter_text}"
        )
    return "\n".join(lines)


def update_memory(
    *,
    question: str,
    sql: str | None,
    answer: str | None,
    result: list[dict[str, Any]] | None,
    path: Path = MEMORY_PATH,
) -> None:
    if not global_memory_enabled():
        return

    memory = load_memory(path)
    interactions = memory.get("recent_interactions") or []
    item = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "sql": sql or "",
        "topic": infer_topic(question, sql),
        "filters": extract_filters(sql or ""),
        "result_count": len(result or []),
        "answer_preview": _preview(answer or ""),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(
            {"recent_interactions": [item, *interactions][:MAX_RECENT_INTERACTIONS]},
            file,
            ensure_ascii=False,
            indent=2,
        )


def infer_topic(question: str, sql: str | None) -> str:
    text = f"{question} {sql or ''}".lower()
    if any(keyword in question for keyword in ["占比", "比例", "分布"]):
        return "人群占比/分布"
    if any(keyword in question for keyword in ["最多", "排行", "Top", "top", "前"]):
        return "App 排行"
    if any(keyword in question for keyword in ["趋势", "环比", "同比", "月份", "月"]):
        return "时间范围"
    if "estimated_user_count" in text or "总人数" in question:
        return "宏观人群估算"
    return "通用问数"


def extract_filters(sql: str) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for column in FILTER_COLUMNS:
        values = sorted(_extract_column_values(sql, column))
        if values:
            filters[column] = values
    return filters


def _extract_column_values(sql: str, column: str) -> set[str]:
    values: set[str] = set()
    string_pattern = r"'((?:''|[^'])*)'"
    column_pattern = re.escape(column)

    comparison_pattern = re.compile(
        rf"\b{column_pattern}\b\s*(?:=|<>|!=|like\b)\s*{string_pattern}",
        flags=re.IGNORECASE,
    )
    values.update(_unescape(match.group(1)) for match in comparison_pattern.finditer(sql))

    in_pattern = re.compile(
        rf"\b{column_pattern}\b\s+in\s*\(([^)]*)\)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in in_pattern.finditer(sql):
        values.update(_unescape(value) for value in re.findall(string_pattern, match.group(1)))
    return values


def _unescape(value: str) -> str:
    return value.replace("''", "'")


def _format_filters(filters: dict[str, list[str]]) -> str:
    if not filters:
        return "无"
    return "; ".join(f"{column}={','.join(values)}" for column, values in filters.items())


def _preview(text: str, limit: int = 80) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."
