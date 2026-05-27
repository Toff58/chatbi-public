import csv
import html
import io
import json
import math
import os
import re
import sqlite3
import uuid
import zipfile
from datetime import datetime
from numbers import Number
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st

from config import DATA_CSV_PATH, DB_PATH, IMPORT_METADATA_TABLE, TABLE_NAME
from data.import_csv_to_db import import_csv_to_sqlite
from graph.workflow import build_graph
from sql.executor import get_schema_profile


LOG_DIR = Path("logs")
QUERY_LOG_FILE = LOG_DIR / "query_log.csv"
DEBUG_LOG_FILE = LOG_DIR / "query_debug.jsonl"
SUPABASE_LOG_TABLE = "chatbi_query_logs"
SUPABASE_TIMEOUT_SECONDS = 5
APP_VERSION = "public-demo"
DATA_WINDOW = "2025-07"
HIDDEN_DISPLAY_COLUMN_FRAGMENTS = {
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
MONTH_COLUMN_NAMES = {"active_month", "month", "月份", "活跃月份"}
DISPLAY_COLUMN_LABELS = {
    "app_name": "App",
    "category": "品类",
    "category_new": "细分品类",
    "active_month": "月份",
    "city_tier": "城市等级",
    "income": "收入段",
    "gender": "性别",
    "province": "省份",
    "age": "年龄段",
    "ppl_cnt": "用户数",
    "user_count": "用户数",
    "estimated_user_count": "估算用户数",
    "female_percent": "女性占比",
}
DISPLAY_TOKEN_LABELS = {
    "estimated": "估算",
    "total": "总",
    "avg": "平均",
    "average": "平均",
    "app": "App",
    "user": "用户",
    "users": "用户",
    "count": "数",
    "cnt": "数",
    "number": "数量",
    "female": "女性",
    "male": "男性",
    "percent": "占比",
    "pct": "占比",
    "ratio": "占比",
    "share": "占比",
    "rate": "占比",
}
DICTIONARY_DIMENSION_ORDER = [
    "app_name",
    "category",
    "category_new",
    "city_tier",
    "income",
    "gender",
    "province",
    "age",
    "active_month",
]
METRIC_DICTIONARY_ROWS = [
    {
        "指标": "用户数",
        "适用问题": "某个 App 或带画像筛选的 App 排行、Top、最多等问题",
        "展示口径": "按 App 汇总满足条件的人群规模",
    },
    {
        "指标": "估算用户数",
        "适用问题": "省份、城市等级、性别、年龄、收入等宏观人群规模问题",
        "展示口径": "按有效样本占比估算总体人群规模",
    },
    {
        "指标": "占比",
        "适用问题": "性别、年龄段、收入段、城市等级等分布或比例问题",
        "展示口径": "排除缺失取值后计算有效样本内占比",
    },
]


def ensure_database() -> None:
    if not Path(DATA_CSV_PATH).exists():
        raise FileNotFoundError(f"数据库不存在，且未找到可导入的 CSV：{DATA_CSV_PATH}")

    if _database_matches_csv():
        return

    import_csv_to_sqlite(DATA_CSV_PATH, DB_PATH)


def _database_matches_csv() -> bool:
    db_file = Path(DB_PATH)
    if not db_file.exists():
        return False

    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            table_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (TABLE_NAME,),
            ).fetchone()
            if not table_exists:
                return False

            db_rows = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
            csv_rows = _csv_row_count(DATA_CSV_PATH)
            if db_rows != csv_rows:
                return False

            metadata_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (IMPORT_METADATA_TABLE,),
            ).fetchone()
            if not metadata_exists:
                return False

            metadata = conn.execute(
                f"""
                SELECT source_mtime, source_rows
                FROM {IMPORT_METADATA_TABLE}
                WHERE table_name = ?
                """,
                (TABLE_NAME,),
            ).fetchone()
            if not metadata:
                return False

            csv_mtime = Path(DATA_CSV_PATH).stat().st_mtime
            return int(metadata[1]) == csv_rows and float(metadata[0]) >= csv_mtime
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _csv_row_count(csv_path: str) -> int:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        return max(sum(1 for _ in file) - 1, 0)


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
        return


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


def build_sorted_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    hidden_columns = [
        column for column in df.columns
        if _is_hidden_display_column(str(column))
    ]
    if hidden_columns:
        df = df.drop(columns=hidden_columns)

    numeric_columns = [
        column for column in df.columns
        if pd.api.types.is_numeric_dtype(df[column])
    ]
    if numeric_columns:
        df = df.sort_values(numeric_columns[0], ascending=False)
    return df


def build_display_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    display_df = df.copy()
    display_df.columns = _unique_display_column_labels(display_df.columns)
    return display_df


def _unique_display_column_labels(columns: Any) -> list[str]:
    labels = [_display_column_label(column) for column in columns]
    counts: dict[str, int] = {}
    unique_labels = []
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
        unique_labels.append(label if counts[label] == 1 else f"{label}{counts[label]}")
    return unique_labels


