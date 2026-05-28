import re
from numbers import Number
from typing import Any

import pandas as pd

from ui.constants import (
    DISPLAY_COLUMN_LABELS,
    DISPLAY_TOKEN_LABELS,
    HIDDEN_DISPLAY_COLUMN_FRAGMENTS,
    RATIO_COLUMN_FRAGMENTS,
)


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

def _is_ratio_column(column: Any) -> bool:
    lowered = str(column).lower()
    return any(fragment in lowered for fragment in RATIO_COLUMN_FRAGMENTS)

def _is_hidden_display_column(column: str) -> bool:
    lowered = column.lower()
    return any(fragment in lowered for fragment in HIDDEN_DISPLAY_COLUMN_FRAGMENTS)
