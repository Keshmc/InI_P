"""Sidebar components shared across view pages."""

from __future__ import annotations

import streamlit as st


NEWS_SEARCH_PAGE = "news_search"
DATASTORE_PAGE = "datastore"
_NAV_OPTIONS = [
    ("News Search", NEWS_SEARCH_PAGE),
    ("Datastore", DATASTORE_PAGE),
]


def render_sidebar(
    default_key: str,
    auto_trend_running: bool,
    auto_trend_last_run: str = "",
    auto_trend_interval_minutes: int = 0,
) -> str:
    """Render app sidebar and return selected page key."""
    _inject_sidebar_styles()
    st.sidebar.title("Navigation")
    selected = str(default_key or NEWS_SEARCH_PAGE)

    keys = [key for _, key in _NAV_OPTIONS]
    labels_by_key = {key: label for label, key in _NAV_OPTIONS}
    try:
        default_index = keys.index(selected)
    except ValueError:
        default_index = 0

    selected = st.sidebar.radio(
        "Section",
        options=keys,
        index=default_index,
        format_func=lambda key: labels_by_key.get(str(key), str(key)),
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    state_label = "running" if auto_trend_running else "stopped"
    st.sidebar.caption(f"Trend Collector: {state_label}")

    if auto_trend_interval_minutes > 0:
        st.sidebar.caption(f"Intervall: alle {auto_trend_interval_minutes} Minute(n)")
    if auto_trend_last_run:
        st.sidebar.caption(f"Last run (UTC): {auto_trend_last_run}")

    return selected


def _inject_sidebar_styles() -> None:
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] div[role="radiogroup"] > label {
                border: 1px solid #d9e2ec;
                border-radius: 8px;
                margin-bottom: 0.35rem;
                padding: 0.35rem 0.45rem;
                background-color: #ffffff;
            }
            [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
                background-color: #eef4ff;
                border-color: #87a9d9;
                box-shadow: inset 3px 0 0 #2f6db5;
                font-weight: 600;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
