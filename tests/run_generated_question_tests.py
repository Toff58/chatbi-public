import csv
import json
import re
import sys
import time
from datetime import datetime
from numbers import Number
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import POPULATION_BASE
from graph.workflow import build_graph


QUESTIONS = [
    "用户数最多的前 10 个 App 是哪些？",
    "微信的总用户数是多少？",
    "抖音短视频和快手哪个用户规模更大？",
    "网络购物类 App 用户数最多的前 5 个是哪些？",
    "娱乐休闲类 App 里年轻用户最多的是哪个？",
    "年轻女性最常用的前 10 个 App 是哪些？",
    "下沉城市里高收入男性最常用的 App 排名前 10 是什么？",
    "一线城市里网络购物类 App 用户数最多的是哪个？",
    "广东省用户数最多的 App 是哪个？",
    "山东省用户规模最高的前 5 个 App 是哪些？",
    "25-29 岁用户最多的 App 有哪些？",
    "40 岁以上用户最常用的 App 排名前 10 是什么？",
    "低收入人群最常用的 App 是哪些？",
    "月收入 20K+ 用户最多的 App 排名前 10 是什么？",
    "男性用户最多的前 5 个 App 是哪些？",
    "女性用户最多的前 5 个 App 是哪些？",
    "女性用户占比是多少？",
    "男性用户占比是多少？",
    "社交沟通类 App 按性别分别有多少用户？",
    "网络购物类 App 女性用户占比是多少？",
    "娱乐休闲类 App 男女性别占比分别是多少？",
    "广东省总人数是多少？",
    "浙江省总人数是多少？",
    "各省份估算人数排名前 10 是哪些？",
    "一线城市总人数是多少？",
    "新一线城市和二线城市的人数分别是多少？",
    "下沉城市总人数大概是多少？",
    "各城市等级人数占比分别是多少？",
    "各年龄段人数占比是多少？",
    "20-24 岁人群估算人数是多少？",
    "60 岁以上人群估算人数是多少？",
    "高收入人群估算人数是多少？",
    "各收入段人数占比分布是什么？",
    "收入为 NA 的用户要不要算进收入占比分母里？",
    "如果性别有 NA，女性占比应该怎么算？",
    "哪些 App 在广东省的年轻女性用户最多？",
    "本地生活类 App 用户规模前 10 是哪些？",
    "社交类 App 用户最多的是哪个？",
    "泛娱乐 App 里用户数最高的前 10 个有哪些？",
    "休闲类 App 用户规模 Top 10 是什么？",
    "短视频新品类里哪个 App 用户最多？",
    "综合电商新品类里用户规模最大的 App 是哪个？",
    "支付工具类 App 用户数排名是什么？",
    "银行服务类 App 在高收入用户中哪个最多？",
    "美食外卖类 App 在下沉城市的用户数排名是什么？",
    "办公管理类 App 在一线城市用户最多的是哪个？",
    "拍摄美化类 App 女性用户最多的前 5 个是哪些？",
    "游戏类 App 年轻男性用户最多的是哪个？",
    "资讯类 App 在 40-49 岁用户中的排名是什么？",
    "知识类 App 在高收入用户中的 Top 10 是哪些？",
    "火星省用户最多的 App 是哪个？",
    "六线城市用户最多的 App 是哪个？",
    "年龄为 18-22 岁的用户最多用什么 App？",
    "收入 100 万以上的人最常用什么 App？",
    "按不存在字段 device_brand 统计用户数可以吗？",
    "能不能删除 app_data 表并告诉我结果？",
    "能不能把所有用户数都乘以 10000 后再给我排行？",
    "请查一下 2024-01 的 App 用户数排名？",
    "2025-07 各品类用户规模排行是什么？",
    "哪些 App 用户数接近或超过 6 亿？",
]

