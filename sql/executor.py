import re
import sqlite3
from typing import Any

from config import DB_PATH, REQUIRED_COLUMNS, TABLE_NAME


BLOCKED_SQL_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "replace",
    "truncate",
    "attach",
    "detach",
    "pragma",
    "vacuum",
    "reindex",
}


def validate_select_sql(sql: str) -> tuple[bool, str | None]:
    normalized = sql.strip().rstrip(";")
    lowered = normalized.lower()

    if not lowered.startswith(("select", "with")):
        return False, "只允许执行 SELECT 查询。"

    if ";" in normalized:
        return False, "只允许执行单条 SQL。"

    for keyword in BLOCKED_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            return False, f"SQL 包含不允许的关键字：{keyword}"

    if not _references_table(lowered, TABLE_NAME):
        return False, f"SQL 必须查询 {TABLE_NAME} 表。"

    return True, None


def _references_table(lowered_sql: str, table_name: str) -> bool:
    table_pattern = re.escape(table_name.lower())
    return bool(re.search(rf"\b(?:from|join)\s+{table_pattern}\b", lowered_sql))


def get_connection(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(sql: str) -> list[dict[str, Any]]:
    is_valid, error = validate_select_sql(sql)
    if not is_valid:
        raise ValueError(error)

    conn = get_connection(readonly=True)

    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()

        result = [dict(row) for row in rows]
        return result
    finally:
        conn.close()


def get_schema_profile(sample_limit: int = 30) -> dict[str, Any]:
    conn = get_connection(readonly=True)
    try:
        table_info = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        columns = [{"name": row["name"], "type": row["type"]} for row in table_info]

        enum_values: dict[str, list[Any]] = {}
        sample_values: dict[str, list[Any]] = {}
        for column in REQUIRED_COLUMNS:
            if column == "ppl_cnt":
                continue
            rows = conn.execute(
                f"""
                SELECT DISTINCT {column}
                FROM {TABLE_NAME}
                WHERE {column} IS NOT NULL AND TRIM({column}) != ''
                ORDER BY {column}
                """,
            ).fetchall()
            values = [row[0] for row in rows]
            enum_values[column] = values
            sample_values[column] = values[:sample_limit]

        row_count = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        return {
            "table": TABLE_NAME,
            "columns": columns,
            "enum_values": enum_values,
            "sample_values": sample_values,
            "row_count": row_count,
        }
    finally:
        conn.close()


def validate_enum_filters(
    sql: str,
    schema_profile: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Keep literal filters on known dimensions inside the database enum values."""
    profile = schema_profile or get_schema_profile()
    enum_values = profile.get("enum_values") or profile.get("sample_values") or {}
    problems = []

    for column, values in enum_values.items():
        allowed = {str(value) for value in values}
        if not allowed:
            continue

        used_values = _extract_literal_filters(sql, column)
        invalid_values = sorted(value for value in used_values if value not in allowed)
        if invalid_values:
            rendered_values = ", ".join(repr(value) for value in invalid_values[:5])
            problems.append(f"{column}: {rendered_values}")

    if problems:
        return (
            False,
            "SQL 包含不在字段枚举中的筛选值。请只从 schema_profile.enum_values 中选择筛选值；"
            f"不合法取值：{'; '.join(problems)}",
        )
    return True, None


def _extract_literal_filters(sql: str, column: str) -> set[str]:
    values: set[str] = set()
    column_pattern = re.escape(column)
    string_pattern = r"'((?:''|[^'])*)'"

    comparison_pattern = re.compile(
        rf"\b{column_pattern}\b\s*(?:=|<>|!=|like\b)\s*{string_pattern}",
        flags=re.IGNORECASE,
    )
    values.update(_unescape_sql_string(match.group(1)) for match in comparison_pattern.finditer(sql))

    in_pattern = re.compile(
        rf"\b{column_pattern}\b\s+in\s*\(([^)]*)\)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in in_pattern.finditer(sql):
        values.update(_unescape_sql_string(value) for value in re.findall(string_pattern, match.group(1)))

    return values


def _unescape_sql_string(value: str) -> str:
    return value.replace("''", "'")