def _display_label_map(columns: list[str]) -> dict[str, str]:
    return dict(zip(columns, _unique_display_column_labels(columns)))


def _display_column_label(column: Any) -> str:
    raw = str(column)
    lowered = raw.lower()
    if raw in DISPLAY_COLUMN_LABELS:
        return DISPLAY_COLUMN_LABELS[raw]
    if lowered in DISPLAY_COLUMN_LABELS:
        return DISPLAY_COLUMN_LABELS[lowered]
    if any("\u4e00" <= character <= "\u9fff" for character in raw):
        return raw
    if _is_user_count_column(raw):
        return "用户数"
    if _is_ratio_column(raw):
        return "占比"

    tokens = [token for token in re.split(r"[_\s]+", lowered) if token]
    rendered_tokens = [DISPLAY_TOKEN_LABELS.get(token, token) for token in tokens]
    if rendered_tokens and all(token in DISPLAY_TOKEN_LABELS for token in tokens):
        label = "".join(rendered_tokens)
        return label.replace("用户数数", "用户数").replace("占比占比", "占比")
    return raw.replace("_", " ").strip() or "指标"


def _chart_metric_label(column: str) -> str:
    if _is_user_count_column(column):
        return "用户规模"
    if _is_ratio_column(column):
        return "占比"
    return _display_column_label(column)


def _is_user_count_column(column: Any) -> bool:
    lowered = str(column).lower()
    if lowered in {"ppl_cnt", "user_count", "estimated_user_count"}:
        return True
    if "用户" in str(column) and any(fragment in str(column) for fragment in {"数", "人数", "规模"}):
        return True
    return "user" in lowered and any(fragment in lowered for fragment in {"count", "cnt", "number"})


def _is_hidden_display_column(column: str) -> bool:
    lowered = column.lower()
    return any(fragment in lowered for fragment in HIDDEN_DISPLAY_COLUMN_FRAGMENTS)


