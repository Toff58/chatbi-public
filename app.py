import uuid
from typing import Any

import streamlit as st

from graph.workflow import build_graph
from ui.charts import build_chart_spec, render_chart
from ui.database import ensure_database
from ui.dataframe import build_display_dataframe, build_sorted_dataframe
from ui.dictionary import render_dictionary_page
from ui.downloads import render_download_buttons
from ui.query_logging import save_logs


def ask(question: str, session_id: str | None = None) -> dict[str, Any]:
    app = build_graph()
    initial_state = {
        "question": question,
        "session_id": session_id,
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
    result = app.invoke(initial_state)
    save_logs(question, result)
    return result


EXAMPLE_QUESTIONS = [
    "用户数最多的前 10 个 App 是哪些？",
    "年轻女性在休闲娱乐类 App 中使用最多的是哪个？",
    "广东省总人数是多少？",
    "女性用户占比是多少？",
    "下沉城市里高收入男性最常用的前 10 个 App 是哪些？",
]


def format_duration(milliseconds: Any) -> str:
    try:
        value = int(milliseconds)
    except (TypeError, ValueError):
        return ""
    if value >= 1000:
        return f"{value / 1000:.1f} 秒"
    return f"{value} 毫秒"


def render_answer_state(state: dict[str, Any], key_prefix: str) -> None:
    timings = state.get("timings") or {}
    rows = state.get("result") or []
    duration_text = format_duration(timings.get("total_ms"))
    if duration_text:
        st.caption(f"耗时 {duration_text} · 返回 {len(rows)} 条结果")

    for clarification in state.get("clarifications") or []:
        st.info(clarification)

    if state.get("error"):
        st.error("这次查询没有成功，请换一种问法或稍后重试。")
        return

    st.markdown("#### 结论")
    st.write(state.get("answer") or "没有生成结论。")

    if not rows:
        if not state.get("sql"):
            return
        st.info("查询没有返回数据。")
        return

    result_df = build_sorted_dataframe(rows)
    display_df = build_display_dataframe(result_df)
    chart_spec = build_chart_spec(rows)
    if chart_spec:
        chart_tab, table_tab = st.tabs(["图表", "明细"])
        with chart_tab:
            render_chart(chart_spec)
        with table_tab:
            st.dataframe(display_df, width="stretch", hide_index=True)
    else:
        st.dataframe(display_df, width="stretch", hide_index=True)

    render_download_buttons(display_df, chart_spec, key_prefix)


def run_question(question: str) -> None:
    cleaned_question = question.strip()
    if not cleaned_question:
        st.warning("请先输入问题。")
        return

    st.session_state.messages.append({"role": "user", "content": cleaned_question})
    with st.chat_message("user"):
        st.write(cleaned_question)

    with st.chat_message("assistant"):
        status = st.status("正在理解问题并检索业务口径...", expanded=False)
        state = ask(cleaned_question, st.session_state.session_id)
        status.update(label="分析完成", state="complete")
        render_answer_state(state, key_prefix=f"live_{len(st.session_state.messages)}")
    st.session_state.messages.append({"role": "assistant", "state": state})


st.set_page_config(page_title="ChatBI 智能问数", layout="wide")
st.title("ChatBI 智能问数")
st.caption("用自然语言查询 App 人群数据。公开演示版数据窗口：仅包含 2025-07。")

try:
    ensure_database()
except Exception as exc:
    st.error(str(exc))
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex

with st.sidebar:
    page = st.radio("导航", ["智能问数", "可问范围"], label_visibility="collapsed")
    st.info("公开演示版仅包含 2025-07 数据。")
    st.divider()
    if page == "智能问数":
        st.subheader("示例问题")
        for example in EXAMPLE_QUESTIONS:
            if st.button(example, use_container_width=True):
                st.session_state.pending_question = example
        st.divider()
        if st.button("清空会话", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_question = None
            st.rerun()

if page == "可问范围":
    render_dictionary_page()
    st.stop()

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            render_answer_state(message["state"], key_prefix=f"history_{index}")

prompt = st.chat_input("输入你的问题")
pending_question = st.session_state.pending_question
if pending_question:
    st.session_state.pending_question = None
    run_question(pending_question)
elif prompt:
    run_question(prompt)
