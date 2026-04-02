"""Sidebar components shared across view pages."""

from __future__ import annotations

import streamlit as st


NEWS_SEARCH_PAGE = "news_search"


def render_sidebar(
    default_key: str,
    auto_trend_running: bool,
    auto_trend_last_run: str = "",
    auto_trend_interval_minutes: int = 0,
) -> str:
    """Render app sidebar and return selected page key."""
    del default_key
    st.sidebar.title("Navigation")
    st.sidebar.caption("Active: News Search")
    st.sidebar.caption("Firestore load/save happens automatically in the search pipeline.")
    state_label = "running" if auto_trend_running else "stopped"
    st.sidebar.caption(f"Trend Collector: {state_label}")

    if auto_trend_interval_minutes > 0:
        st.sidebar.caption(f"Intervall: alle {auto_trend_interval_minutes} Minute(n)")
    if auto_trend_last_run:
        st.sidebar.caption(f"Last run (UTC): {auto_trend_last_run}")

    return NEWS_SEARCH_PAGE