def build_chart_spec(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None

    df = build_sorted_dataframe(rows)
    if df.empty or len(df) <= 1:
        return None

    numeric_columns = _numeric_columns(df)
    if not numeric_columns:
        return None

    dimension_column = _pick_dimension_column(df, numeric_columns)
    if not dimension_column:
        return None

    if _is_month_column(dimension_column) and df[dimension_column].nunique(dropna=True) > 1:
        y_column = numeric_columns[0]
        chart_df = df[[dimension_column, y_column]].dropna().sort_values(dimension_column)
        return {
            "type": "line",
            "data": chart_df,
            "x_column": dimension_column,
            "y_column": y_column,
            "y_columns": [y_column],
            "x_label": _display_column_label(dimension_column),
            "y_label": _display_column_label(y_column),
            "metric_labels": _display_label_map([y_column]),
            "title": _build_chart_title("line", dimension_column, [y_column], len(chart_df)),
        }

    if len(numeric_columns) >= 2 and len(df) <= 12:
        y_columns = numeric_columns[:4]
        chart_df = df[[dimension_column, *y_columns]].dropna(subset=[dimension_column])
        if len(chart_df) > 1:
            return {
                "type": "grouped_bar",
                "data": chart_df,
                "x_column": dimension_column,
                "y_column": None,
                "y_columns": y_columns,
                "x_label": _display_column_label(dimension_column),
                "y_label": None,
                "metric_labels": _display_label_map(y_columns),
                "title": _build_chart_title("grouped_bar", dimension_column, y_columns, len(chart_df)),
            }

    y_column = numeric_columns[0]
    chart_df = df[[dimension_column, y_column]].dropna().head(10)
    if len(chart_df) <= 1:
        return None

    if _should_render_pie(chart_df, y_column):
        return {
            "type": "pie",
            "data": chart_df,
            "x_column": dimension_column,
            "y_column": y_column,
            "y_columns": [y_column],
            "x_label": _display_column_label(dimension_column),
            "y_label": _display_column_label(y_column),
            "metric_labels": _display_label_map([y_column]),
            "title": _build_chart_title("pie", dimension_column, [y_column], len(chart_df)),
        }

    return {
        "type": "bar",
        "data": chart_df,
        "x_column": dimension_column,
        "y_column": y_column,
        "y_columns": [y_column],
        "x_label": _display_column_label(dimension_column),
        "y_label": _display_column_label(y_column),
        "metric_labels": _display_label_map([y_column]),
        "title": _build_chart_title("bar", dimension_column, [y_column], len(chart_df)),
    }


def _build_chart_title(
    chart_type: str,
    x_column: str,
    y_columns: list[str],
    row_count: int | None = None,
) -> str:
    primary_metric = y_columns[0] if y_columns else "指标"
    dimension_label = _display_column_label(x_column)
    metric_label = _chart_metric_label(primary_metric)
    if chart_type == "line":
        return f"{metric_label}趋势"
    if chart_type == "grouped_bar":
        return f"不同{dimension_label}的指标对比"
    if chart_type == "pie":
        return f"{dimension_label}占比结构"
    if _is_ratio_column(primary_metric):
        return f"{dimension_label}占比分布"
    if _is_user_count_column(primary_metric):
        if str(x_column).lower() == "app_name":
            suffix = f" Top {row_count}" if row_count else ""
            return f"App 用户规模{suffix}"
        return f"不同{dimension_label}的用户规模"
    return f"不同{dimension_label}的{metric_label}对比"


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [
        column for column in df.columns
        if pd.api.types.is_numeric_dtype(df[column])
    ]


def _pick_dimension_column(df: pd.DataFrame, numeric_columns: list[str]) -> str | None:
    dimension_columns = [column for column in df.columns if column not in numeric_columns]
    if not dimension_columns:
        return None

    for preferred in ["active_month", "app_name", "category", "category_new", "province", "city_tier", "age", "income", "gender"]:
        if preferred in dimension_columns:
            return preferred
    return dimension_columns[0]


def _is_month_column(column: str) -> bool:
    return str(column).lower() in MONTH_COLUMN_NAMES


def _should_render_pie(df: pd.DataFrame, y_column: str) -> bool:
    if len(df) < 2 or len(df) > 8:
        return False
    if not _is_ratio_column(y_column):
        return False
    values = pd.to_numeric(df[y_column], errors="coerce").dropna()
    if values.empty or (values < 0).any():
        return False
    total = float(values.sum())
    return 0 < total <= 101


def _is_ratio_column(column: str) -> bool:
    lowered = str(column).lower()
    return any(fragment in lowered for fragment in RATIO_COLUMN_FRAGMENTS)


def render_chart(chart_spec: dict[str, Any]) -> None:
    chart = build_altair_chart(chart_spec)
    if chart is not None:
        st.altair_chart(chart, width="stretch")


def build_altair_chart(chart_spec: dict[str, Any]) -> alt.Chart | None:
    chart_type = chart_spec["type"]
    chart_df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_column = chart_spec["y_column"]
    x_label = chart_spec.get("x_label") or _display_column_label(x_column)
    y_label = chart_spec.get("y_label") or _display_column_label(y_column)

    if chart_type == "line" and x_column and y_column:
        chart_df[x_column] = chart_df[x_column].astype(str)
        return (
            alt.Chart(chart_df)
            .mark_line(point=True)
            .encode(
                x=alt.X(f"{x_column}:N", sort=chart_df[x_column].tolist(), title=None),
                y=alt.Y(f"{y_column}:Q", title=None),
                tooltip=[
                    alt.Tooltip(f"{x_column}:N", title=x_label),
                    alt.Tooltip(f"{y_column}:Q", title=y_label, format=","),
                ],
            )
            .properties(height=340, title=chart_spec["title"])
        )

    if chart_type == "pie" and x_column and y_column:
        chart_df[x_column] = chart_df[x_column].astype(str)
        return (
            alt.Chart(chart_df)
            .mark_arc(innerRadius=55)
            .encode(
                theta=alt.Theta(f"{y_column}:Q", title=None),
                color=alt.Color(f"{x_column}:N", title=None),
                tooltip=[
                    alt.Tooltip(f"{x_column}:N", title=x_label),
                    alt.Tooltip(f"{y_column}:Q", title=y_label, format=","),
                ],
            )
            .properties(height=360, title=chart_spec["title"])
        )

    if chart_type == "grouped_bar" and x_column:
        y_columns = chart_spec["y_columns"]
        metric_labels = chart_spec.get("metric_labels") or _display_label_map(y_columns)
        folded_df = chart_df.melt(
            id_vars=[x_column],
            value_vars=y_columns,
            var_name="metric",
            value_name="value",
        )
        folded_df["metric"] = folded_df["metric"].map(metric_labels).fillna(folded_df["metric"])
        folded_df[x_column] = folded_df[x_column].astype(str)
        return (
            alt.Chart(folded_df)
            .mark_bar()
            .encode(
                x=alt.X(f"{x_column}:N", title=None),
                y=alt.Y("value:Q", title=None),
                color=alt.Color("metric:N", title=None),
                xOffset="metric:N",
                tooltip=[
                    alt.Tooltip(f"{x_column}:N", title=x_label),
                    alt.Tooltip("metric:N", title="指标"),
                    alt.Tooltip("value:Q", title="数值", format=","),
                ],
            )
            .properties(height=360, title=chart_spec["title"])
        )

    if chart_type == "bar" and x_column and y_column:
        return build_bar_chart(
            chart_df,
            x_column,
            y_column,
            chart_spec["title"],
            x_label=x_label,
            y_label=y_label,
        )

    return None


def build_bar_chart(
    chart_df: pd.DataFrame,
    x_column: str,
    y_column: str,
    title: str,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
) -> alt.Chart:
    sorted_df = chart_df.sort_values(y_column, ascending=False).copy()
    sorted_df[x_column] = sorted_df[x_column].astype(str)
    sort_order = list(reversed(sorted_df[x_column].tolist()))
    height = max(280, min(520, len(sorted_df) * 36))
    x_label = x_label or _display_column_label(x_column)
    y_label = y_label or _display_column_label(y_column)
    chart = (
        alt.Chart(sorted_df)
        .mark_bar()
        .encode(
            y=alt.Y(f"{x_column}:N", sort=sort_order, title=None),
            x=alt.X(f"{y_column}:Q", title=None),
            tooltip=[
                alt.Tooltip(f"{x_column}:N", title=x_label),
                alt.Tooltip(f"{y_column}:Q", title=y_label, format=","),
            ],
        )
        .properties(height=height, title=title)
    )
    return chart


def render_download_buttons(
    df: pd.DataFrame,
    chart_spec: dict[str, Any] | None,
    key_prefix: str,
) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"chatbi_result_{timestamp}"
    columns = st.columns(3 if chart_spec else 2)

    with columns[0]:
        st.download_button(
            "下载 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{base_name}.csv",
            mime="text/csv",
            key=f"{key_prefix}_download_csv",
        )
    with columns[1]:
        st.download_button(
            "下载 Excel",
            data=build_excel_bytes(df),
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_download_xlsx",
        )

    if chart_spec:
        jpg_bytes = build_chart_jpg(chart_spec)
        chart_bytes = jpg_bytes or build_chart_svg(chart_spec)
        if chart_bytes:
            extension = "jpg" if jpg_bytes else "svg"
            mime = "image/jpeg" if jpg_bytes else "image/svg+xml"
            label = "下载图表 JPG" if jpg_bytes else "下载图表 SVG"
            with columns[2]:
                st.download_button(
                    label,
                    data=chart_bytes,
                    file_name=f"{base_name}_chart.{extension}",
                    mime=mime,
                    key=f"{key_prefix}_download_chart",
                )


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types())
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("xl/workbook.xml", _xlsx_workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels())
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(df))
    return output.getvalue()


