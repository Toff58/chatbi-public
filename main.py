import argparse
import json
from typing import Any

from graph.workflow import build_graph


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one ChatBI Agent question from the command line.")
    parser.add_argument("question", nargs="?", default="用户数最多的前 10 个 App 是哪些？")
    args = parser.parse_args()

    app = build_graph()
    state = app.invoke(build_initial_state(args.question))
    print("Question:", args.question)
    print("SQL:", state.get("sql") or "")
    print("SQL valid:", state.get("sql_valid"))
    print("Answer:", state.get("answer") or "")
    print("Error:", state.get("error") or "")
    print("Rows:")
    print(json.dumps(state.get("result") or [], ensure_ascii=False, indent=2))
    return 0 if not state.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
