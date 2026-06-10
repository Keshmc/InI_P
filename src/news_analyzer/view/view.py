"""Streamlit view orchestration for navigation and page rendering."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from news_analyzer.model.trends import get_long_term_trend_scheduler, load_long_term_trend_config
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.datastore.datastore_page import DataStorePage
from news_analyzer.view.pages.general.topbar import (
    DATASTORE_PAGE,
    LONG_TERM_PAGE,
    NEWS_SEARCH_PAGE,
    PUBLISHER_PAGE,
    render_topbar,
)
from news_analyzer.view.pages.long_term.long_term_page import LongTermPage
from news_analyzer.view.pages.publishers.publisher_page import PublisherPage
from news_analyzer.view.pages.search.search_page import NewsSearchPage


_LATEST_INGESTED_CACHE_KEY = "_long_term_latest_ingested_cache"
_LATEST_INGESTED_TTL_SECONDS = 300


def _bootstrap_state() -> None:
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = NEWS_SEARCH_PAGE


def _datastore_latest_ingested_at(presenter: NewsPresenter) -> str:
    """Return the most recent `ingested_at` ISO string from Firestore, cached per session.

    In production the daily Cloud Run Job persists records from a separate process,
    so the webapp's in-memory scheduler state never reflects real runs. This lookup
    lets the navbar pill and per-page metrics show the external job's last execution.
    """
    cache = st.session_state.get(_LATEST_INGESTED_CACHE_KEY)
    now_ts = datetime.now(timezone.utc).timestamp()
    if isinstance(cache, dict) and (now_ts - float(cache.get("fetched_at", 0))) < _LATEST_INGESTED_TTL_SECONDS:
        return str(cache.get("value", "")).strip()

    repo = presenter.datastore_repository
    value = ""
    if repo is not None and repo.is_available:
        try:
            value = repo.get_latest_ingested_at()
        except Exception:  # noqa: BLE001
            value = ""

    st.session_state[_LATEST_INGESTED_CACHE_KEY] = {"value": value, "fetched_at": now_ts}
    return value


def run_view(presenter: NewsPresenter) -> None:
    """Render Streamlit app entrypoint."""
    st.set_page_config(
        page_title="News Analyzer",
        page_icon="N",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _bootstrap_state()

    trend_config = load_long_term_trend_config()
    trend_scheduler = get_long_term_trend_scheduler(
        pipeline=presenter.pipeline,
        config=trend_config,
    )
    trend_scheduler.set_enabled(bool(trend_config.enabled))
    trend_status = trend_scheduler.status()

    # The in-process `last_run_at` is empty in production (Cloud Scheduler runs the
    # job in a separate process). Fall back to the most recent Firestore record so
    # the pill reflects what the external collector actually did.
    external_last_run = _datastore_latest_ingested_at(presenter)
    if external_last_run and not str(trend_status.get("last_run_at", "") or "").strip():
        trend_status["last_run_at"] = external_last_run

    selected_page = render_topbar(
        default_key=st.session_state.nav_page,
        trend_status=trend_status,
    )
    st.session_state.nav_page = selected_page

    current_status = trend_scheduler.status()
    if external_last_run and not str(current_status.get("last_run_at", "") or "").strip():
        current_status["last_run_at"] = external_last_run
    if current_status.get("last_error"):
        st.warning(f"Background collector issue: {current_status['last_error']}")

    if selected_page == DATASTORE_PAGE:
        DataStorePage(presenter=presenter).render()
        return

    if selected_page == PUBLISHER_PAGE:
        PublisherPage(presenter=presenter).render()
        return

    if selected_page == LONG_TERM_PAGE:
        LongTermPage(
            presenter=presenter,
            trend_config=trend_config,
            trend_status=current_status,
            scheduler=trend_scheduler,
        ).render()
        return

    NewsSearchPage(presenter=presenter).render()