def _xlsx_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""


def _xlsx_root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _xlsx_workbook() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="结果" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""


def _xlsx_workbook_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _xlsx_sheet(df: pd.DataFrame) -> str:
    rows = [_xlsx_row(1, list(df.columns))]
    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        rows.append(_xlsx_row(row_number, [row[column] for column in df.columns]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData>"
        "</worksheet>"
    )


def _xlsx_row(row_number: int, values: list[Any]) -> str:
    cells = []
    for column_index, value in enumerate(values, start=1):
        cell_ref = f"{_excel_column_name(column_index)}{row_number}"
        cells.append(_xlsx_cell(cell_ref, value))
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def _xlsx_cell(cell_ref: str, value: Any) -> str:
    if pd.isna(value):
        return f'<c r="{cell_ref}"/>'
    if isinstance(value, Number) and not isinstance(value, bool):
        return f'<c r="{cell_ref}" t="n"><v>{value}</v></c>'
    escaped = html.escape(str(value), quote=False)
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def _excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def build_chart_jpg(chart_spec: dict[str, Any]) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    if not _has_chart_image_font():
        return None

    chart_type = chart_spec["type"]
    if chart_type == "pie":
        image = _build_pie_image(chart_spec)
    elif chart_type == "line":
        image = _build_line_image(chart_spec)
    elif chart_type == "grouped_bar":
        image = _build_grouped_bar_image(chart_spec)
    else:
        image = _build_bar_image(chart_spec)

    if image is None:
        return None

    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def _build_bar_image(chart_spec: dict[str, Any]) -> Any | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_column = chart_spec["y_column"]
    if not x_column or not y_column or df.empty:
        return None

    df = df.sort_values(y_column, ascending=False).head(12)
    values = pd.to_numeric(df[y_column], errors="coerce").fillna(0)
    max_value = float(values.max())
    if max_value <= 0:
        return None

    width = 1200
    row_height = 46
    top = 100
    bottom = 44
    left = 340
    right = 180
    height = top + bottom + row_height * len(df)
    chart_width = width - left - right
    image, draw = _new_chart_image(width, height)
    _draw_image_title(draw, chart_spec["title"], width)

    label_font = _image_font(18)
    value_font = _image_font(16)
    draw.line((left, top - 8, left, height - bottom + 8), fill="#d1d5db", width=1)

    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        label = _fit_image_text(draw, row[x_column], label_font, left - 64)
        value_text = _format_number(value)
        bar_width = chart_width * value / max_value
        y = top + index * row_height
        label_width, _ = _image_text_size(draw, label, label_font)
        value_width, _ = _image_text_size(draw, value_text, value_font)
        value_x = min(left + bar_width + 12, width - 40 - value_width)
        draw.text((left - 16 - label_width, y + 13), label, fill="#374151", font=label_font)
        draw.rounded_rectangle(
            (left, y + 9, left + bar_width, y + 34),
            radius=7,
            fill="#2563eb",
        )
        draw.text((value_x, y + 14), value_text, fill="#111827", font=value_font)

    return image


def _build_grouped_bar_image(chart_spec: dict[str, Any]) -> Any | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_columns = chart_spec["y_columns"]
    if not x_column or not y_columns or df.empty:
        return None

    y_columns = y_columns[:4]
    values = pd.to_numeric(df[y_columns].stack(), errors="coerce").fillna(0)
    max_value = float(values.max()) if not values.empty else 0.0
    if max_value <= 0:
        return None

    width = 1200
    metric_height = 24
    row_height = max(60, 28 + metric_height * len(y_columns))
    top = 130
    bottom = 44
    left = 320
    right = 180
    height = top + bottom + row_height * len(df)
    chart_width = width - left - right
    image, draw = _new_chart_image(width, height)
    _draw_image_title(draw, chart_spec["title"], width)
    _draw_image_legend(draw, _chart_metric_labels(chart_spec, y_columns), 42, 78)

    label_font = _image_font(17)
    value_font = _image_font(13)
    colors = _chart_colors()

    for row_index, (_, row) in enumerate(df.iterrows()):
        y_base = top + row_index * row_height
        label = _fit_image_text(draw, row[x_column], label_font, left - 64)
        label_width, _ = _image_text_size(draw, label, label_font)
        draw.text(
            (left - 16 - label_width, y_base + row_height / 2 - 10),
            label,
            fill="#374151",
            font=label_font,
        )
        for metric_index, metric in enumerate(y_columns):
            value = _coerce_float(row[metric])
            bar_width = chart_width * value / max_value
            y = y_base + 14 + metric_index * metric_height
            value_text = _format_number(value)
            value_width, _ = _image_text_size(draw, value_text, value_font)
            value_x = min(left + bar_width + 10, width - 40 - value_width)
            draw.rounded_rectangle(
                (left, y, left + bar_width, y + 15),
                radius=5,
                fill=colors[metric_index % len(colors)],
            )
            draw.text((value_x, y - 1), value_text, fill="#111827", font=value_font)

    return image


def _build_line_image(chart_spec: dict[str, Any]) -> Any | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_column = chart_spec["y_column"]
    if not x_column or not y_column or df.empty:
        return None

    values = pd.to_numeric(df[y_column], errors="coerce").fillna(0)
    max_value = float(values.max())
    min_value = float(values.min())
    if max_value <= 0:
        return None

    width = 1200
    height = 560
    left = 120
    right = 76
    top = 104
    bottom = 106
    chart_width = width - left - right
    chart_height = height - top - bottom
    denominator = max(len(df) - 1, 1)
    value_range = max(max_value - min_value, 1)
    image, draw = _new_chart_image(width, height)
    _draw_image_title(draw, chart_spec["title"], width)

    axis_font = _image_font(14)
    label_font = _image_font(15)
    draw.line((left, height - bottom, width - right, height - bottom), fill="#9ca3af", width=1)
    draw.line((left, top, left, height - bottom), fill="#9ca3af", width=1)
    draw.text((40, top - 8), _format_number(max_value), fill="#6b7280", font=axis_font)
    draw.text((40, height - bottom - 8), _format_number(min_value), fill="#6b7280", font=axis_font)

    points = []
    label_width_limit = max(72, int(chart_width / max(len(df), 1)) - 12)
    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        x = left + chart_width * index / denominator
        y = top + chart_height * (max_value - value) / value_range
        points.append((x, y))

        label = _fit_image_text(draw, row[x_column], label_font, label_width_limit)
        label_width, _ = _image_text_size(draw, label, label_font)
        label_x = max(left, min(x - label_width / 2, width - right - label_width))
        draw.text((label_x, height - bottom + 30), label, fill="#374151", font=label_font)

    if len(points) > 1:
        draw.line(points, fill="#2563eb", width=4)
    for x, y in points:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#2563eb", outline="white", width=3)

    return image


def _build_pie_image(chart_spec: dict[str, Any]) -> Any | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_column = chart_spec["y_column"]
    if not x_column or not y_column or df.empty:
        return None

    values = pd.to_numeric(df[y_column], errors="coerce").fillna(0)
    total = float(values.sum())
    if total <= 0:
        return None

    width = 1200
    height = max(560, 150 + len(df) * 38)
    center_x = 310
    center_y = 315
    radius = 170
    image, draw = _new_chart_image(width, height)
    _draw_image_title(draw, chart_spec["title"], width)
    colors = _chart_colors()

    start_angle = -90.0
    box = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius,
    )
    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        angle = 360.0 * value / total
        draw.pieslice(box, start=start_angle, end=start_angle + angle, fill=colors[index % len(colors)])
        start_angle += angle
    draw.ellipse(
        (center_x - 74, center_y - 74, center_x + 74, center_y + 74),
        fill="white",
    )

    label_font = _image_font(18)
    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        percent = value / total * 100
        legend_y = 142 + index * 38
        color = colors[index % len(colors)]
        label = _fit_image_text(
            draw,
            f"{row[x_column]} {_format_number(value)} ({percent:.1f}%)",
            label_font,
            width - 600,
        )
        draw.rounded_rectangle((560, legend_y - 18, 580, legend_y + 2), radius=4, fill=color)
        draw.text((596, legend_y - 20), label, fill="#374151", font=label_font)

    return image


