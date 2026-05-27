import html
import math
from typing import Any

import pandas as pd

from ui.chart_export_utils import _chart_colors, _coerce_float, _format_number


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
