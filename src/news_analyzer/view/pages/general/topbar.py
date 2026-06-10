"""Horizontal top navigation bar, global design tokens, and shared layout helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.view.utils import format_swiss_timestamp

NEWS_SEARCH_PAGE = "news_search"
DATASTORE_PAGE = "datastore"
PUBLISHER_PAGE = "publisher_sentiment"
LONG_TERM_PAGE = "long_term_trends"

_NAV_OPTIONS = [
    ("News Search", NEWS_SEARCH_PAGE, "home"),
    ("Article Library", DATASTORE_PAGE, "grid"),
    ("Publisher Sentiment", PUBLISHER_PAGE, "search"),
    ("Long-Term Trends", LONG_TERM_PAGE, "chart"),
]


def render_topbar(
    default_key: str,
    trend_status: dict[str, object] | None = None,
) -> str:
    """Render the sticky horizontal navigation bar and return the selected page key.

    `trend_status` is the full dict returned by `LongTermTrendScheduler.status()` —
    we use it to drive a four-state collector pill (Live / Idle / Degraded / Stopped).
    """
    _inject_global_styles()
    keys = [key for _, key, _ in _NAV_OPTIONS]
    selected = _resolve_selected_key(default_key=str(default_key or NEWS_SEARCH_PAGE), keys=keys)

    nav_links_html = "".join(
        (
            f'<a class="na-nav-link{" na-nav-link-active" if key == selected else ""}" '
            f'href="?nav={key}" target="_self" aria-label="{escape(label)}">'
            f'<span class="na-nav-icon">{_render_icon(icon_name)}</span>'
            f'<span class="na-nav-label">{escape(label)}</span>'
            "</a>"
        )
        for label, key, icon_name in _NAV_OPTIONS
    )

    status_html = build_collector_status_pill(trend_status or {})

    st.markdown(
        (
            '<nav class="na-navbar" aria-label="Primary">'
            '<div class="na-navbar-brand">'
            f'<span class="na-navbar-logo">{_brand_logo_svg()}</span>'
            '<span class="na-navbar-name">News Analyzer</span>'
            "</div>"
            f'<div class="na-navbar-links">{nav_links_html}</div>'
            f'<div class="na-navbar-status">{status_html}</div>'
            "</nav>"
        ),
        unsafe_allow_html=True,
    )
    return selected


def render_page_header(
    title: str,
    subtitle: str,
    eyebrow: str | None = None,
    meta: str | None = None,
) -> None:
    """Render a consistent page header: optional eyebrow, large title, single subtitle, optional meta tag on the right."""
    eyebrow_html = (
        f'<div class="na-page-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    )
    meta_html = (
        f'<div class="na-page-meta">{escape(meta)}</div>' if meta else ""
    )
    st.markdown(
        (
            '<header class="na-page-header">'
            '<div class="na-page-header-text">'
            f"{eyebrow_html}"
            f'<h1 class="na-page-title">{escape(title)}</h1>'
            f'<p class="na-page-subtitle">{escape(subtitle)}</p>'
            "</div>"
            f"{meta_html}"
            "</header>"
        ),
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, subtitle: str | None = None) -> None:
    """Render a section heading used inside a page (smaller than the page title)."""
    subtitle_html = (
        f'<p class="na-section-subtitle">{escape(subtitle)}</p>' if subtitle else ""
    )
    st.markdown(
        (
            '<div class="na-section-heading">'
            f'<h2 class="na-section-title">{escape(title)}</h2>'
            f"{subtitle_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_search_panel_header(title: str, subtitle: str) -> None:
    """Render the consistent search hero block + injects the marker the panel CSS
    keys off of. Call this **immediately before** `st.container(border=True)` that
    holds the form widgets — the next border container will pick up the highlighted
    background style.
    """
    st.markdown(
        (
            '<div class="na-search-hero">'
            f'<p class="na-search-hero-title">{escape(title)}</p>'
            f'<p class="na-search-hero-sub">{escape(subtitle)}</p>'
            "</div>"
            '<div class="na-search-panel-marker"></div>'
        ),
        unsafe_allow_html=True,
    )


def render_loading_card_html(title: str, subtitle: str) -> str:
    """Return HTML for a centered loading card with a CSS spinner.

    Used by the News Search loading screen — the progress bar text is appended
    via Streamlit's `st.progress`, which renders inside the same vertical block.
    """
    return (
        '<div class="na-loading-card">'
        '<div class="na-loading-spinner" aria-hidden="true"></div>'
        f'<p class="na-loading-title">{escape(title)}</p>'
        f'<p class="na-loading-sub">{escape(subtitle)}</p>'
        "</div>"
    )


def render_loading_pill_html(label: str) -> str:
    """Return HTML for a compact spinner pill — pair with `st.empty()` for short loads."""
    return (
        '<div style="display:flex;justify-content:center;margin:0.6rem 0 0.8rem;">'
        '<span class="na-loading-inline">'
        '<span class="na-loading-inline-dot" aria-hidden="true"></span>'
        f"<span>{escape(label)}</span>"
        "</span>"
        "</div>"
    )


def render_empty_state(
    title: str,
    message: str,
    icon: str = "📭",
    hint: str | None = None,
) -> None:
    """Render a consistent empty-state card with title, message, and optional hint."""
    hint_html = (
        f'<p class="na-empty-hint">{escape(hint)}</p>' if hint else ""
    )
    st.markdown(
        (
            '<div class="na-empty-state">'
            f'<div class="na-empty-icon">{escape(icon)}</div>'
            f'<p class="na-empty-title">{escape(title)}</p>'
            f'<p class="na-empty-message">{escape(message)}</p>'
            f"{hint_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _resolve_selected_key(default_key: str, keys: list[str]) -> str:
    nav_query = st.query_params.get("nav", "")
    if isinstance(nav_query, list):
        nav_query = nav_query[0] if nav_query else ""
    selected = str(nav_query or default_key or NEWS_SEARCH_PAGE)
    if selected not in keys:
        return NEWS_SEARCH_PAGE
    return selected


def build_collector_status_pill(trend_status: dict[str, object]) -> str:
    """Render a four-state pill that reflects whether collection is actually happening.

    The check is data-driven, not thread-driven: in production the in-process
    scheduler is disabled and the daily collection runs in a separate Cloud Run
    Job, so a missing background thread does *not* mean "stopped". We look at the
    most recent `last_run_at` (which the view enriches from Firestore's latest
    `ingested_at`) and decide based on freshness.

    - Stopped: no past run found AND no in-process thread → daily collector is
      not configured at all.
    - Idle: a past run exists but is older than the expected interval (job is
      configured, just waiting for the next scheduled trigger), OR an in-process
      thread is running but hasn't completed a cycle yet.
    - Degraded: last cycle errored.
    - Live: last run is within the expected interval window.
    """
    running = bool(trend_status.get("running", False))
    last_run = str(trend_status.get("last_run_at", "") or "")
    last_error = str(trend_status.get("last_error", "") or "").strip()
    interval_minutes = int(trend_status.get("interval_minutes", 0) or 0)

    last_result = trend_status.get("last_result", {}) or {}
    totals = last_result.get("totals", {}) if isinstance(last_result, dict) else {}
    saved_count = int(totals.get("saved", 0) or 0)

    last_run_dt = _parse_iso(last_run)
    age_minutes: float | None = None
    if last_run_dt is not None:
        age_minutes = (datetime.now(timezone.utc) - last_run_dt).total_seconds() / 60.0

    freshness_threshold_minutes = (
        max(interval_minutes * 2, 60) if interval_minutes > 0 else 48 * 60
    )

    if last_error:
        state_class = "na-status-degraded"
        state_label = "Degraded"
        primary_line = f"Last cycle failed: {last_error}"
    elif last_run_dt is None and not running:
        # Never collected and no thread → daily container is not running.
        state_class = "na-status-stopped"
        state_label = "Stopped"
        primary_line = "No collection runs found — daily collector may not be configured."
    elif last_run_dt is not None and age_minutes is not None and age_minutes <= freshness_threshold_minutes:
        state_class = "na-status-running"
        state_label = "Live"
        if saved_count > 0:
            primary_line = f"Last cycle saved {saved_count} new article(s)."
        else:
            primary_line = "Recent collection cycle completed."
    else:
        # Records exist but are stale, or thread is up without a completed run.
        state_class = "na-status-idle"
        state_label = "Idle"
        if last_run_dt is None:
            primary_line = "Collector ready — first cycle hasn't completed yet."
        else:
            primary_line = "No recent collection cycle — waiting for the next scheduled run."

    tooltip_parts = [primary_line]
    if interval_minutes > 0:
        tooltip_parts.append(f"Expected every {interval_minutes} min.")
    formatted_last_run = format_swiss_timestamp(last_run) if last_run else ""
    if formatted_last_run and formatted_last_run != "-":
        tooltip_parts.append(f"Last run (Zurich): {formatted_last_run}.")

    tooltip = " ".join(tooltip_parts)
    return (
        f'<span class="na-status-pill {state_class}" title="{escape(tooltip)}" role="status">'
        '<span class="na-status-dot" aria-hidden="true"></span>'
        f'<span class="na-status-label">Collector · {escape(state_label)}</span>'
        "</span>"
    )


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except Exception:  # noqa: BLE001
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _inject_global_styles() -> None:
    st.markdown(_GLOBAL_STYLES, unsafe_allow_html=True)


def _brand_logo_svg() -> str:
    return (
        '<svg viewBox="0 0 32 32" aria-hidden="true">'
        '<rect x="2" y="2" width="28" height="28" rx="8" fill="#ffffff"></rect>'
        '<path d="M9 22V10l8 9V10" stroke="#3a63d4" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"></path>'
        '<circle cx="22.5" cy="20" r="2" fill="#3a63d4"></circle>'
        "</svg>"
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
        "search": (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<circle cx="11" cy="11" r="6.5"></circle>'
            '<path d="m16 16 4 4"></path>'
            "</svg>"
        ),
        "chart": (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M4 19h16"></path>'
            '<path d="M7 16V10"></path>'
            '<path d="M12 16V6"></path>'
            '<path d="M17 16v-3"></path>'
            "</svg>"
        ),
    }
    return icons.get(icon_name, icons["grid"])


_GLOBAL_STYLES = """
<style>
    :root {
        --na-primary: #3a63d4;
        --na-primary-deep: #1e3a8a;
        --na-primary-soft: #e7edfb;
        --na-text: #1f2937;
        --na-muted: #64748b;
        --na-border: #e3e7ef;
        --na-surface: #ffffff;
        --na-surface-soft: #f6f8fc;
        --na-success: #1e8449;
        --na-warning: #d4a017;
    }

    /* Hide Streamlit's left sidebar entirely (and its collapsed hamburger). */
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    /* Give the main content a little breathing room at the top so the navbar sits high. */
    [data-testid="stAppViewContainer"] .main .block-container {
        padding-top: 0.6rem;
        padding-bottom: 3rem;
        max-width: 1280px;
    }

    /* Soften the overall app background so cards pop a bit more. */
    [data-testid="stAppViewContainer"] {
        background: #f4f6fb;
    }

    /* === Top navigation bar ============================================= */
    .na-navbar {
        position: sticky;
        top: 0;
        z-index: 100;
        display: flex;
        align-items: center;
        gap: 1.25rem;
        padding: 0.65rem 1.1rem;
        margin: -0.6rem -1rem 1.5rem -1rem;
        background: linear-gradient(120deg, #1e3a8a 0%, #3a63d4 55%, #4f7bd9 100%);
        border-bottom: none;
        box-shadow: 0 10px 30px -18px rgba(30, 58, 138, 0.55), 0 1px 0 rgba(255, 255, 255, 0.08) inset;
        color: #ffffff;
    }

    .na-navbar-brand,
    .na-navbar .na-navbar-brand {
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        font-weight: 700;
        color: #ffffff !important;
        white-space: nowrap;
    }

    .na-navbar-logo svg {
        width: 28px;
        height: 28px;
        display: block;
        box-shadow: 0 4px 14px -6px rgba(255, 255, 255, 0.5);
        border-radius: 8px;
    }

    .na-navbar-name,
    .na-navbar .na-navbar-name {
        font-size: 1.05rem;
        letter-spacing: 0.01em;
        color: #ffffff !important;
    }

    .na-navbar-links {
        display: flex;
        align-items: center;
        gap: 0.3rem;
        flex: 0 1 auto;
        justify-content: flex-start;
        margin-left: 0.6rem;
        flex-wrap: wrap;
    }

    /* High specificity + !important so Streamlit's link styles can't override. */
    .na-navbar a.na-nav-link,
    .na-navbar a.na-nav-link:link,
    .na-navbar a.na-nav-link:visited {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.45rem 0.9rem;
        border-radius: 999px;
        color: rgba(255, 255, 255, 0.92) !important;
        background: transparent;
        text-decoration: none !important;
        font-weight: 500;
        font-size: 0.92rem;
        transition: background 140ms ease, color 140ms ease, transform 140ms ease;
    }

    .na-navbar a.na-nav-link:hover {
        background: rgba(255, 255, 255, 0.18) !important;
        color: #ffffff !important;
    }

    .na-navbar a.na-nav-link-active,
    .na-navbar a.na-nav-link-active:link,
    .na-navbar a.na-nav-link-active:visited {
        background: #ffffff !important;
        color: #1e3a8a !important;
        font-weight: 600;
        box-shadow: 0 6px 16px -10px rgba(15, 23, 42, 0.4);
    }

    .na-navbar a.na-nav-link .na-nav-label,
    .na-navbar a.na-nav-link-active .na-nav-label {
        color: inherit !important;
    }

    .na-nav-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 16px;
        height: 16px;
        color: currentColor;
    }

    .na-nav-icon svg {
        width: 16px;
        height: 16px;
        stroke: currentColor;
        fill: none;
        stroke-width: 1.9;
        stroke-linecap: round;
        stroke-linejoin: round;
    }

    .na-navbar-status {
        display: inline-flex;
        align-items: center;
        white-space: nowrap;
        margin-left: auto;
    }

    /* === Status pill ==================================================== */
    .na-navbar .na-status-pill {
        background: rgba(255, 255, 255, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.22);
        color: #ffffff;
    }

    .na-navbar .na-status-label {
        color: #ffffff;
    }

    .na-status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.32rem 0.75rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 500;
        border: 1px solid var(--na-border);
        background: var(--na-surface);
        color: var(--na-muted);
        cursor: help;
    }

    .na-status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--na-muted);
        box-shadow: 0 0 0 0 rgba(0, 0, 0, 0);
    }

    .na-status-running .na-status-dot {
        background: #4ade80;
        box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.22);
    }

    .na-status-idle .na-status-dot {
        background: #60a5fa;
        box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.22);
    }

    .na-status-degraded .na-status-dot {
        background: #f59e0b;
        box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.25);
    }

    .na-status-stopped .na-status-dot {
        background: #cbd5e1;
    }

    /* In-page inline status (used outside the navbar). */
    .na-inline-status {
        margin: 0.2rem 0 0.9rem;
    }

    .na-inline-status .na-status-pill {
        font-size: 0.88rem;
        padding: 0.42rem 0.9rem;
    }

    .na-inline-status .na-status-running {
        background: rgba(74, 222, 128, 0.12);
        border-color: rgba(74, 222, 128, 0.35);
        color: #166534;
    }

    .na-inline-status .na-status-idle {
        background: rgba(96, 165, 250, 0.12);
        border-color: rgba(96, 165, 250, 0.35);
        color: #1e40af;
    }

    .na-inline-status .na-status-degraded {
        background: rgba(245, 158, 11, 0.14);
        border-color: rgba(245, 158, 11, 0.4);
        color: #92400e;
    }

    .na-inline-status .na-status-stopped {
        background: var(--na-surface-soft);
        color: var(--na-muted);
    }

    /* === Page header ==================================================== */
    .na-page-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1.5rem;
        padding: 1.1rem 1.25rem 1.2rem;
        margin: 0 0 1.5rem;
        background: var(--na-surface);
        border: 1px solid var(--na-border);
        border-radius: 14px;
        box-shadow: 0 1px 0 rgba(15, 23, 42, 0.02);
    }

    .na-page-eyebrow {
        text-transform: uppercase;
        font-size: 0.72rem;
        letter-spacing: 0.09em;
        color: var(--na-primary);
        font-weight: 600;
        margin-bottom: 0.3rem;
    }

    .na-page-title {
        font-size: 1.7rem;
        line-height: 1.15;
        margin: 0;
        color: var(--na-text);
        font-weight: 700;
    }

    .na-page-subtitle {
        margin: 0.35rem 0 0;
        color: var(--na-muted);
        font-size: 0.98rem;
        max-width: 70ch;
    }

    .na-page-meta {
        flex-shrink: 0;
        padding: 0.4rem 0.7rem;
        border-radius: 999px;
        background: var(--na-surface-soft);
        color: var(--na-muted);
        font-size: 0.78rem;
        white-space: nowrap;
    }

    /* === Section heading ================================================ */
    .na-section-heading {
        margin: 0.6rem 0 0.6rem;
    }

    .na-section-title {
        font-size: 1.12rem;
        margin: 0;
        color: var(--na-text);
        font-weight: 600;
        letter-spacing: 0.005em;
    }

    .na-section-subtitle {
        margin: 0.2rem 0 0;
        color: var(--na-muted);
        font-size: 0.9rem;
    }

    /* === Empty state card ============================================== */
    .na-empty-state {
        text-align: center;
        padding: 2.4rem 1.4rem;
        margin: 1rem 0;
        background: var(--na-surface);
        border: 1px dashed var(--na-border);
        border-radius: 14px;
    }

    .na-empty-icon {
        font-size: 2.2rem;
        line-height: 1;
        margin-bottom: 0.5rem;
    }

    .na-empty-title {
        margin: 0;
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--na-text);
    }

    .na-empty-message {
        margin: 0.35rem auto 0;
        color: var(--na-muted);
        font-size: 0.94rem;
        max-width: 50ch;
    }

    .na-empty-hint {
        margin: 0.85rem auto 0;
        color: var(--na-primary);
        font-size: 0.86rem;
        font-weight: 500;
        max-width: 50ch;
    }

    /* === Search hero header (sits above the search panel) =============== */
    .na-search-hero {
        text-align: left;
        padding: 0.4rem 0.2rem 0.9rem;
        margin: 0 0 -0.4rem;
    }

    .na-search-hero-title {
        font-size: 1.08rem;
        font-weight: 600;
        color: var(--na-text);
        margin: 0;
    }

    .na-search-hero-sub {
        margin: 0.25rem 0 0;
        color: var(--na-muted);
        font-size: 0.88rem;
        max-width: 72ch;
    }

    /* === Card style for every st.container(border=True) ================ */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--na-surface);
        border: 1px solid var(--na-border) !important;
        border-radius: 14px !important;
        padding: 1.1rem 1.2rem !important;
        box-shadow: 0 14px 36px -28px rgba(15, 23, 42, 0.18),
                    0 1px 0 rgba(255, 255, 255, 0.6) inset;
    }

    /* The search panel uses a coloured gradient surface to stand out from
       the page background — applied via a CSS class injected next to the
       Streamlit container. Markers are emitted by inject_search_panel_marker(). */
    /* Tighter spacing for the two-toggle row below the time-window selector. */
    .na-toggle-row + div [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
        margin-top: -0.2rem;
    }

    /* Don't let Streamlit fade widgets while a background re-run is in progress —
       the search form should stay visually crisp while results load below it. */
    [data-stale="true"],
    [data-stale="true"] [data-testid="stForm"],
    [data-stale="true"] [data-testid="stVerticalBlockBorderWrapper"] {
        opacity: 1 !important;
        filter: none !important;
    }

    /* === Loading screen card (rendered below the search panel) ========== */
    .na-loading-card {
        margin: 1.6rem auto 0;
        max-width: 720px;
        padding: 1.8rem 1.6rem 1.4rem;
        background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
        border: 1px solid #cdd7ef;
        border-radius: 18px;
        text-align: center;
        box-shadow: 0 28px 56px -28px rgba(58, 99, 212, 0.4),
                    0 0 0 4px rgba(58, 99, 212, 0.06);
    }

    .na-loading-title {
        margin: 0 0 0.3rem;
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--na-text);
    }

    .na-loading-sub {
        margin: 0 0 0.9rem;
        color: var(--na-muted);
        font-size: 0.9rem;
    }

    .na-loading-spinner {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        margin: 0 auto 1rem;
        border: 4px solid #e7edfb;
        border-top-color: var(--na-primary);
        border-right-color: #6b8df2;
        animation: na-spin 0.85s linear infinite;
        box-shadow: 0 6px 18px -10px rgba(58, 99, 212, 0.35);
    }

    /* Compact inline spinner — used inside short-running loading rows. */
    .na-loading-inline {
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.55rem 0.95rem;
        background: rgba(58, 99, 212, 0.08);
        border: 1px solid rgba(58, 99, 212, 0.22);
        border-radius: 999px;
        color: var(--na-primary-deep);
        font-size: 0.9rem;
        font-weight: 500;
    }

    .na-loading-inline-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 2px solid #cdd7ef;
        border-top-color: var(--na-primary);
        animation: na-spin 0.75s linear infinite;
    }

    @keyframes na-spin {
        to { transform: rotate(360deg); }
    }

    .na-search-panel-marker + div [data-testid="stVerticalBlockBorderWrapper"] {
        position: relative;
        background: linear-gradient(180deg, #eef3fd 0%, #dde6f7 100%);
        border: 2px solid var(--na-primary) !important;
        border-radius: 16px !important;
        padding-top: 1.4rem !important;
        box-shadow: 0 24px 50px -28px rgba(58, 99, 212, 0.45),
                    0 0 0 4px rgba(58, 99, 212, 0.08),
                    0 1px 0 rgba(255, 255, 255, 0.7) inset;
    }

    .na-search-panel-marker + div [data-testid="stVerticalBlockBorderWrapper"]::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, var(--na-primary) 0%, #6b8df2 60%, #a8c0fa 100%);
        border-top-left-radius: 14px;
        border-top-right-radius: 14px;
    }

    /* Inputs inside the search panel get a clearly raised, bordered look so they
       sit on TOP of the tinted panel surface instead of blending in. */
    .na-search-panel-marker + div [data-testid="stTextInput"] input,
    .na-search-panel-marker + div [data-testid="stNumberInput"] input {
        background: #ffffff !important;
        border: 2px solid var(--na-primary) !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 12px -4px rgba(58, 99, 212, 0.28),
                    0 0 0 4px rgba(58, 99, 212, 0.10) !important;
        color: var(--na-text) !important;
        min-height: 2.7rem !important;
    }

    .na-search-panel-marker + div [data-testid="stTextInput"] input::placeholder {
        color: #94a3c4 !important;
    }

    .na-search-panel-marker + div [data-testid="stTextInput"] input:hover,
    .na-search-panel-marker + div [data-testid="stNumberInput"] input:hover {
        background: #fbfcff !important;
        box-shadow: 0 6px 16px -6px rgba(58, 99, 212, 0.32),
                    0 0 0 4px rgba(58, 99, 212, 0.14) !important;
    }

    .na-search-panel-marker + div [data-testid="stTextInput"] input:focus,
    .na-search-panel-marker + div [data-testid="stNumberInput"] input:focus {
        background: #fbfcff !important;
        border-color: var(--na-primary-deep) !important;
        box-shadow: 0 6px 18px -6px rgba(58, 99, 212, 0.35),
                    0 0 0 5px rgba(58, 99, 212, 0.22) !important;
    }

    .na-search-panel-marker + div [data-testid="stSelectbox"] > div > div,
    .na-search-panel-marker + div [data-testid="stMultiSelect"] > div > div,
    .na-search-panel-marker + div [data-testid="stDateInput"] > div > div {
        background: #ffffff !important;
        border: 2px solid var(--na-primary) !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 12px -4px rgba(58, 99, 212, 0.28),
                    0 0 0 4px rgba(58, 99, 212, 0.10) !important;
        min-height: 2.7rem !important;
    }

    .na-search-panel-marker + div [data-testid="stSelectbox"] > div > div:hover,
    .na-search-panel-marker + div [data-testid="stMultiSelect"] > div > div:hover,
    .na-search-panel-marker + div [data-testid="stDateInput"] > div > div:hover {
        background: #fbfcff !important;
        box-shadow: 0 6px 16px -6px rgba(58, 99, 212, 0.32),
                    0 0 0 4px rgba(58, 99, 212, 0.14) !important;
    }

    /* Slider track + thumb inside search panels — match the primary accent. */
    .na-search-panel-marker + div [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
        background: var(--na-primary) !important;
        border: 2px solid #ffffff !important;
        box-shadow: 0 0 0 3px rgba(58, 99, 212, 0.22) !important;
    }

    /* Section labels inside search panels — slightly stronger so each filter group reads as its own block. */
    .na-search-panel-marker + div [data-testid="stWidgetLabel"] p,
    .na-search-panel-marker + div label p {
        font-weight: 600 !important;
        color: var(--na-primary-deep) !important;
    }

    /* Modernize all text inputs / selectboxes / primary buttons app-wide. */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {
        border-radius: 10px;
    }

    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus {
        border-color: var(--na-primary) !important;
        box-shadow: 0 0 0 3px rgba(58, 99, 212, 0.15) !important;
    }

    [data-testid="stSelectbox"] > div > div,
    [data-testid="stMultiSelect"] > div > div {
        border-radius: 10px;
    }

    .stButton > button {
        border-radius: 10px;
        font-weight: 500;
        letter-spacing: 0.005em;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(120deg, #3a63d4 0%, #2548b0 100%);
        border: none;
        box-shadow: 0 10px 22px -14px rgba(58, 99, 212, 0.55);
    }

    .stButton > button[kind="primary"]:hover {
        filter: brightness(1.06);
        transform: translateY(-1px);
    }

    [data-testid="stExpander"] {
        border-radius: 12px;
        border: 1px solid var(--na-border);
        background: var(--na-surface);
    }

    /* === In-page tab styling (Article Library mode switch) =============== */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.25rem;
        border-bottom: 1px solid var(--na-border);
        background: transparent;
    }

    [data-testid="stTabs"] [data-baseweb="tab"] {
        height: 2.6rem;
        padding: 0 1.1rem;
        background: transparent;
        font-weight: 500;
        color: var(--na-muted);
        border-radius: 10px 10px 0 0;
    }

    [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
        color: var(--na-primary);
        background: var(--na-primary-soft);
        font-weight: 600;
    }

    [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
        background: var(--na-primary);
        height: 3px;
    }

    /* Slightly taller inputs feel more modern. */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 2.55rem;
    }

    /* === Small responsive cleanup ======================================= */
    @media (max-width: 820px) {
        .na-navbar {
            gap: 0.6rem;
            padding: 0.5rem 0.6rem;
        }
        .na-navbar-name { display: none; }
        .na-nav-label { display: none; }
        .na-nav-link { padding: 0.45rem 0.55rem; }
        .na-status-label { display: none; }
        .na-status-pill { padding: 0.32rem 0.45rem; }
    }
</style>
"""