def _new_chart_image(width: int, height: int) -> tuple[Any, Any]:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), "white")
    return image, ImageDraw.Draw(image)


def _draw_image_title(draw: Any, title: str, width: int) -> None:
    font = _image_font(30, bold=True)
    title_text = _fit_image_text(draw, title, font, width - 80)
    draw.text((40, 28), title_text, fill="#111827", font=font)


def _chart_metric_labels(chart_spec: dict[str, Any], y_columns: list[str] | None = None) -> list[str]:
    columns = y_columns or chart_spec.get("y_columns") or []
    metric_labels = chart_spec.get("metric_labels") or _display_label_map(columns)
    return [metric_labels.get(column, _display_column_label(column)) for column in columns]


def _draw_image_legend(draw: Any, labels: list[str], x: int, y: int) -> None:
    font = _image_font(14)
    colors = _chart_colors()
    cursor_x = x
    for index, label in enumerate(labels):
        color = colors[index % len(colors)]
        label_text = _fit_image_text(draw, label, font, 180)
        label_width, _ = _image_text_size(draw, label_text, font)
        draw.rounded_rectangle((cursor_x, y - 10, cursor_x + 14, y + 4), radius=3, fill=color)
        draw.text((cursor_x + 22, y - 13), label_text, fill="#374151", font=font)
        cursor_x += label_width + 52


