import re
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from ui.constants import MONTH_COLUMN_NAMES, RATIO_COLUMN_FRAGMENTS
from ui.dataframe import (
    _chart_metric_label,
    _display_column_label,
    _display_label_map,
    _is_user_count_column,
    build_sorted_dataframe,
)


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
