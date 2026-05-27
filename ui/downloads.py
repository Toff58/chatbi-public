from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from ui.chart_image_export import build_chart_jpg
from ui.chart_svg_export import build_chart_svg
from ui.excel_export import build_excel_bytes


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
