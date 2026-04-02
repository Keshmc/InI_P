"""Sidebar components shared across view pages."""

from __future__ import annotations

import streamlit as st


NEWS_SEARCH_PAGE = "news_search"


def render_sidebar(default_key: str) -> str:
    """Render app sidebar and return selected page key."""
    del default_key
    st.sidebar.title("Navigation")
    st.sidebar.caption("Active: News Search")
    st.sidebar.caption("Firestore load/save happens automatically in the search pipeline.")
    return NEWS_SEARCH_PAGE