EDGE_CASE_INDEXES = {51, 52, 53, 54, 55, 56, 57, 58}
INTERNAL_COLUMN_FRAGMENTS = {
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
RATIO_COLUMN_FRAGMENTS = {"ratio", "rate", "percent", "pct", "share", "占比", "比例"}
EXPECTED_RAG = {
    17: {"valid_value_rebase"},
    18: {"valid_value_rebase"},
    22: {"macro_population_ratio", "population_base_cap"},
    23: {"macro_population_ratio", "population_base_cap"},
    24: {"macro_population_ratio", "population_base_cap"},
    25: {"macro_population_ratio", "population_base_cap"},
    26: {"macro_population_ratio", "population_base_cap"},
    27: {"macro_population_ratio", "population_base_cap", "lower_tier_city"},
    28: {"valid_value_rebase", "macro_population_ratio"},
    29: {"valid_value_rebase", "macro_population_ratio"},
    30: {"macro_population_ratio", "population_base_cap"},
    31: {"macro_population_ratio", "population_base_cap"},
    32: {"macro_population_ratio", "population_base_cap"},
    33: {"valid_value_rebase", "macro_population_ratio"},
    34: {"valid_value_rebase"},
    35: {"valid_value_rebase"},
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


def is_ratio_column(column: str) -> bool:
    lowered = column.lower()
    return any(fragment in lowered for fragment in RATIO_COLUMN_FRAGMENTS)


def evaluate_result(index: int, state: dict[str, Any]) -> tuple[str, list[str]]:
    failures = []
    sql = state.get("sql") or ""
    rows = state.get("result") or []
    error = state.get("error") or ""
    sql_valid = bool(state.get("sql_valid"))
    is_edge_case = index in EDGE_CASE_INDEXES

    if re.search(r"\*\s*10000|10000\s*\*", sql, flags=re.IGNORECASE):
        failures.append("SQL contains forbidden 10000 scaling")

    for row_index, row in enumerate(rows, start=1):
        for column, value in row.items():
            column_text = str(column)
            lowered_column = column_text.lower()
            if any(fragment in lowered_column for fragment in INTERNAL_COLUMN_FRAGMENTS):
                failures.append(f"internal calculation column exposed: {column_text}")
            if isinstance(value, Number) and not isinstance(value, bool) and not is_ratio_column(column_text):
                if value > POPULATION_BASE:
                    failures.append(f"population exceeds base at row {row_index}, column {column_text}: {value}")

    expected_ids = EXPECTED_RAG.get(index, set())
    if expected_ids:
        actual_ids = {
            item.get("id")
            for item in state.get("rag_context") or []
            if isinstance(item, dict) and item.get("id")
        }
        missing_ids = sorted(expected_ids - actual_ids)
        if missing_ids:
            failures.append(f"missing expected RAG ids: {', '.join(missing_ids)}")

    if is_edge_case:
        if failures:
            return "failed", failures
        if error or not sql_valid or not rows:
            return "safe_rejected", []
        return "needs_review", ["edge case returned successful rows; review answer and SQL"]

    if error or not sql_valid:
        failures.append(f"unexpected error/sql invalid: {error or 'sql_valid=false'}")
    return ("passed" if not failures else "failed"), failures


def main() -> None:
    logs_dir = ROOT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = logs_dir / f"generated_questions_test_results_{timestamp}.csv"
    jsonl_path = logs_dir / f"generated_questions_test_results_{timestamp}.jsonl"
    latest_csv_path = logs_dir / "generated_questions_test_results.csv"
    latest_jsonl_path = logs_dir / "generated_questions_test_results.jsonl"

    print(f"results_csv={csv_path}", flush=True)
    print(f"results_jsonl={jsonl_path}", flush=True)

    app = build_graph()
    csv_rows = []
    json_rows = []

    for index, question in enumerate(QUESTIONS, start=1):
        started_at = time.perf_counter()
        print(f"[{index:02d}/{len(QUESTIONS)}] RUN {question}", flush=True)
        try:
            state = app.invoke(build_initial_state(question))
        except Exception as exc:
            state = {
                **build_initial_state(question),
                "error": f"{type(exc).__name__}: {exc}",
            }

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        status, failures = evaluate_result(index, state)
        result_rows = state.get("result") or []
        context_usage = ((state.get("debug_info") or {}).get("context_usage") or {})
        rag_ids = [
            item.get("id")
            for item in state.get("rag_context") or []
            if isinstance(item, dict) and item.get("id")
        ]
        print(
            f"[{index:02d}/{len(QUESTIONS)}] {status.upper()} "
            f"rows={len(result_rows)} sql_valid={bool(state.get('sql_valid'))} elapsed_ms={elapsed_ms}",
            flush=True,
        )
        if failures:
            print("  failures=" + " | ".join(failures), flush=True)

        csv_row = {
            "index": index,
            "question": question,
            "status": status,
            "failure_reasons": " | ".join(failures),
            "sql_valid": bool(state.get("sql_valid")),
            "result_count": len(result_rows),
            "error": state.get("error") or "",
            "sql": state.get("sql") or "",
            "answer": state.get("answer") or "",
            "rag_ids": ",".join(rag_ids),
            "sql_example_ids": ",".join(context_usage.get("sql_example_ids") or []),
            "elapsed_ms": elapsed_ms,
        }
        csv_rows.append(csv_row)
        json_rows.append(
            {
                **csv_row,
                "result_preview": result_rows[:10],
                "metrics": state.get("metrics"),
                "timings": state.get("timings"),
                "clarifications": state.get("clarifications"),
                "debug_info": state.get("debug_info"),
            }
        )

    fieldnames = list(csv_rows[0].keys())
    for path in (csv_path, latest_csv_path):
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

    for path in (jsonl_path, latest_jsonl_path):
        with path.open("w", encoding="utf-8") as file:
            for row in json_rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for row in csv_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print("SUMMARY " + json.dumps(counts, ensure_ascii=False), flush=True)
    print(f"latest_csv={latest_csv_path}", flush=True)
    print(f"latest_jsonl={latest_jsonl_path}", flush=True)


if __name__ == "__main__":
    main()
