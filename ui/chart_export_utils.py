import math
from typing import Any


def _chart_colors() -> list[str]:
    return ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#4b5563", "#db2777"]

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