def _image_font(size: int, bold: bool = False) -> Any:
    from PIL import ImageFont

    for path in _image_font_paths(bold):
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _has_chart_image_font() -> bool:
    return any(path.exists() for path in _image_font_paths(bold=False))


def _image_font_paths(bold: bool) -> list[Path]:
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    regular_fonts = [
        font_dir / "msyh.ttc",
        font_dir / "simhei.ttf",
        font_dir / "simsun.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    bold_fonts = [
        font_dir / "msyhbd.ttc",
        font_dir / "simhei.ttf",
        font_dir / "simsun.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Bold.otf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    return bold_fonts if bold else regular_fonts


def _fit_image_text(draw: Any, value: Any, font: Any, max_width: int) -> str:
    text = str(value)
    if _image_text_size(draw, text, font)[0] <= max_width:
        return text

    suffix = "..."
    while text and _image_text_size(draw, text + suffix, font)[0] > max_width:
        text = text[:-1]
    return text + suffix if text else suffix


def _image_text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _chart_colors() -> list[str]:
    return ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#4b5563", "#db2777"]


def build_chart_svg(chart_spec: dict[str, Any]) -> bytes | None:
    chart_type = chart_spec["type"]
    if chart_type == "pie":
        return _build_pie_svg(chart_spec)
    if chart_type == "line":
        return _build_line_svg(chart_spec)
    return _build_bar_like_svg(chart_spec)


def _build_bar_like_svg(chart_spec: dict[str, Any]) -> bytes | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_columns = chart_spec["y_columns"]
    y_column = chart_spec["y_column"] or y_columns[0]
    if not x_column or not y_column or df.empty:
        return None

    df = df.sort_values(y_column, ascending=False).head(12)
    values = pd.to_numeric(df[y_column], errors="coerce").fillna(0)
    max_value = float(values.max())
    if max_value <= 0:
        return None

    width = 1080
    row_height = 36
    left = 280
    right = 180
    top = 76
    bottom = 40
    height = top + bottom + row_height * len(df)
    chart_width = width - left - right
    bars = []

    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        label = _svg_text(_truncate_svg_text(row[x_column], 30))
        value_text = _svg_text(_format_number(value))
        bar_width = chart_width * value / max_value
        y = top + index * row_height
        value_x = min(left + bar_width + 8, width - 36 - _estimate_svg_text_width(value_text, 13))
        bars.append(
            f'<text x="{left - 12}" y="{y + 22}" text-anchor="end" class="label">{label}</text>'
            f'<rect x="{left}" y="{y + 5}" width="{bar_width:.2f}" height="22" rx="4" class="bar"/>'
            f'<text x="{value_x:.2f}" y="{y + 22}" class="value">{value_text}</text>'
        )

    svg = _svg_shell(width, height, chart_spec["title"], "".join(bars))
    return svg.encode("utf-8")


def _build_line_svg(chart_spec: dict[str, Any]) -> bytes | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_column = chart_spec["y_column"]
    if not x_column or not y_column or df.empty:
        return None

    values = pd.to_numeric(df[y_column], errors="coerce").fillna(0)
    max_value = float(values.max())
    min_value = float(values.min())
    if max_value <= 0:
        return None

    width = 1080
    height = 420
    left = 84
    right = 64
    top = 84
    bottom = 88
    chart_width = width - left - right
    chart_height = height - top - bottom
    denominator = max(len(df) - 1, 1)
    value_range = max(max_value - min_value, 1)
    points = []
    labels = []

    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        x = left + chart_width * index / denominator
        y = top + chart_height * (max_value - value) / value_range
        points.append(f"{x:.2f},{y:.2f}")
        labels.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" class="point"/>'
            f'<text x="{x:.2f}" y="{height - 38}" text-anchor="middle" class="label">{_svg_text(_truncate_svg_text(row[x_column], 16))}</text>'
        )

    body = (
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" class="axis"/>'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" class="axis"/>'
        f'<polyline points="{" ".join(points)}" class="line"/>'
        f'{"".join(labels)}'
    )
    svg = _svg_shell(width, height, chart_spec["title"], body)
    return svg.encode("utf-8")


