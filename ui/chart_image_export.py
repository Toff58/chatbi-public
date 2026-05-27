import io
import os
from pathlib import Path
from typing import Any

import pandas as pd

from ui.chart_export_utils import _chart_colors, _coerce_float, _format_number
from ui.dataframe import _display_column_label, _display_label_map


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
