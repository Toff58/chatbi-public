import csv
import json
import re
import sys
import time
import traceback
from datetime import datetime
from numbers import Number
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from graph.workflow import build_graph
from config import POPULATION_BASE
from test_cases import TEST_CASES


RESULTS_PATH = ROOT_DIR / "logs" / "agent_test_results.csv"
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TIMESTAMPED_RESULTS_PATH = ROOT_DIR / "logs" / f"agent_test_results_{RUN_TIMESTAMP}.csv"
INTERNAL_RESULT_COLUMN_FRAGMENTS = {
    "numerator",
    "denominator",
    "target_sum",
    "source_sum",
    "valid_total",
    "valid_denominator",
    "ratio_raw",
    "base_population",
    "base_count",
    "calc_",
    "_calc",
    "分子",
    "分母",
    "有效分母",
}


def build_initial_state(question: str) -> dict[str, Any]:
    return {
        "question": question,
        "sql": None,
        "sql_valid": False,
        "summary": None,
        "result": None,
        "error": None,
        "answer": None,
        "rag_context": None,
        "metrics": None,
        "clarifications": None,
        "timings": None,
        "debug_info": None,
    }


def evaluate_case(test_case: dict[str, Any], state: dict[str, Any]) -> tuple[bool, list[str]]:
    failures = []
    sql = state.get("sql") or ""
    sql_valid = bool(state.get("sql_valid"))
    error = state.get("error")
    rows = state.get("result") or []
    result_count = len(rows)

    if "expect_sql_valid" in test_case:
        expected_sql_valid = bool(test_case["expect_sql_valid"])
        if sql_valid != expected_sql_valid:
            failures.append(f"sql_valid expected {expected_sql_valid}, got {sql_valid}")

    if test_case.get("expect_error") is True and not error:
        failures.append("expected visible error, got empty error")
    if test_case.get("expect_error") is False and error:
        failures.append(f"expected no error, got: {error}")

    if test_case.get("expect_error") is not True:
        for pattern in test_case.get("required_sql_patterns", []):
            if not re.search(pattern, sql, flags=re.IGNORECASE):
                failures.append(f"missing SQL pattern: {pattern}")

    for pattern in test_case.get("forbidden_sql_patterns", []):
        if sql and re.search(pattern, sql, flags=re.IGNORECASE):
            failures.append(f"forbidden SQL pattern matched: {pattern}")

    if "exact_result_count" in test_case and result_count != test_case["exact_result_count"]:
        failures.append(
            f"result_count expected {test_case['exact_result_count']}, got {result_count}"
        )
    if "min_result_count" in test_case and result_count < test_case["min_result_count"]:
        failures.append(
            f"result_count expected >= {test_case['min_result_count']}, got {result_count}"
        )
    if "max_result_count" in test_case and result_count > test_case["max_result_count"]:
        failures.append(
            f"result_count expected <= {test_case['max_result_count']}, got {result_count}"
        )

    for row_index, row in enumerate(rows, start=1):
        for column, value in row.items():
            lowered_column = str(column).lower()
            if any(fragment in lowered_column for fragment in INTERNAL_RESULT_COLUMN_FRAGMENTS):
                failures.append(f"internal calculation column exposed in result: {column}")
            if isinstance(value, Number) and not isinstance(value, bool) and value > POPULATION_BASE:
                failures.append(
                    f"population value exceeds base at row {row_index}, column {column}: {value}"
                )

    expected_rag_ids = set(test_case.get("expected_rag_ids", []))
    if expected_rag_ids:
        actual_rag_ids = {
            item.get("id")
            for item in state.get("rag_context") or []
            if isinstance(item, dict) and item.get("id")
        }
        missing_rag_ids = sorted(expected_rag_ids - actual_rag_ids)
        if missing_rag_ids:
            failures.append(f"missing RAG ids: {', '.join(missing_rag_ids)}")

    return not failures, failures