def _build_pie_svg(chart_spec: dict[str, Any]) -> bytes | None:
    df = chart_spec["data"].copy()
    x_column = chart_spec["x_column"]
    y_column = chart_spec["y_column"]
    if not x_column or not y_column or df.empty:
        return None

    values = pd.to_numeric(df[y_column], errors="coerce").fillna(0)
    total = float(values.sum())
    if total <= 0:
        return None

    width = 1080
    height = 500
    center_x = 250
    center_y = 275
    radius = 150
    colors = _chart_colors()
    start_angle = -math.pi / 2
    paths = []
    legends = []

    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        angle = 2 * math.pi * value / total
        end_angle = start_angle + angle
        color = colors[index % len(colors)]
        paths.append(_pie_slice_path(center_x, center_y, radius, start_angle, end_angle, color))
        percent = value / total * 100
        legend_y = 148 + index * 32
        legends.append(
            f'<rect x="470" y="{legend_y - 14}" width="16" height="16" rx="3" fill="{color}"/>'
            f'<text x="498" y="{legend_y}" class="label">{_svg_text(_truncate_svg_text(row[x_column], 34))} {_svg_text(f"{percent:.1f}%")}</text>'
        )
        start_angle = end_angle

    body = "".join(paths) + "".join(legends)
    svg = _svg_shell(width, height, chart_spec["title"], body)
    return svg.encode("utf-8")


def _pie_slice_path(center_x: int, center_y: int, radius: int, start: float, end: float, color: str) -> str:
    start_x = center_x + radius * math.cos(start)
    start_y = center_y + radius * math.sin(start)
    end_x = center_x + radius * math.cos(end)
    end_y = center_y + radius * math.sin(end)
    large_arc = 1 if end - start > math.pi else 0
    return (
        f'<path d="M {center_x} {center_y} L {start_x:.2f} {start_y:.2f} '
        f'A {radius} {radius} 0 {large_arc} 1 {end_x:.2f} {end_y:.2f} Z" fill="{color}"/>'
    )


