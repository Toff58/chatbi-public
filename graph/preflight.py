import re
from typing import Any

from config import TABLE_NAME
from graph.vocabulary import (
    APP_ALIAS_TERMS,
    CROSS_APP_RELATION_KEYWORDS,
    ENUM_ANALYSIS_KEYWORDS,
    ENUM_DISPLAY_LABELS,
    ENUM_FIELD_TERMS,
    ENUM_LOOKUP_PHRASES,
    RELATIVE_MONTH_KEYWORDS,
    TREND_KEYWORDS,
    UNAVAILABLE_BEHAVIOR_KEYWORDS,
    UNAVAILABLE_RELATIONSHIP_KEYWORDS,
    USER_LEVEL_SET_KEYWORDS,
)
from sql.executor import execute_query


class QuestionPreflight:
    def __init__(self, schema_profile: dict[str, Any]) -> None:
        self.schema_profile = schema_profile

    def detect_data_availability_issue(self, question: str) -> dict[str, Any] | None:
        available_months = self.available_months()
        if not available_months:
            return None

        requested_months = self._extract_requested_months(question)
        unsupported_months = [
            month["display"]
            for month in requested_months
            if not self._month_is_available(month, available_months)
        ]

        asks_for_trend = self._asks_for_trend(question)
        if asks_for_trend and len(available_months) < 2:
            month_text = "、".join(available_months)
            return {
                "type": "trend_unavailable",
                "available_months": available_months,
                "requested_months": [month["display"] for month in requested_months],
                "answer": (
                    f"当前数据只包含 {month_text} 一个月，无法提供趋势、环比、同比或跨月变化。"
                    "可以查询 2025 年 7 月内的排行、分布、占比或单月统计。"
                ),
                "clarifications": [f"数据范围说明：当前只可查询 {month_text} 单月数据。"],
            }

        if unsupported_months:
            month_text = "、".join(available_months)
            requested_text = "、".join(dict.fromkeys(unsupported_months))
            return {
                "type": "month_unavailable",
                "available_months": available_months,
                "requested_months": [month["display"] for month in requested_months],
                "answer": (
                    f"当前数据只包含 {month_text}，无法查询 {requested_text} 的数据。"
                    "可以改问 2025 年 7 月内的单月问题。"
                ),
                "clarifications": [f"数据范围说明：当前只可查询 {month_text} 单月数据。"],
            }

        return None

    def detect_data_scope_issue(self, question: str) -> dict[str, Any] | None:
        compact = _compact_question(question)
        app_mentions = self._mentioned_app_terms(question)

        if self._asks_for_cross_app_overlap(question, compact, app_mentions):
            return self._unsupported_scope_issue(
                "unsupported_cross_app_overlap",
                "这个问题需要知道同一个用户是否同时使用多个 App，但当前表只有 App × 画像切片的聚合人数，没有用户级 ID 或跨 App 关联字段，因此不能计算交叉重合、共同用户或某 App 用户里的其他 App 分布。",
                [
                    "可以改问“支付宝和抖音短视频分别有多少用户”",
                    "也可以改问“某类画像人群中哪些 App 用户数最多”",
                ],
            )

        if self._asks_for_user_level_set_metric(compact, app_mentions):
            return self._unsupported_scope_issue(
                "unsupported_user_level_set_metric",
                "这个问题需要用户级去重或集合关系，但当前数据只有聚合切片人数，不能判断任一/至少使用、去重覆盖、人均使用几个 App、双装或多装。",
                [
                    "可以改问“各 App 的用户规模排行”",
                    "也可以按画像条件查询 App Top 或分布",
                ],
            )

        if self._asks_for_unavailable_behavior_metric(compact):
            return self._unsupported_scope_issue(
                "unsupported_behavior_metric",
                "这个问题需要行为日志、订单或设备级明细，但当前表没有使用时长、打开次数、频次、留存、新增、卸载、下载量、订单或交易金额等字段。",
                [
                    "可以改问“某个 App 的用户数”",
                    "也可以改问“某个 App 在年龄、性别、城市等级等画像上的分布”",
                ],
            )

        if self._asks_for_unavailable_relationship_analysis(compact, app_mentions):
            return self._unsupported_scope_issue(
                "unsupported_relationship_analysis",
                "这个问题需要用户级关系、实验或时间链路数据。当前聚合切片表只能做人数、占比、画像分布和 App 排行，不能证明因果、影响、转化或相关性。",
                [
                    "可以改问“不同画像下 App 用户数如何分布”",
                    "也可以改问“某类人群里 App 用户数排名”",
                ],
            )

        return None

    def detect_enum_lookup(self, question: str) -> dict[str, Any] | None:
        if not self._asks_for_enum_lookup(question):
            return None

        field = self._pick_enum_field(question)
        if not field:
            if self._asks_for_dictionary_lookup(question):
                return self._build_dictionary_lookup()
            return None
        return self._build_field_enum_lookup(question, field)

    def _asks_for_enum_lookup(self, question: str) -> bool:
        compact = _compact_question(question)
        has_lookup_phrase = any(_compact_question(phrase) in compact for phrase in ENUM_LOOKUP_PHRASES)
        if not has_lookup_phrase:
            return False

        strong_lookup = any(
            phrase in compact
            for phrase in {
                "取值",
                "枚举",
                "可选值",
                "可问范围",
                "字段字典",
                "指标字典",
                "能问哪些",
                "可以问哪些",
                "穷举",
                "列出",
            }
        )
        if strong_lookup:
            return True
        return not any(keyword in compact for keyword in ENUM_ANALYSIS_KEYWORDS)

    def _asks_for_dictionary_lookup(self, question: str) -> bool:
        compact = _compact_question(question)
        return any(
            phrase in compact
            for phrase in {
                "可问范围",
                "字段字典",
                "指标字典",
                "能问哪些",
                "可以问哪些",
                "有哪些字段",
                "有哪些指标",
                "有哪些维度",
            }
        )

    def _pick_enum_field(self, question: str) -> str | None:
        compact = _compact_question(question)
        for field, terms in ENUM_FIELD_TERMS:
            if any(_compact_question(term) in compact for term in terms):
                return field
        return None

    def _build_dictionary_lookup(self) -> dict[str, Any]:
        enum_values = self.schema_profile.get("enum_values") or {}
        rows = []
        for field in ENUM_DISPLAY_LABELS:
            values = _public_enum_values(enum_values.get(field, []))
            if not values:
                continue
            rows.append(
                {
                    "可问维度": ENUM_DISPLAY_LABELS[field],
                    "可用取值数": len(values),
                    "示例取值": "、".join(map(str, values[:8])),
                }
            )
        dimension_text = "、".join(row["可问维度"] for row in rows)
        return {
            "type": "dictionary_lookup",
            "sql": None,
            "rows": rows,
            "answer": f"当前可问维度包括：{dimension_text}。页面左侧的“可问范围”里可以查看完整取值。",
        }

    def _build_field_enum_lookup(self, question: str, field: str) -> dict[str, Any]:
        enum_values = self.schema_profile.get("enum_values") or {}
        all_values = _public_enum_values(enum_values.get(field, []))
        matched_values = self._mentioned_enum_values(question, all_values)
        selected_values = matched_values or all_values
        label = ENUM_DISPLAY_LABELS.get(field, field)
        sql = self._build_enum_sql(field, label, matched_values)

        try:
            rows = execute_query(sql)
        except Exception:
            rows = [{label: value} for value in selected_values]

        value_text = "、".join(str(value) for value in selected_values[:30])
        if len(selected_values) > 30:
            value_text += f"等 {len(selected_values)} 个取值"

        if field == "city_tier":
            prefix = "当前数据记录的是城市等级，不包含具体城市名称；"
        else:
            prefix = ""

        return {
            "type": "field_enum_lookup",
            "field": field,
            "display_label": label,
            "matched_values": matched_values,
            "sql": sql,
            "rows": rows,
            "answer": f"{prefix}当前可查询的{label}包括：{value_text}。",
        }

    def _mentioned_enum_values(self, question: str, values: list[Any]) -> list[Any]:
        compact = _compact_question(question)
        matched = []
        for value in values:
            if _compact_question(str(value)) in compact:
                matched.append(value)
        return matched

    def _build_enum_sql(self, field: str, label: str, matched_values: list[Any]) -> str:
        conditions = [
            f"{field} IS NOT NULL",
            f"TRIM({field}) != ''",
            f"{field} != 'NA'",
        ]
        if matched_values:
            literal_values = ", ".join(_sql_literal(value) for value in matched_values)
            conditions.append(f"{field} IN ({literal_values})")
        where_clause = " AND ".join(conditions)
        return (
            f'SELECT DISTINCT {field} AS "{label}"\n'
            f"FROM {TABLE_NAME}\n"
            f"WHERE {where_clause}\n"
            f"ORDER BY {field};"
        )

    def _mentioned_app_terms(self, question: str) -> set[str]:
        compact = _compact_question(question)
        enum_values = self.schema_profile.get("enum_values") or {}
        app_values = enum_values.get("app_name", [])
        mentions: set[str] = set()
        for app_name in app_values:
            normalized = str(app_name).strip().lower()
            if normalized and normalized in compact:
                mentions.add(str(app_name))
        for alias in APP_ALIAS_TERMS:
            if alias.lower() in compact:
                mentions.add(alias)
        return mentions

    def _asks_for_cross_app_overlap(self, question: str, compact: str, app_mentions: set[str]) -> bool:
        has_app_or_category_context = self._has_app_or_category_context(compact, app_mentions)
        if has_app_or_category_context and _contains_any_compact(compact, CROSS_APP_RELATION_KEYWORDS):
            return True

        if len(app_mentions) >= 2 and re.search(
            r"(使用|用|打开|安装|装).{0,30}(的人|用户|人群).{0,30}(使用|用|打开|安装|装)",
            compact,
        ):
            return True

        if app_mentions and re.search(
            r"(使用|用|打开|安装|装)?[^，。？！?]*?(用户|的人|人群)(中|里|里面|当中)"
            r"[^，。？！?]*(其他|其它|别的|还|也|同时|共同|哪个app|哪些app|哪款app|app最多|应用最多)",
            compact,
        ):
            return True

        if app_mentions and re.search(
            r"(使用|用|打开|安装|装)[^，。？！?]*(的人|用户|人群)[^，。？！?]*"
            r"(哪个app|哪些app|其他app|其它app|别的app|应用)",
            compact,
        ):
            return True

        return False

    def _asks_for_user_level_set_metric(self, compact: str, app_mentions: set[str]) -> bool:
        if self._has_app_or_category_context(compact, app_mentions) and _contains_any_compact(
            compact,
            USER_LEVEL_SET_KEYWORDS,
        ):
            return True

        return bool(
            re.search(r"(使用|用|安装|装).{0,8}(几个|多少个).{0,8}(app|应用)", compact)
            or re.search(r"(几个|多少个).{0,8}(app|应用).{0,8}(用户|人数)", compact)
        )

    def _asks_for_unavailable_behavior_metric(self, compact: str) -> bool:
        return _contains_any_compact(compact, UNAVAILABLE_BEHAVIOR_KEYWORDS)

    def _asks_for_unavailable_relationship_analysis(self, compact: str, app_mentions: set[str]) -> bool:
        if not _contains_any_compact(compact, UNAVAILABLE_RELATIONSHIP_KEYWORDS):
            return False
        return self._has_app_or_category_context(compact, app_mentions) or any(
            term in compact for term in {"年龄", "收入", "性别", "城市", "省份", "画像", "人群"}
        )

    def _has_app_or_category_context(self, compact: str, app_mentions: set[str]) -> bool:
        return bool(app_mentions) or any(
            term in compact
            for term in {
                "app",
                "应用",
                "品类",
                "类别",
                "类目",
                "社交",
                "购物",
                "娱乐",
                "短视频",
                "金融",
            }
        )

    def _unsupported_scope_issue(
        self,
        issue_type: str,
        reason: str,
        suggestions: list[str],
    ) -> dict[str, Any]:
        suggestion_text = "；".join(suggestions)
        return {
            "type": issue_type,
            "answer": f"当前数据不支持这个问题。{reason}可支持的问法包括：{suggestion_text}。",
            "clarifications": [f"数据边界说明：{reason}"],
        }

    def available_months(self) -> list[str]:
        enum_values = self.schema_profile.get("enum_values") or {}
        return sorted(str(month) for month in enum_values.get("active_month", []) if month)

    def _extract_requested_months(self, question: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        seen = set()
        normalized_question = _normalize_chinese_month_text(question)

        for match in re.finditer(r"(?<!\d)(20\d{2}|\d{2})[-/.](0?[1-9]|1[0-2])(?!\d)", normalized_question):
            raw_year = int(match.group(1))
            year = raw_year if raw_year >= 100 else 2000 + raw_year
            month = int(match.group(2))
            self._append_month_match(matches, seen, year, month, f"{year:04d}-{month:02d}", False)

        for match in re.finditer(r"(?<!\d)(20\d{2}|\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月?", normalized_question):
            raw_year = int(match.group(1))
            year = raw_year if raw_year >= 100 else 2000 + raw_year
            month = int(match.group(2))
            self._append_month_match(matches, seen, year, month, f"{year:04d}-{month:02d}", False)

        for match in re.finditer(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)", normalized_question):
            year = int(match.group(1))
            month = int(match.group(2))
            self._append_month_match(matches, seen, year, month, f"{year:04d}-{month:02d}", False)

        for match in re.finditer(r"(?<!年)(?<!\d)(0?[1-9]|1[0-2])\s*月", normalized_question):
            month = int(match.group(1))
            display = f"{month}月"
            self._append_month_match(matches, seen, None, month, display, True)

        return matches

    def _append_month_match(
        self,
        matches: list[dict[str, Any]],
        seen: set[tuple[int | None, int, bool]],
        year: int | None,
        month: int,
        display: str,
        month_only: bool,
    ) -> None:
        key = (year, month, month_only)
        if key in seen:
            return
        seen.add(key)
        matches.append(
            {
                "year": year,
                "month": month,
                "display": display,
                "month_only": month_only,
            }
        )

    def _month_is_available(self, month: dict[str, Any], available_months: list[str]) -> bool:
        if month["month_only"]:
            return any(int(available_month[-2:]) == int(month["month"]) for available_month in available_months)
        requested = f"{int(month['year']):04d}-{int(month['month']):02d}"
        return requested in available_months

    def _asks_for_trend(self, question: str) -> bool:
        lowered = question.lower()
        if any(keyword in question for keyword in TREND_KEYWORDS):
            return True
        if any(keyword in question for keyword in RELATIVE_MONTH_KEYWORDS):
            return True
        return "active_month" in lowered and any(keyword in question for keyword in {"分布", "变化", "统计"})

    def detect_unknown_field_tokens(self, question: str) -> list[str]:
        known_columns = {
            str(column.get("name", "")).lower()
            for column in self.schema_profile.get("columns", [])
            if column.get("name")
        }
        allowed_terms = {
            "app",
            "top",
            "sql",
            "select",
            "where",
            "group",
            "by",
            "order",
            "limit",
            "sum",
            "count",
            "avg",
            "max",
            "min",
            "ppl",
            "cnt",
            TABLE_NAME.lower(),
        }
        tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", question)
        unknown = []
        for token in tokens:
            normalized = token.lower()
            if normalized in known_columns or normalized in allowed_terms:
                continue
            if "_" in normalized and normalized not in unknown:
                unknown.append(normalized)
        return unknown


def _normalize_chinese_month_text(text: str) -> str:
    month_map = {
        "十一": "11",
        "十二": "12",
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
        "十": "10",
    }
    normalized = text
    for chinese_month, month in month_map.items():
        normalized = normalized.replace(f"{chinese_month}月", f"{month}月")
    return normalized

def _compact_question(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())

def _contains_any_compact(text: str, keywords: set[str]) -> bool:
    return any(keyword.lower().replace(" ", "") in text for keyword in keywords)

def _public_enum_values(values: list[Any]) -> list[Any]:
    hidden_values = {"", "NA", "N/A", "NULL", "NONE", "None", "null", "nan"}
    return [value for value in values if str(value).strip() not in hidden_values]

def _sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"
