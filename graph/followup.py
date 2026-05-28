import re
from typing import Any


FOLLOWUP_MARKERS = ("呢", "那", "换成", "改成", "改为", "换到", "这个呢", "它呢")
INTENT_WORDS = (
    "占比",
    "比例",
    "分布",
    "人数",
    "用户数",
    "排行",
    "排名",
    "最多",
    "最少",
    "top",
    "Top",
    "分别",
    "多少",
    "哪些",
    "趋势",
)
SUBSTITUTABLE_COLUMNS = (
    "province",
    "income",
    "gender",
    "city_tier",
    "age",
    "category",
    "category_new",
    "app_name",
)

BUSINESS_TERM_ALIASES = {
    "income": {
        "高收入": "20K+",
        "高薪": "20K+",
        "高净值": "20K+",
        "低收入": "3000元以下",
        "低薪": "3000元以下",
    },
    "gender": {
        "男性": "男",
        "男生": "男",
        "男用户": "男",
        "女性": "女",
        "女生": "女",
        "女用户": "女",
    },
    "city_tier": {
        "一线城市": "一线城市",
        "新一线城市": "新一线城市",
        "二线城市": "二线城市",
        "三线城市": "三线城市",
        "四线城市": "四线城市",
        "五线城市": "五线城市",
        "下沉城市": "三线城市",
        "低线城市": "三线城市",
    },
}


def resolve_followup_question(
    question: str,
    memory: dict[str, Any],
    schema_profile: dict[str, Any],
) -> dict[str, Any]:
    """Resolve short follow-up questions by inheriting the last successful query."""
    previous = _latest_interaction(memory)
    if not previous:
        return _unchanged(question, "no_memory")

    detected_slots = _detect_slots(question, schema_profile)
    if not detected_slots:
        return _unchanged(question, "no_slot_detected")
    if not _looks_like_followup(question, detected_slots):
        return _unchanged(question, "standalone_question")

    previous_question = str(previous.get("question") or "").strip()
    if not previous_question:
        return _unchanged(question, "missing_previous_question")

    filters = previous.get("filters") or {}
    resolved = previous_question
    replacements = []

    for slot in detected_slots:
        column = slot["column"]
        new_value = slot["value"]
        old_values = [str(value) for value in filters.get(column, []) if value]
        replaced = False

        for old_value in old_values:
            if old_value and old_value in resolved:
                resolved = resolved.replace(old_value, new_value)
                replaced = True

        if not replaced:
            before_alias_replace = resolved
            resolved = _replace_alias_for_column(resolved, column, new_value)
            replaced = resolved != before_alias_replace

        if not replaced:
            resolved = _prepend_slot(resolved, column, new_value)

        replacements.append(
            {
                "column": column,
                "value": new_value,
                "previous_values": old_values,
            }
        )

    if resolved.strip() == previous_question:
        return _unchanged(question, "unchanged_after_resolution")

    return {
        "is_followup": True,
        "original_question": question,
        "resolved_question": resolved.strip(),
        "reason": "slot_replacement",
        "previous_question": previous_question,
        "replacements": replacements,
    }


def _latest_interaction(memory: dict[str, Any]) -> dict[str, Any] | None:
    interactions = memory.get("recent_interactions") or []
    if not interactions or not isinstance(interactions[0], dict):
        return None
    latest = interactions[0]
    if latest.get("sql") and latest.get("result_count", 0) != 0:
        return latest
    return latest if latest.get("question") else None


def _looks_like_followup(question: str, detected_slots: list[dict[str, str]]) -> bool:
    compact = _compact(question)
    if any(marker in question for marker in FOLLOWUP_MARKERS):
        return True
    if len(compact) <= 12 and not _has_intent_word(question):
        return True
    slot_text = "".join(slot["matched_text"] for slot in detected_slots)
    residue = compact
    for token in (slot_text, "呢", "那", "吗", "？", "?", "的话"):
        residue = residue.replace(_compact(token), "")
    return not residue and not _has_intent_word(question)


def _has_intent_word(question: str) -> bool:
    return any(word in question for word in INTENT_WORDS)


def _detect_slots(question: str, schema_profile: dict[str, Any]) -> list[dict[str, str]]:
    enum_values = schema_profile.get("enum_values") or schema_profile.get("sample_values") or {}
    slots = []
    used_columns = set()
    for column in SUBSTITUTABLE_COLUMNS:
        values = [str(value) for value in enum_values.get(column, []) if value]
        for value in sorted(values, key=len, reverse=True):
            if value in question:
                slots.append({"column": column, "value": value, "matched_text": value})
                used_columns.add(column)
                break

    for column, aliases in BUSINESS_TERM_ALIASES.items():
        if column in used_columns:
            continue
        for alias, value in aliases.items():
            if alias in question:
                slots.append({"column": column, "value": value, "matched_text": alias})
                used_columns.add(column)
                break
    return slots


def _replace_alias_for_column(text: str, column: str, new_value: str) -> str:
    aliases = BUSINESS_TERM_ALIASES.get(column) or {}
    for alias in aliases:
        if alias in text:
            return text.replace(alias, _display_value(column, new_value))
    return text


def _prepend_slot(text: str, column: str, value: str) -> str:
    if column == "province":
        return f"{value}{_strip_leading_same_dimension(text, 'province')}"
    if column == "gender":
        return f"{_display_value(column, value)}{_strip_leading_same_dimension(text, 'gender')}"
    if column == "income":
        return f"{_display_value(column, value)}{_strip_leading_same_dimension(text, 'income')}"
    return f"{_display_value(column, value)}的{text}"


def _strip_leading_same_dimension(text: str, column: str) -> str:
    if column == "province":
        return re.sub(r"^[\u4e00-\u9fa5]{2,4}省", "", text)
    if column == "gender":
        return re.sub(r"^(男性|女性|男生|女生|男用户|女用户)", "", text)
    if column == "income":
        return re.sub(r"^(高收入|高薪|高净值|低收入|低薪)", "", text)
    return text


def _display_value(column: str, value: str) -> str:
    if column == "income" and value == "20K+":
        return "高收入"
    if column == "income" and value == "3000元以下":
        return "低收入"
    if column == "gender" and value == "男":
        return "男性"
    if column == "gender" and value == "女":
        return "女性"
    return value


def _unchanged(question: str, reason: str) -> dict[str, Any]:
    return {
        "is_followup": False,
        "original_question": question,
        "resolved_question": question,
        "reason": reason,
        "previous_question": "",
        "replacements": [],
    }


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