def _svg_shell(width: int, height: int, title: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
  .title {{ font: 700 24px Arial, "Microsoft YaHei", sans-serif; fill: #111827; }}
  .label {{ font: 14px Arial, "Microsoft YaHei", sans-serif; fill: #374151; }}
  .value {{ font: 13px Arial, "Microsoft YaHei", sans-serif; fill: #111827; }}
  .bar {{ fill: #2563eb; }}
  .axis {{ stroke: #9ca3af; stroke-width: 1; }}
  .line {{ fill: none; stroke: #2563eb; stroke-width: 3; }}
  .point {{ fill: #2563eb; stroke: white; stroke-width: 2; }}
</style>
<rect width="100%" height="100%" fill="white"/>
<text x="40" y="42" class="title">{_svg_text(title)}</text>
{body}
</svg>"""


def _svg_text(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _truncate_svg_text(value: Any, max_chars: int) -> str:
    text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _estimate_svg_text_width(text: str, font_size: int) -> int:
    ascii_count = sum(1 for character in text if ord(character) < 128)
    wide_count = len(text) - ascii_count
    return int(ascii_count * font_size * 0.56 + wide_count * font_size)


def _format_number(value: float) -> str:
    if abs(value) >= 10000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:,.2f}"


def _coerce_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


@st.cache_data(show_spinner=False)
def load_data_dictionary() -> dict[str, list[Any]]:
    profile = get_schema_profile()
    enum_values = profile.get("enum_values") or {}
    return {
        field: _public_enum_values(enum_values.get(field, []))
        for field in DICTIONARY_DIMENSION_ORDER
        if enum_values.get(field)
    }


def _public_enum_values(values: list[Any]) -> list[Any]:
    hidden_values = {"", "NA", "N/A", "NULL", "NONE", "None", "null", "nan"}
    return [value for value in values if str(value).strip() not in hidden_values]


def render_dictionary_page() -> None:
    metric_tab, dimension_tab = st.tabs(["指标字典", "字段字典"])
    with metric_tab:
        st.dataframe(pd.DataFrame(METRIC_DICTIONARY_ROWS), width="stretch", hide_index=True)

    with dimension_tab:
        dictionary = load_data_dictionary()
        available_fields = [field for field in DICTIONARY_DIMENSION_ORDER if dictionary.get(field)]
        if not available_fields:
            st.info("当前没有可展示的字段取值。")
            return

        available_labels = [_display_column_label(field) for field in available_fields]
        selected_label = st.selectbox("维度", available_labels, index=0)
        selected_field = available_fields[available_labels.index(selected_label)]
        values = dictionary.get(selected_field, [])
        st.caption(f"{selected_label} 共 {len(values)} 个可用取值")
        st.dataframe(pd.DataFrame({"可用取值": values}), width="stretch", hide_index=True)


def ask(question: str, session_id: str | None = None) -> dict[str, Any]:
    app = build_graph()
    initial_state = {
        "question": question,
        "session_id": session_id,
        "sql": None,
        "sql_valid": False,
        "summary": None,
        "result": None,
        "error": None,
        "answer": None,
        "rag_context": None,
        "metrics": None,
        "clarifications": None,
        "timings": None,
        "debug_info": None,
    }
    result = app.invoke(initial_state)
    save_logs(question, result)
    return result


EXAMPLE_QUESTIONS = [
    "用户数最多的前 10 个 App 是哪些？",
    "年轻女性在休闲娱乐类 App 中使用最多的是哪个？",
    "广东省总人数是多少？",
    "女性用户占比是多少？",
    "下沉城市里高收入男性最常用的前 10 个 App 是哪些？",
]


def format_duration(milliseconds: Any) -> str:
    try:
        value = int(milliseconds)
    except (TypeError, ValueError):
        return ""
    if value >= 1000:
        return f"{value / 1000:.1f} 秒"
    return f"{value} 毫秒"


def render_answer_state(state: dict[str, Any], key_prefix: str) -> None:
    timings = state.get("timings") or {}
    rows = state.get("result") or []
    duration_text = format_duration(timings.get("total_ms"))
    if duration_text:
        st.caption(f"耗时 {duration_text} · 返回 {len(rows)} 条结果")

    for clarification in state.get("clarifications") or []:
        st.info(clarification)

    if state.get("error"):
        st.error("这次查询没有成功，请换一种问法或稍后重试。")
        return

    st.markdown("#### 结论")
    st.write(state.get("answer") or "没有生成结论。")

    if not rows:
        if not state.get("sql"):
            return
        st.info("查询没有返回数据。")
        return

    result_df = build_sorted_dataframe(rows)
    display_df = build_display_dataframe(result_df)
    chart_spec = build_chart_spec(rows)
    if chart_spec:
        chart_tab, table_tab = st.tabs(["图表", "明细"])
        with chart_tab:
            render_chart(chart_spec)
        with table_tab:
            st.dataframe(display_df, width="stretch", hide_index=True)
    else:
        st.dataframe(display_df, width="stretch", hide_index=True)

    render_download_buttons(display_df, chart_spec, key_prefix)


def run_question(question: str) -> None:
    cleaned_question = question.strip()
    if not cleaned_question:
        st.warning("请先输入问题。")
        return

    st.session_state.messages.append({"role": "user", "content": cleaned_question})
    with st.chat_message("user"):
        st.write(cleaned_question)

    with st.chat_message("assistant"):
        status = st.status("正在理解问题并检索业务口径...", expanded=False)
        state = ask(cleaned_question, st.session_state.session_id)
        status.update(label="分析完成", state="complete")
        render_answer_state(state, key_prefix=f"live_{len(st.session_state.messages)}")
    st.session_state.messages.append({"role": "assistant", "state": state})


st.set_page_config(page_title="ChatBI 智能问数", layout="wide")
st.title("ChatBI 智能问数")
st.caption("用自然语言查询 App 人群数据。公开演示版数据窗口：仅包含 2025-07。")

try:
    ensure_database()
except Exception as exc:
    st.error(str(exc))
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex

with st.sidebar:
    page = st.radio("导航", ["智能问数", "可问范围"], label_visibility="collapsed")
    st.info("公开演示版仅包含 2025-07 数据。")
    st.divider()
    if page == "智能问数":
        st.subheader("示例问题")
        for example in EXAMPLE_QUESTIONS:
            if st.button(example, use_container_width=True):
                st.session_state.pending_question = example
        st.divider()
        if st.button("清空会话", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_question = None
            st.rerun()

if page == "可问范围":
    render_dictionary_page()
    st.stop()

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            render_answer_state(message["state"], key_prefix=f"history_{index}")

prompt = st.chat_input("输入你的问题")
pending_question = st.session_state.pending_question
if pending_question:
    st.session_state.pending_question = None
    run_question(pending_question)
elif prompt:
    run_question(prompt)
