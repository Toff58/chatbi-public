import csv
import html
import io
import json
import math
import os
import sqlite3
import zipfile
from datetime import datetime
from numbers import Number
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from config import DATA_CSV_PATH, DB_PATH, IMPORT_METADATA_TABLE, TABLE_NAME
from data.import_csv_to_db import import_csv_to_sqlite
from graph.workflow import build_graph


LOG_DIR = Path("logs")
QUERY_LOG_FILE = LOG_DIR / "query_log.csv"
DEBUG_LOG_FILE = LOG_DIR / "query_debug.jsonl"
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


def _log_fieldnames() -> list[str]:
    return [
        "时间",
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
            "title": "趋势图",
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
                "title": "对比图",
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
            "title": "占比图",
        }

    return {
        "type": "bar",
        "data": chart_df,
        "x_column": dimension_column,
        "y_column": y_column,
        "y_columns": [y_column],
        "title": "排行图",
    }


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

    if chart_type == "line" and x_column and y_column:
        chart_df[x_column] = chart_df[x_column].astype(str)
        return (
            alt.Chart(chart_df)
            .mark_line(point=True)
            .encode(
                x=alt.X(f"{x_column}:N", sort=chart_df[x_column].tolist(), title=None),
                y=alt.Y(f"{y_column}:Q", title=None),
                tooltip=[
                    alt.Tooltip(f"{x_column}:N", title=x_column),
                    alt.Tooltip(f"{y_column}:Q", title=y_column, format=","),
                ],
            )
            .properties(height=340)
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
                    alt.Tooltip(f"{x_column}:N", title=x_column),
                    alt.Tooltip(f"{y_column}:Q", title=y_column, format=","),
                ],
            )
            .properties(height=360)
        )

    if chart_type == "grouped_bar" and x_column:
        y_columns = chart_spec["y_columns"]
        folded_df = chart_df.melt(
            id_vars=[x_column],
            value_vars=y_columns,
            var_name="metric",
            value_name="value",
        )
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
                    alt.Tooltip(f"{x_column}:N", title=x_column),
                    alt.Tooltip("metric:N", title="指标"),
                    alt.Tooltip("value:Q", title="数值", format=","),
                ],
            )
            .properties(height=360)
        )

    if chart_type == "bar" and x_column and y_column:
        return build_bar_chart(chart_df, x_column, y_column)

    return None


def build_bar_chart(chart_df: pd.DataFrame, x_column: str, y_column: str) -> alt.Chart:
    sorted_df = chart_df.sort_values(y_column, ascending=False).copy()
    sorted_df[x_column] = sorted_df[x_column].astype(str)
    sort_order = list(reversed(sorted_df[x_column].tolist()))
    height = max(280, min(520, len(sorted_df) * 36))
    chart = (
        alt.Chart(sorted_df)
        .mark_bar()
        .encode(
            y=alt.Y(f"{x_column}:N", sort=sort_order, title=None),
            x=alt.X(f"{y_column}:Q", title=None),
            tooltip=[
                alt.Tooltip(f"{x_column}:N", title=x_column),
                alt.Tooltip(f"{y_column}:Q", title=y_column, format=","),
            ],
        )
        .properties(height=height)
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
        svg_bytes = build_chart_svg(chart_spec)
        if svg_bytes:
            with columns[2]:
                st.download_button(
                    "下载图表 SVG",
                    data=svg_bytes,
                    file_name=f"{base_name}_chart.svg",
                    mime="image/svg+xml",
                    key=f"{key_prefix}_download_svg",
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

    width = 960
    row_height = 36
    left = 220
    right = 44
    top = 44
    bottom = 40
    height = top + bottom + row_height * len(df)
    chart_width = width - left - right
    bars = []

    for index, (_, row) in enumerate(df.iterrows()):
        value = _coerce_float(row[y_column])
        label = _svg_text(row[x_column])
        bar_width = chart_width * value / max_value
        y = top + index * row_height
        bars.append(
            f'<text x="{left - 12}" y="{y + 22}" text-anchor="end" class="label">{label}</text>'
            f'<rect x="{left}" y="{y + 5}" width="{bar_width:.2f}" height="22" rx="4" class="bar"/>'
            f'<text x="{left + bar_width + 8}" y="{y + 22}" class="value">{_svg_text(_format_number(value))}</text>'
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

    width = 960
    height = 420
    left = 84
    right = 40
    top = 54
    bottom = 72
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
            f'<text x="{x:.2f}" y="{height - 34}" text-anchor="middle" class="label">{_svg_text(row[x_column])}</text>'
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

    width = 960
    height = 460
    center_x = 250
    center_y = 245
    radius = 150
    colors = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#4b5563", "#db2777"]
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
        legend_y = 128 + index * 32
        legends.append(
            f'<rect x="470" y="{legend_y - 14}" width="16" height="16" rx="3" fill="{color}"/>'
            f'<text x="498" y="{legend_y}" class="label">{_svg_text(row[x_column])} {_svg_text(f"{percent:.1f}%")}</text>'
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
<text x="32" y="32" class="title">{_svg_text(title)}</text>
{body}
</svg>"""


def _svg_text(value: Any) -> str:
    return html.escape(str(value), quote=False)


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


def ask(question: str) -> dict[str, Any]:
    app = build_graph()
    initial_state = {
        "question": question,
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
    chart_spec = build_chart_spec(rows)
    if chart_spec:
        chart_tab, table_tab = st.tabs(["图表", "明细"])
        with chart_tab:
            render_chart(chart_spec)
        with table_tab:
            st.dataframe(result_df, width="stretch", hide_index=True)
    else:
        st.dataframe(result_df, width="stretch", hide_index=True)

    render_download_buttons(result_df, chart_spec, key_prefix)


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
        state = ask(cleaned_question)
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

with st.sidebar:
    st.info("公开演示版仅包含 2025-07 数据。")
    st.divider()
    st.subheader("示例问题")
    for example in EXAMPLE_QUESTIONS:
        if st.button(example, use_container_width=True):
            st.session_state.pending_question = example
    st.divider()
    if st.button("清空会话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pending_question = None
        st.rerun()

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
