from typing import Any

import pandas as pd
import streamlit as st

from sql.executor import get_schema_profile
from ui.constants import DICTIONARY_DIMENSION_ORDER, METRIC_DICTIONARY_ROWS
from ui.dataframe import _display_column_label


@st.cache_data(show_spinner=False)
def load_data_dictionary() -> dict[str, list[Any]]:
    profile = get_schema_profile()
    enum_values = profile.get("enum_values") or {}
    return {
        field: _public_enum_values(enum_values.get(field, []))
        for field in DICTIONARY_DIMENSION_ORDER
        if enum_values.get(field)
    }

def _public_enum_values(values: list[Any]) -> list[Any]:
    hidden_values = {"", "NA", "N/A", "NULL", "NONE", "None", "null", "nan"}
    return [value for value in values if str(value).strip() not in hidden_values]

def render_dictionary_page() -> None:
    metric_tab, dimension_tab = st.tabs(["指标字典", "字段字典"])
    with metric_tab:
        st.dataframe(pd.DataFrame(METRIC_DICTIONARY_ROWS), width="stretch", hide_index=True)

    with dimension_tab:
        dictionary = load_data_dictionary()
        available_fields = [field for field in DICTIONARY_DIMENSION_ORDER if dictionary.get(field)]
        if not available_fields:
            st.info("当前没有可展示的字段取值。")
            return

        available_labels = [_display_column_label(field) for field in available_fields]
        selected_label = st.selectbox("维度", available_labels, index=0)
        selected_field = available_fields[available_labels.index(selected_label)]
        values = dictionary.get(selected_field, [])
        st.caption(f"{selected_label} 共 {len(values)} 个可用取值")
        st.dataframe(pd.DataFrame({"可用取值": values}), width="stretch", hide_index=True)
