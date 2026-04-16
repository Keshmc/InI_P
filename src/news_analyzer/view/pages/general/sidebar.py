"""Sidebar components shared across view pages."""

from __future__ import annotations

import streamlit as st

from news_analyzer.view.utils import format_swiss_timestamp

NEWS_SEARCH_PAGE = "news_search"
DATASTORE_PAGE = "datastore"
_NAV_OPTIONS = [
    ("News Search", NEWS_SEARCH_PAGE, "home"),
    ("Datastore", DATASTORE_PAGE, "grid"),
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
    keys = [key for _, key, _ in _NAV_OPTIONS]
    selected = _resolve_selected_key(default_key=str(default_key or NEWS_SEARCH_PAGE), keys=keys)

    st.sidebar.markdown('<div class="nav-stack">', unsafe_allow_html=True)
    for label, key, icon_name in _NAV_OPTIONS:
        css_class = "nav-line nav-line-active" if key == selected else "nav-line"
        st.sidebar.markdown(
            (
                f'<a class="{css_class}" href="?nav={key}" target="_self">'
                f'<span class="nav-icon">{_render_icon(icon_name)}</span>'
                f'<span class="nav-label">{label}</span>'
                "</a>"
            ),
            unsafe_allow_html=True,
        )
    st.sidebar.markdown("</div>", unsafe_allow_html=True)

    st.sidebar.divider()
    state_label = "running" if auto_trend_running else "stopped"
    st.sidebar.caption(f"Trend Collector: {state_label}")

    if auto_trend_interval_minutes > 0:
        st.sidebar.caption(f"Intervall: alle {auto_trend_interval_minutes} Minute(n)")
    if auto_trend_last_run:
        st.sidebar.caption(f"Letzter Lauf (CH): {format_swiss_timestamp(auto_trend_last_run)}")

    return selected


def _resolve_selected_key(default_key: str, keys: list[str]) -> str:
    nav_query = st.query_params.get("nav", "")
    if isinstance(nav_query, list):
        nav_query = nav_query[0] if nav_query else ""
    selected = str(nav_query or default_key or NEWS_SEARCH_PAGE)
    if selected not in keys:
        return NEWS_SEARCH_PAGE
    return selected


def _inject_sidebar_styles() -> None:
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] .nav-stack {
                display: block;
                margin-top: 0.2rem;
            }

            [data-testid="stSidebar"] .nav-line {
                display: flex;
                align-items: center;
                gap: 0.55rem;
                width: 100%;
                text-decoration: none;
                color: #68758a;
                background: transparent;
                border: none;
                border-radius: 8px;
                padding: 0.55rem 0.62rem;
                margin-bottom: 0.25rem;
                line-height: 1.1rem;
                font-weight: 500;
                transition: all 120ms ease;
            }

            [data-testid="stSidebar"] .nav-line:hover {
                color: #4b5a70;
                background: #f3f5f9;
            }

            [data-testid="stSidebar"] .nav-line-active {
                background: #e7edfb;
                color: #3a63d4;
                font-weight: 600;
            }

            [data-testid="stSidebar"] .nav-icon {
                width: 16px;
                height: 16px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: currentColor;
                flex: 0 0 16px;
            }

            [data-testid="stSidebar"] .nav-icon svg {
                width: 16px;
                height: 16px;
                stroke: currentColor;
                fill: none;
                stroke-width: 1.9;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            [data-testid="stSidebar"] .nav-label {
                font-size: 0.92rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_icon(icon_name: str) -> str:
    icons: dict[str, str] = {
        "home": (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M3 10.8 12 4l9 6.8"></path>'
            '<path d="M5.5 10.4V20h13V10.4"></path>'
            "</svg>"
        ),
        "grid": (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<rect x="4" y="4" width="6.5" height="6.5" rx="1.3"></rect>'
            '<rect x="13.5" y="4" width="6.5" height="6.5" rx="1.3"></rect>'
            '<rect x="4" y="13.5" width="6.5" height="6.5" rx="1.3"></rect>'
            '<rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.3"></rect>'
            "</svg>"
        ),
    }
    return icons.get(icon_name, icons["grid"])
