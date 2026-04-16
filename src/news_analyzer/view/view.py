"""Streamlit view orchestration for navigation and page rendering."""

from __future__ import annotations

import streamlit as st

from news_analyzer.model.trends import get_long_term_trend_scheduler, load_long_term_trend_config
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.datastore.datastore_page import DataStorePage
from news_analyzer.view.pages.general.sidebar import DATASTORE_PAGE, NEWS_SEARCH_PAGE, PUBLISHER_PAGE, render_sidebar
from news_analyzer.view.pages.publishers.publisher_page import PublisherPage
from news_analyzer.view.pages.search.search_page import NewsSearchPage


def _bootstrap_state() -> None:
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = NEWS_SEARCH_PAGE


def run_view(presenter: NewsPresenter) -> None:
    """Render Streamlit app entrypoint."""
    st.set_page_config(
        page_title="News Analyzer",
        page_icon="N",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _bootstrap_state()

    trend_config = load_long_term_trend_config()
    trend_scheduler = get_long_term_trend_scheduler(
        pipeline=presenter.pipeline,
        config=trend_config,
    )
    trend_scheduler.set_enabled(bool(trend_config.enabled))
    trend_status = trend_scheduler.status()

    selected_page = render_sidebar(
        default_key=st.session_state.nav_page,
        auto_trend_running=bool(trend_status.get("running", False)),
        auto_trend_last_run=str(trend_status.get("last_run_at", "") or ""),
        auto_trend_interval_minutes=int(trend_status.get("interval_minutes", 0)),
    )
    st.session_state.nav_page = selected_page

    current_status = trend_scheduler.status()
    if current_status.get("last_error"):
        st.warning(f"Long-term trend collector warning: {current_status['last_error']}")

    if selected_page == DATASTORE_PAGE:
        DataStorePage(presenter=presenter).render()
        return

    if selected_page == PUBLISHER_PAGE:
        PublisherPage(presenter=presenter).render()
        return

    NewsSearchPage(presenter=presenter).render()