def run_test_case(app: Any, test_case: dict[str, Any]) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        state = app.invoke(build_initial_state(test_case["question"]))
    except Exception as exc:
        state = {
            **build_initial_state(test_case["question"]),
            "error": f"{type(exc).__name__}: {exc}",
            "debug_info": {"traceback": traceback.format_exc()},
        }
    wall_elapsed_ms = int((time.perf_counter() - started_at) * 1000)

    passed, failures = evaluate_case(test_case, state)
    timings = state.get("timings") or {}
    debug_info = state.get("debug_info") or {}
    model_calls = debug_info.get("model_calls") or []
    tool_timings = debug_info.get("tool_timings") or {}
    result = {
        "test_id": test_case["test_id"],
        "question": test_case["question"],
        "generated_sql": state.get("sql") or "",
        "sql_valid": bool(state.get("sql_valid")),
        "result_count": len(state.get("result") or []),
        "error": state.get("error") or "",
        "passed": passed,
        "status": "passed" if passed else "failed",
        "failure_reasons": " | ".join(failures),
        "expected_sql_pattern": test_case.get("expected_sql_pattern", ""),
        "expected_behavior": test_case.get("expected_behavior", ""),
        "risk_level": test_case.get("risk_level", ""),
        "wall_elapsed_ms": wall_elapsed_ms,
        "retrieval_ms": timings.get("retrieval_ms", ""),
        "first_model_call_ms": timings.get("first_model_call_ms", ""),
        "final_model_call_ms": timings.get("final_model_call_ms", ""),
        "model_calls_total_ms": timings.get("model_calls_total_ms", ""),
        "model_call_count": timings.get("model_call_count", ""),
        "agent_model_and_tools_ms": timings.get("agent_model_and_tools_ms", ""),
        "sql_validation_ms": tool_timings.get("sql_validation_ms", ""),
        "enum_validation_ms": tool_timings.get("enum_validation_ms", ""),
        "population_sql_validation_ms": tool_timings.get("population_sql_validation_ms", ""),
        "sql_execution_ms": tool_timings.get("sql_execution_ms", ""),
        "result_validation_ms": tool_timings.get("result_validation_ms", ""),
        "sql_tool_total_ms": tool_timings.get("tool_total_ms", ""),
        "total_ms": timings.get("total_ms", ""),
        "model_call_durations_ms": json.dumps(
            [item.get("duration_ms") for item in model_calls],
            ensure_ascii=False,
        ),
    }
    return result


def print_case_result(result: dict[str, Any]) -> None:
    print("=" * 80)
    print(f"{result['test_id']} - {result['status'].upper()}")
    print(f"question: {result['question']}")
    print(f"generated_sql: {result['generated_sql']}")
    print(f"sql_valid: {result['sql_valid']}")
    print(f"result_count: {result['result_count']}")
    print(f"error: {result['error']}")
    print(
        "timings_ms: "
        f"total={result['total_ms']} "
        f"first_model={result['first_model_call_ms']} "
        f"final_model={result['final_model_call_ms']} "
        f"sql_tool={result['sql_tool_total_ms']}"
    )
    print(f"passed / failed: {result['status']}")
    if result["failure_reasons"]:
        print(f"failure_reasons: {result['failure_reasons']}")


def save_results(results: list[dict[str, Any]]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "test_id",
        "question",
        "generated_sql",
        "sql_valid",
        "result_count",
        "error",
        "passed",
        "status",
        "failure_reasons",
        "expected_sql_pattern",
        "expected_behavior",
        "risk_level",
        "wall_elapsed_ms",
        "retrieval_ms",
        "first_model_call_ms",
        "final_model_call_ms",
        "model_calls_total_ms",
        "model_call_count",
        "agent_model_and_tools_ms",
        "sql_validation_ms",
        "enum_validation_ms",
        "population_sql_validation_ms",
        "sql_execution_ms",
        "result_validation_ms",
        "sql_tool_total_ms",
        "total_ms",
        "model_call_durations_ms",
    ]
    for path in (RESULTS_PATH, TIMESTAMPED_RESULTS_PATH):
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)


def print_summary(results: list[dict[str, Any]]) -> None:
    total_tests = len(results)
    passed_tests = sum(1 for result in results if result["passed"])
    failed_tests = total_tests - passed_tests
    pass_rate = passed_tests / total_tests if total_tests else 0

    print("=" * 80)
    print("SUMMARY")
    print(f"total_tests: {total_tests}")
    print(f"passed_tests: {passed_tests}")
    print(f"failed_tests: {failed_tests}")
    print(f"pass_rate: {pass_rate:.2%}")
    print(f"results_csv: {RESULTS_PATH}")
    print(f"timestamped_results_csv: {TIMESTAMPED_RESULTS_PATH}")


def main() -> None:
    app = build_graph()
    results = []
    for test_case in TEST_CASES:
        result = run_test_case(app, test_case)
        results.append(result)
        print_case_result(result)

    save_results(results)
    print_summary(results)


if __name__ == "__main__":
    main()
