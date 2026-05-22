import re
from typing import Any

from graph.business_terms import match_business_scopes
from sql.executor import validate_select_sql


def evaluate_run(
    *,
    question: str,
    sql: str | None,
    result: list[dict[str, Any]] | None,
    answer: str | None,
    error: str | None,
    rag_items: list[dict[str, Any]],
    latency_ms: int,
    tool_called: bool,
) -> dict[str, Any]:
    sql_valid, _ = validate_select_sql(sql or "") if sql else (False, "empty sql")
    execution_success = error is None and result is not None
    answer_nonempty = bool((answer or "").strip())
    result_count = len(result or [])
    rag_precision, rag_recall = _rag_precision_recall(question, rag_items)

    accuracy = 1.0 if sql_valid and execution_success and answer_nonempty and tool_called else 0.0

    return {
        "accuracy": accuracy,
        "recall": rag_recall,
        "precision": rag_precision,
        "sql_valid": sql_valid,
        "execution_success": execution_success,
        "tool_called": tool_called,
        "answer_nonempty": answer_nonempty,
        "result_count": result_count,
        "rag_context_count": len(rag_items),
        "latency_ms": latency_ms,
    }


def _rag_precision_recall(question: str, rag_items: list[dict[str, Any]]) -> tuple[float, float]:
    expected = _expected_rag_ids(question)
    retrieved = {item.get("id") for item in rag_items if item.get("id")}
    if not retrieved:
        return 0.0, 0.0 if expected else 1.0

    relevant_retrieved = retrieved & expected if expected else retrieved
    precision = len(relevant_retrieved) / len(retrieved)
    recall = len(relevant_retrieved) / len(expected) if expected else 1.0
    return round(precision, 4), round(recall, 4)


def _expected_rag_ids(question: str) -> set[str]:
    lowered = question.lower()
    checks = [
        ("metric_ppl_cnt", ["人数", "用户", "用户数", "规模", "ppl_cnt"]),
        ("unique_segment_sum", ["加总", "求和", "sum", "总用户数"]),
        ("ranking_default", ["最多", "最大", "排行", "排名", "top", "前"]),
        ("young_users", ["年轻", "青年", "年轻人", "低龄"]),
        ("lower_tier_city", ["下沉", "低线", "三线", "四线", "五线"]),
        ("month_filter", ["月", "月份", "趋势", "时间"]),
        ("aggregation_default", ["多少", "哪些", "分布", "占比", "统计"]),
    ]
    expected = set()
    for item_id, keywords in checks:
        if any(keyword in lowered for keyword in keywords):
            expected.add(item_id)
    if re.search(r"\btop\b", lowered):
        expected.add("ranking_default")
    expected.update(scope["id"] for scope in match_business_scopes(question))
    return expected
