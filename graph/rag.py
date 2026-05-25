import re
from typing import Any, TypedDict

from config import POPULATION_BASE, TABLE_NAME
from graph.business_terms import BUSINESS_SCOPES, match_business_scopes
from graph.sql_examples import SQL_EXAMPLES


class RagItem(TypedDict):
    id: str
    title: str
    content: str
    keywords: list[str]
    sql_hint: str
    score: float


class SqlExample(TypedDict):
    id: str
    question: str
    sql: str
    keywords: list[str]
    score: float


BUSINESS_KNOWLEDGE: list[dict[str, Any]] = [
    {
        "id": "metric_ppl_cnt",
        "title": "用户人数口径",
        "content": (
            "ppl_cnt 在数据库里已经是实际人数；单个 App 的用户数可按 app_name 直接 SUM(ppl_cnt)。"
            f"但人数 base 是 {POPULATION_BASE}，任何人数结果都不能超过 base。"
        ),
        "keywords": ["人数", "用户数", "用户", "规模", "最多", "排行", "top", "ppl_cnt"],
        "sql_hint": "按 app_name 统计 App 总人数时使用 SUM(ppl_cnt) AS user_count，并确保每个结果不超过 base。",
    },
    {
        "id": "unique_segment_sum",
        "title": "唯一人群切片求和",
        "content": "数据已按年龄段、城市、性别、收入等维度切分；只有单个 App 或带 app_name 的 App 排行/画像筛选结果才直接 SUM(ppl_cnt)。",
        "keywords": ["加总", "求和", "sum", "人数", "用户数", "总用户数"],
        "sql_hint": "App 总用户数和按 app_name 的画像筛选排行直接使用 SUM(ppl_cnt)；宏观人群人数不要直接输出 SUM(ppl_cnt)。",
    },
    {
        "id": "unsupported_cross_app_overlap",
        "title": "不支持跨 App 重合或共同用户",
        "content": (
            "当前表只有 App 与画像切片的聚合人数，没有用户级 ID 或跨 App 关联关系。"
            "不能回答使用 A 的人是否也使用 B、A 用户还用哪些 App、同时使用多个 App、交叉重合或共同用户等问题。"
        ),
        "keywords": [
            "同时使用",
            "同时用",
            "还用",
            "也用",
            "都用",
            "共同用户",
            "共用用户",
            "重合",
            "重叠",
            "交叉",
            "交集",
            "双装",
            "多装",
            "用支付宝的人",
            "微信用户还用",
        ],
        "sql_hint": "这类问题应直接说明当前数据不支持，不要改写成整体 App 排行或排除某 App 后的排行。",
    },
    {
        "id": "unsupported_user_level_behavior",
        "title": "不支持用户级行为、去重覆盖和链路分析",
        "content": (
            "当前表没有用户 ID、设备 ID、访问日志、订单、交易金额、使用时长、打开次数或多月链路。"
            "不能回答去重覆盖、任一/至少使用几个 App、人均使用 App 数、留存、新增、卸载、转化、频次、时长、因果或相关性问题。"
        ),
        "keywords": [
            "去重",
            "不重复",
            "覆盖用户",
            "覆盖人数",
            "至少使用",
            "任一",
            "人均",
            "几个App",
            "几个 app",
            "使用时长",
            "使用频次",
            "打开次数",
            "留存",
            "新增",
            "卸载",
            "转化",
            "订单",
            "金额",
            "相关性",
            "因果",
        ],
        "sql_hint": "这类问题应说明当前数据缺少用户级或行为日志字段，不能生成 SQL 推断。",
    },
    {
        "id": "population_base_cap",
        "title": "6 亿 base 人数上限",
        "content": f"项目固定 base 人数为 {POPULATION_BASE}，任何返回给前端的人数、用户数、人口数都不能超过这个值。",
        "keywords": ["base", "6亿", "六亿", "600000000", "人数", "总人数", "人数上限", "不能超过", "人口"],
        "sql_hint": f"所有人数结果必须 <= {POPULATION_BASE}；非 App 宏观人数应使用 base 乘以有效样本占比。",
    },
    {
        "id": "macro_population_ratio",
        "title": "宏观人群人数估算",
        "content": "当问题问省份、城市等级、性别、年龄、收入等宏观人群人数，而不是某个 App 的总人数时，先算目标人群在有效样本中的占比，再用 base 乘以该占比。",
        "keywords": ["宏观", "人口", "总人数", "省份", "广东省", "城市等级", "年龄", "收入", "性别", "比例"],
        "sql_hint": (
            f"{POPULATION_BASE}.0 * target_sum / valid_denominator_sum AS estimated_user_count；"
            "最终 SELECT 不暴露 target_sum、valid_denominator_sum 或 ratio。"
        ),
    },
    {
        "id": "valid_value_rebase",
        "title": "NA 和空白值 rebase",
        "content": "NA、NULL 或空白表示该字段未取到值，不代表这部分人不存在；计算该字段占比时，分母只使用该字段有有效值的部分。",
        "keywords": ["NA", "空白", "NULL", "缺失", "占比", "比例", "rebase", "女性占比", "有效值"],
        "sql_hint": "例如女性占比使用 女 / (男 + 女)，字段有 NA 或空白时从分母排除。",
    },
    {
        "id": "profile_app_ranking",
        "title": "画像筛选后的 App 排行",
        "content": "当问题问某类画像人群在哪个 App 使用最多时，需要统计每个 App 中满足该画像的总人数，再取人数最大的 App。",
        "keywords": ["年轻女性", "画像", "哪个app", "哪个 App", "使用最多", "用的最多", "app"],
        "sql_hint": "WHERE age IN (...) AND gender = '女' GROUP BY app_name ORDER BY SUM(ppl_cnt) DESC LIMIT 1",
    },
    {
        "id": "ranking_default",
        "title": "排行默认规则",
        "content": "当用户询问最多、最大、排行、Top 时，默认按目标指标降序排序并 LIMIT 10。",
        "keywords": ["最多", "最大", "排行", "排名", "top", "前", "高"],
        "sql_hint": "ORDER BY user_count DESC LIMIT 10",
    },
    {
        "id": "young_users",
        "title": "年轻用户口径",
        "content": "年轻用户通常可理解为 age in ('小于20岁', '20-24岁', '25-29岁')。",
        "keywords": ["年轻", "青年", "年轻人", "低龄", "age"],
        "sql_hint": "WHERE age IN ('小于20岁', '20-24岁', '25-29岁')",
    },
    {
        "id": "lower_tier_city",
        "title": "下沉城市口径",
        "content": "下沉、低线城市通常可理解为三线及以下城市。",
        "keywords": ["下沉", "低线", "三线", "四线", "五线", "city_tier"],
        "sql_hint": "WHERE city_tier IN ('三线城市', '四线城市', '五线城市')",
    },
    {
        "id": "aggregation_default",
        "title": "聚合优先",
        "content": "如果问题没有要求明细，优先返回聚合结果，避免直接返回大量原始行。",
        "keywords": ["多少", "哪些", "分布", "占比", "趋势", "统计"],
        "sql_hint": "App 维度可 GROUP BY app_name 并 SUM(ppl_cnt)；宏观维度人数先算有效样本占比再乘以 base。",
    },
    {
        "id": "month_filter",
        "title": "月份字段",
        "content": "active_month 是活跃月份，格式如 2025-07，涉及月份或趋势时使用该字段。",
        "keywords": ["月份", "月", "趋势", "active_month", "时间"],
        "sql_hint": "GROUP BY active_month ORDER BY active_month",
    },
]


