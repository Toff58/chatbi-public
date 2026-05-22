import json
from pathlib import Path
from typing import Any

from config import POPULATION_BASE, TABLE_NAME


EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "data" / "sql_examples.json"


def load_sql_examples(path: Path = EXAMPLES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        raw_examples = json.load(file)
    return [_render_example(example) for example in raw_examples]


def _render_example(example: dict[str, Any]) -> dict[str, Any]:
    rendered = dict(example)
    rendered["table"] = str(example.get("table", TABLE_NAME)).format(table_name=TABLE_NAME)
    rendered["sql"] = str(example["sql"]).format(
        table_name=TABLE_NAME,
        population_base=POPULATION_BASE,
    ).strip()
    return rendered


SQL_EXAMPLES: list[dict[str, Any]] = load_sql_examples()


def get_prompt_few_shot_examples(limit: int = 5) -> list[dict[str, Any]]:
    examples = [example for example in SQL_EXAMPLES if example.get("include_in_prompt")]
    return examples[:limit]
