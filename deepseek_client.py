from pathlib import Path
from typing import Any

from config import POPULATION_BASE, REQUIRED_COLUMNS, TABLE_NAME
from graph.sql_examples import get_prompt_few_shot_examples


class DeepSeekError(RuntimeError):
    pass


PROMPT_DIR = Path(__file__).resolve().parent / "graph" / "prompts"
SQL_GENERATION_PROMPT = (PROMPT_DIR / "sql_generation_prompt.md").read_text(encoding="utf-8").strip()


def build_sql_prompt(question: str, schema_profile: dict[str, Any]) -> str:
    columns = ", ".join(REQUIRED_COLUMNS)
    value_lines = []
    enum_values = schema_profile.get("enum_values") or schema_profile.get("sample_values", {})
    available_months = [str(value) for value in enum_values.get("active_month", []) if value]
    available_month_text = "、".join(available_months) if available_months else "未识别"
    for column in REQUIRED_COLUMNS:
        if column == "ppl_cnt":
            continue
        values = enum_values.get(column, [])
        if values:
            rendered = ", ".join(repr(value) for value in values)
            value_lines.append(f"- {column}: {rendered}")

    value_text = "\n".join(value_lines)
    few_shot_text = _format_prompt_few_shots()
    return SQL_GENERATION_PROMPT.format(
        table_name=TABLE_NAME,
        columns=columns,
        field_enum_text=value_text or "无。",
        few_shot_text=few_shot_text,
        population_base=POPULATION_BASE,
        available_month_text=available_month_text,
        question=question,
    )


def _format_prompt_few_shots() -> str:
    lines = []
    for index, example in enumerate(get_prompt_few_shot_examples(), start=1):
        lines.append(
            f"{index}. 问题：{example['question']}\n"
            f"   SQL：\n{example['sql']}"
        )
    return "\n\n".join(lines) if lines else "无。"