def retrieve_sql_context(
    question: str,
    schema_profile: dict[str, Any],
    top_k: int = 6,
) -> list[RagItem]:
    items = _build_items(schema_profile)
    matched_scope_ids = {scope["id"] for scope in match_business_scopes(question)}
    question_tokens = _tokenize(question)
    scored: list[RagItem] = []

    for item in items:
        text = " ".join([item["title"], item["content"], item["sql_hint"], " ".join(item["keywords"])])
        item_tokens = _tokenize(text)
        overlap = len(question_tokens & item_tokens)
        keyword_hits = sum(1 for keyword in item["keywords"] if keyword.lower() in question.lower())
        score = overlap + keyword_hits * 3
        if item["id"] in matched_scope_ids:
            score += 20
        if score <= 0:
            continue
        scored.append({**item, "score": float(score)})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def retrieve_sql_examples(question: str, top_k: int = 3) -> list[SqlExample]:
    question_tokens = _tokenize(question)
    scored: list[SqlExample] = []

    for item in SQL_EXAMPLES:
        text = " ".join([item["question"], item["sql"], " ".join(item["keywords"])])
        item_tokens = _tokenize(text)
        overlap = len(question_tokens & item_tokens)
        keyword_hits = sum(1 for keyword in item["keywords"] if keyword.lower() in question.lower())
        score = overlap + keyword_hits * 3
        if score <= 0:
            continue
        scored.append({**item, "score": float(score)})

    if not scored:
        scored = [{**item, "score": 0.0} for item in SQL_EXAMPLES[:2]]

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def format_rag_context(items: list[RagItem]) -> str:
    if not items:
        return "没有检索到额外业务规则。"

    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item['title']}: {item['content']}\n"
            f"   SQL 提示: {item['sql_hint']}"
        )
    return "\n".join(lines)


def format_sql_examples(items: list[SqlExample]) -> str:
    if not items:
        return "没有匹配到可参考的 SQL 示例。"

    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. 问题：{item['question']}\n"
            f"   SQL：\n{item['sql']}"
        )
    return "\n\n".join(lines)


def _build_items(schema_profile: dict[str, Any]) -> list[dict[str, Any]]:
    items = [dict(item) for item in BUSINESS_KNOWLEDGE]
    existing_ids = {item["id"] for item in items}
    for scope in BUSINESS_SCOPES:
        if scope["id"] in existing_ids:
            continue
        values = "', '".join(scope["values"])
        items.append(
            {
                "id": scope["id"],
                "title": f"固定业务范围：{scope['name']}",
                "content": scope["description"],
                "keywords": scope["keywords"],
                "sql_hint": f"{scope['field']} IN ('{values}')",
            }
        )
    for column in schema_profile.get("columns", []):
        name = column.get("name", "")
        sample_values = (schema_profile.get("enum_values") or schema_profile.get("sample_values", {})).get(name, [])
        if not name:
            continue
        items.append(
            {
                "id": f"column_{name}",
                "title": f"字段 {name}",
                "content": f"{TABLE_NAME}.{name} 可用于筛选或分组。样例值: {', '.join(map(str, sample_values[:12]))}",
                "keywords": [name, *[str(value) for value in sample_values[:20]]],
                "sql_hint": f"需要该维度时使用字段 {name}",
            }
        )
    return items


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.update(chinese_chars)
    tokens.update("".join(chinese_chars[index : index + 2]) for index in range(max(len(chinese_chars) - 1, 0)))
    return {token for token in tokens if token}
