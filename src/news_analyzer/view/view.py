"""Streamlit view orchestration for navigation and page rendering."""

from __future__ import annotations

import streamlit as st

from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.datastore.datastore_page import DataStorePage
from news_analyzer.view.pages.general.sidebar import PageKey, render_sidebar
from news_analyzer.view.pages.search.search_page import NewsSearchPage


def _bootstrap_state() -> None:
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = PageKey.NEWS_SEARCH.value


def run_view(presenter: NewsPresenter) -> None:
    """Render Streamlit app entrypoint."""
    st.set_page_config(
        page_title="News Analyzer",
        page_icon="N",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _bootstrap_state()

    selected_page = render_sidebar(default_key=st.session_state.nav_page)
    st.session_state.nav_page = selected_page

    if selected_page == PageKey.DATASTORE.value:
        DataStorePage().render()
        return

    NewsSearchPage(presenter=presenter).render()
