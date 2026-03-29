"""Sidebar components shared across view pages."""

from __future__ import annotations

from enum import Enum

import streamlit as st


class PageKey(str, Enum):
    NEWS_SEARCH = "news_search"
    DATASTORE = "datastore"


def render_sidebar(default_key: str) -> str:
    """Render app sidebar and return selected page key."""
    st.sidebar.title("Navigation")
    selected = default_key
    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("News Search", width="stretch"):
        selected = PageKey.NEWS_SEARCH.value
    if col_b.button("Datastore", width="stretch"):
        selected = PageKey.DATASTORE.value

    active_label = "News Search" if selected == PageKey.NEWS_SEARCH.value else "Datastore"
    st.sidebar.caption(f"Active: {active_label}")
    st.sidebar.caption("Datastore will be expanded in a later step.")
    return str(selected)
