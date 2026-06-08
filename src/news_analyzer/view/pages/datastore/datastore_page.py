"""Article library page with overview analytics and filtered search."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.model import DatastoreInsights, DatastoreQuery, build_datastore_insights
from news_analyzer.model.trends import DEFAULT_LONG_TERM_TICKERS
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.general.topbar import (
    render_empty_state,
    render_loading_card_html,
    render_page_header,
    render_search_panel_header,
    render_section_heading,
)
from news_analyzer.view.pages.search.sentiment_score import render_sentiment_meter
from news_analyzer.view.utils import (
    build_export_file_stem,
    format_swiss_date_time,
    render_export_downloads,
    render_sentiment_donut,
)


class DataStorePage:
    """Owns the article library overview and saved-article search UI."""

    _INDUSTRY_SECTOR_OPTIONS = [
        "Any",
        "Technology",
        "Energy",
        "Healthcare",
        "Financials",
        "Industrials",
        "Consumer",
        "Communication Services",
        "Materials",
        "Real Estate",
        "Utilities",
    ]

    _OVERVIEW_STATE_KEY = "article_library_overview_payload"
    _OVERVIEW_MESSAGE_KEY = "article_library_overview_message"
    _OVERVIEW_OK_KEY = "article_library_overview_ok"

    _SEARCH_STATE_KEY = "article_library_search_payload"
    _SEARCH_MESSAGE_KEY = "article_library_search_message"
    _SEARCH_OK_KEY = "article_library_search_ok"

    _LIMIT = 50000

    def __init__(self, presenter: NewsPresenter) -> None:
        self.presenter = presenter

    def render(self) -> None:
        render_page_header(
            eyebrow="Collection",
            title="Article Library",
            subtitle="Browse, search, and analyze your saved article collection.",
            meta="Timestamps in Europe/Zurich",
        )

        tab_overview, tab_search, tab_long_term = st.tabs(
            ["Overview", "Search", "Long-Term Ticker"]
        )

        with tab_overview:
            self._render_overview_mode()

        with tab_search:
            self._render_search_mode()

        with tab_long_term:
            self._render_long_term_analysis_mode()

    def _render_overview_mode(self) -> None:
        if self._OVERVIEW_STATE_KEY not in st.session_state:
            loading_zone = st.empty()
            loading_zone.markdown(
                render_loading_card_html(
                    title="Loading your library…",
                    subtitle="Pulling saved articles from the datastore — this may take a few seconds.",
                ),
                unsafe_allow_html=True,
            )
            try:
                self._load_overview_payload(force_reload=False)
            finally:
                loading_zone.empty()
        else:
            self._load_overview_payload(force_reload=False)

        payload = st.session_state.get(self._OVERVIEW_STATE_KEY, {})
        self._render_message(
            message=str(st.session_state.get(self._OVERVIEW_MESSAGE_KEY, "")),
            ok=bool(st.session_state.get(self._OVERVIEW_OK_KEY, True)),
        )

        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records:
            render_empty_state(
                title="Your library is empty",
                message="No saved articles yet. Start by running a search on the News Search page.",
                icon="📭",
                hint="News Search → enter a keyword → Analyze coverage",
            )
            return

        insights = build_datastore_insights(records)
        with st.container(border=True):
            self._render_facts(records=records, payload=payload, insights=insights)
            self._render_sentiment_section(insights=insights)
        self._render_trend_chart(insights=insights)
        self._render_entity_chart(insights=insights)
        self._render_publisher_chart(insights=insights)
        self._render_article_table(insights=insights, title="Stored Articles")
        st.divider()
        render_section_heading("Export")
        render_export_downloads(
            sections=self._build_overview_export_sections(records=records, payload=payload, insights=insights),
            file_stem=build_export_file_stem(prefix="article_library_overview"),
            key_prefix="article_library_overview_export",
            caption="Export the full library overview as CSV, JSON, or Excel.",
        )

    def _render_search_mode(self) -> None:
        default_start = date.today() - timedelta(days=30)
        default_end = date.today()

        left_pad, center, right_pad = st.columns([1, 3, 1])
        del left_pad, right_pad

        with center:
            render_search_panel_header(
                title="Search your saved library",
                subtitle="Filter by keyword, sector, sentiment, or date.",
            )

            with st.container(border=True):
                with st.form("article_library_search_form"):
                    company_text = st.text_input(
                        "Search",
                        placeholder="e.g. NVIDIA, Apple, Tesla",
                        help="Enter one or more keywords (company, ticker, topic). Separate multiple with commas.",
                        key="article_library_search_companies",
                    ).strip()

                    filter_col_a, filter_col_b = st.columns(2, gap="medium")
                    with filter_col_a:
                        sector_text = st.selectbox(
                            "Industry sector",
                            options=self._INDUSTRY_SECTOR_OPTIONS,
                            key="article_library_search_sector",
                            help="Choose a standard sector label for a more reliable match.",
                        )
                    with filter_col_b:
                        result_limit = st.selectbox(
                            "Max results",
                            options=[50, 100, 250, 500, 1000, 2500, 5000, 10000],
                            index=4,
                            key="article_library_result_limit",
                            help="Higher limits take longer to load.",
                        )

                    sentiment_range = st.slider(
                        "Sentiment range",
                        min_value=-1.0,
                        max_value=1.0,
                        value=(-1.0, 1.0),
                        step=0.05,
                        key="article_library_sentiment_range",
                        help="Restrict matches by sentiment score. Leave at (−1.0, 1.0) for all.",
                    )

                    date_range = st.date_input(
                        "Publication range",
                        value=(default_start, default_end),
                        key="article_library_date_range",
                        help="Only saved articles published in this window are returned.",
                    )

                    search_clicked = st.form_submit_button(
                        "Run search", type="primary", width="stretch"
                    )

        # Single slot for the results area. While the search runs we write the
        # loading card into it; when results are ready we overwrite the same slot
        # with the actual content — so old results are never visible during the wait.
        content_zone = st.empty()

        if search_clicked:
            min_sent, max_sent = sentiment_range
            with content_zone.container():
                st.markdown(
                    render_loading_card_html(
                        title="Filtering your library…",
                        subtitle="Scanning saved articles by keyword, sector, sentiment, and date.",
                    ),
                    unsafe_allow_html=True,
                )
            self._run_filtered_search(
                company_text=company_text,
                sector_text="" if sector_text == "Any" else sector_text,
                min_sentiment=float(min_sent),
                max_sentiment=float(max_sent),
                date_range=date_range,
                result_limit=int(result_limit),
            )

        payload = st.session_state.get(self._SEARCH_STATE_KEY, {})
        message = str(st.session_state.get(self._SEARCH_MESSAGE_KEY, ""))
        ok = bool(st.session_state.get(self._SEARCH_OK_KEY, True))

        if not isinstance(payload, dict) or not payload:
            with content_zone.container():
                self._render_message(message=message, ok=ok)
            return

        records = payload.get("records", [])
        filters_summary = payload.get("filters_summary", [])

        with content_zone.container():
            self._render_message(message=message, ok=ok)

            if filters_summary:
                render_section_heading("Active Filters")
                st.dataframe(filters_summary, width="stretch", hide_index=True)

            if not records:
                render_empty_state(
                    title="No matching articles",
                    message="The current filters didn't return any saved articles.",
                    icon="🪹",
                    hint="Try widening the date range or sentiment range, or remove the sector filter.",
                )
                return

            insights = build_datastore_insights(records)
            self._render_search_summary(records=records, payload=payload, insights=insights)
            self._render_sentiment_section(insights=insights)
            self._render_publisher_chart(insights=insights)
            self._render_trend_chart(insights=insights)
            self._render_article_table(insights=insights, title="Matching Articles")
            st.divider()
            render_section_heading("Export")
            render_export_downloads(
                sections=self._build_search_export_sections(payload=payload, insights=insights),
                file_stem=build_export_file_stem(
                    prefix="article_library_search",
                    parts=[
                        ", ".join(self._parse_company_tokens(st.session_state.get("article_library_search_companies", ""))),
                        str(st.session_state.get("article_library_search_sector", "")).strip(),
                    ],
                ),
                key_prefix="article_library_search_export",
                caption="Export the current filtered results as CSV, JSON, or Excel.",
            )

    def _load_overview_payload(self, force_reload: bool) -> None:
        if not force_reload and self._OVERVIEW_STATE_KEY in st.session_state:
            return

        response = self.presenter.query_datastore(DatastoreQuery(limit=self._LIMIT))
        st.session_state[self._OVERVIEW_STATE_KEY] = response.payload
        st.session_state[self._OVERVIEW_MESSAGE_KEY] = response.message
        st.session_state[self._OVERVIEW_OK_KEY] = response.ok

    def _run_filtered_search(
        self,
        company_text: str,
        sector_text: str,
        min_sentiment: float,
        max_sentiment: float,
        date_range: Any,
        result_limit: int,
    ) -> None:
        company_tokens = self._parse_company_tokens(company_text)
        date_from, date_to = self._resolve_date_filters(date_range=date_range, enabled=True)

        # Treat full [-1, 1] sentiment slider as "no filter" so we don't constrain unnecessarily.
        apply_sent_filter = not (min_sentiment <= -1.0 and max_sentiment >= 1.0)

        st.session_state.pop(self._SEARCH_STATE_KEY, None)
        st.session_state.pop(self._SEARCH_MESSAGE_KEY, None)
        st.session_state.pop(self._SEARCH_OK_KEY, None)

        query = DatastoreQuery(
            company_keyword=company_tokens[0] if len(company_tokens) == 1 else None,
            company_keywords=company_tokens if len(company_tokens) > 1 else None,
            industry_sector=sector_text or None,
            date_from=date_from,
            date_to=date_to,
            min_sentiment=min_sentiment if apply_sent_filter else None,
            max_sentiment=max_sentiment if apply_sent_filter else None,
            limit=max(1, min(int(result_limit), self._LIMIT)),
        )

        response = self.presenter.query_datastore(query)
        payload = dict(response.payload)
        payload["filters_summary"] = self._build_filters_summary(
            company_tokens=company_tokens,
            sector_text=sector_text,
            apply_sent_filter=apply_sent_filter,
            min_sentiment=min_sentiment,
            max_sentiment=max_sentiment,
            date_from=date_from,
            date_to=date_to,
            result_limit=result_limit,
        )
        st.session_state[self._SEARCH_STATE_KEY] = payload
        st.session_state[self._SEARCH_MESSAGE_KEY] = response.message
        st.session_state[self._SEARCH_OK_KEY] = response.ok

    def _render_search_summary(
        self,
        records: list[dict[str, Any]],
        payload: dict[str, Any],
        insights: DatastoreInsights,
    ) -> None:
        st.divider()
        render_section_heading(
            "Search Results",
            "Summary of the articles returned by your current filters.",
        )

        oldest, newest = self._resolve_date_range(records)
        metrics = st.columns(5)
        metrics[0].metric("Matching articles", str(int(payload.get("count", len(records)))))
        metrics[1].metric("Average score", f"{float(payload.get('avg_sentiment_score', 0.0)):+.3f}")
        metrics[2].metric("Average magnitude", f"{float(payload.get('avg_sentiment_magnitude', 0.0)):.3f}")
        metrics[3].metric("Unique publishers", str(int(insights.unique_publishers)))
        metrics[4].metric("Unique trends", str(int(insights.unique_trends)))

        time_col_a, time_col_b = st.columns(2)
        with time_col_a:
            st.markdown("**Oldest match · Zurich**")
            st.caption(oldest)
        with time_col_b:
            st.markdown("**Newest match · Zurich**")
            st.caption(newest)

    def _render_facts(self, records: list[dict[str, Any]], payload: dict[str, Any], insights: DatastoreInsights) -> None:
        st.divider()
        render_section_heading("Overview")

        oldest, newest = self._resolve_date_range(records)
        metrics = st.columns(4)
        metrics[0].metric("Stored articles", str(int(payload.get("count", len(records)))))
        metrics[1].metric("Unique publishers", str(int(insights.unique_publishers)))
        metrics[2].metric("Unique trends", str(int(insights.unique_trends)))
        metrics[3].metric("Unique entities", str(int(insights.unique_entities)))

        time_col_a, time_col_b = st.columns(2)
        with time_col_a:
            st.markdown("**Oldest article · Zurich**")
            st.caption(oldest)
        with time_col_b:
            st.markdown("**Newest article · Zurich**")
            st.caption(newest)

    def _render_sentiment_section(self, insights: DatastoreInsights) -> None:
        st.divider()
        render_section_heading("Sentiment Overview")

        col_stats, col_meter = st.columns([1.4, 3])
        with col_stats:
            st.metric("Average score", f"{insights.sentiment.average_score:+.3f}")
            st.metric("Average magnitude", f"{insights.sentiment.average_magnitude:.3f}")
        with col_meter:
            render_sentiment_meter(insights.sentiment.average_score)

        render_section_heading("Sentiment Distribution")
        render_sentiment_donut(insights.sentiment.as_distribution_rows())

    def _render_trend_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        render_section_heading("Top Trends")
        if not insights.top_trends:
            st.info("No trend data is available yet.", icon="📈")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_trends]
        self._render_ranked_bar(rows=rows, label_field="Trend", value_field="Articles", color="#2471A3")

    def _render_entity_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        render_section_heading("Top Entities")
        if not insights.top_entities:
            st.info("No entities are available yet.", icon="🏷️")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_entities]
        self._render_ranked_bar(rows=rows, label_field="Entity", value_field="Count", color="#0E6655")

    def _render_publisher_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        render_section_heading("Top Publishers")
        if not insights.top_publishers:
            st.info("No publisher data is available yet.", icon="📰")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_publishers]
        self._render_ranked_bar(rows=rows, label_field="Publisher", value_field="Articles", color="#935116")

    def _render_article_table(self, insights: DatastoreInsights, title: str) -> None:
        st.divider()
        render_section_heading(
            title,
            "Headlines, publishers, trends, and sentiment scores for each article.",
        )
        st.dataframe(self._build_article_table_rows(insights), width="stretch", hide_index=True)

    def _render_ranked_bar(
        self,
        rows: list[dict[str, Any]],
        label_field: str,
        value_field: str,
        color: str,
    ) -> None:
        sorted_rows = sorted(rows, key=lambda row: int(row.get("count", 0)), reverse=True)
        ranked_rows = [
            {
                "Rank": index + 1,
                label_field: str(item.get("label", "")).strip() or "Unknown",
                value_field: int(item.get("count", 0)),
            }
            for index, item in enumerate(sorted_rows)
        ]

        chart_col, table_col = st.columns([2.8, 1.2])
        with chart_col:
            st.vega_lite_chart(
                ranked_rows,
                {
                    "mark": {"type": "bar", "cornerRadiusEnd": 3},
                    "encoding": {
                        "y": {"field": label_field, "type": "nominal", "sort": "-x", "title": label_field},
                        "x": {"field": value_field, "type": "quantitative", "title": value_field},
                        "color": {"value": color},
                        "tooltip": [
                            {"field": "Rank", "type": "quantitative", "title": "Rank"},
                            {"field": label_field, "type": "nominal", "title": label_field},
                            {"field": value_field, "type": "quantitative", "title": value_field},
                        ],
                    },
                },
                width="stretch",
            )
        with table_col:
            st.dataframe(ranked_rows, width="stretch", hide_index=True)

    def _build_filters_summary(
        self,
        company_tokens: list[str],
        sector_text: str,
        apply_sent_filter: bool,
        min_sentiment: float,
        max_sentiment: float,
        date_from: str | None,
        date_to: str | None,
        result_limit: int,
    ) -> list[dict[str, str]]:
        """Build a compact summary table for the current search filters."""
        sentiment_label = (
            f"{min_sentiment:+.2f} to {max_sentiment:+.2f}" if apply_sent_filter else "Any"
        )
        rows = [
            {
                "Companies": ", ".join(company_tokens) if company_tokens else "Any",
                "Industry Sector": sector_text or "Any",
                "Sentiment Range": sentiment_label,
                "Publication Range": self._format_range_label(date_from, date_to) or "Any",
                "Result Limit": str(int(result_limit)),
            }
        ]
        return rows

    def _build_overview_export_sections(
        self,
        records: list[dict[str, Any]],
        payload: dict[str, Any],
        insights: DatastoreInsights,
    ) -> dict[str, list[dict[str, Any]]]:
        oldest, newest = self._resolve_date_range(records)
        summary_rows = [
            {
                "stored_articles": int(payload.get("count", len(records))),
                "unique_publishers": int(insights.unique_publishers),
                "unique_trends": int(insights.unique_trends),
                "unique_entities": int(insights.unique_entities),
                "avg_sentiment_score": float(insights.sentiment.average_score),
                "avg_sentiment_magnitude": float(insights.sentiment.average_magnitude),
                "oldest_article_zurich": oldest,
                "newest_article_zurich": newest,
            }
        ]
        return {
            "overview_summary": summary_rows,
            "sentiment_distribution": insights.sentiment.as_distribution_rows(),
            "top_trends": [item.as_dict() for item in insights.top_trends],
            "top_entities": [item.as_dict() for item in insights.top_entities],
            "top_publishers": [item.as_dict() for item in insights.top_publishers],
            "stored_articles": self._build_article_table_rows(insights),
        }

    def _build_search_export_sections(
        self,
        payload: dict[str, Any],
        insights: DatastoreInsights,
    ) -> dict[str, list[dict[str, Any]]]:
        records = payload.get("records", []) if isinstance(payload, dict) else []
        oldest, newest = self._resolve_date_range(records if isinstance(records, list) else [])
        summary_rows = [
            {
                "matching_articles": int(payload.get("count", len(records) if isinstance(records, list) else 0)),
                "avg_sentiment_score": float(payload.get("avg_sentiment_score", 0.0)),
                "avg_sentiment_magnitude": float(payload.get("avg_sentiment_magnitude", 0.0)),
                "unique_publishers": int(insights.unique_publishers),
                "unique_trends": int(insights.unique_trends),
                "oldest_match_zurich": oldest,
                "newest_match_zurich": newest,
            }
        ]
        return {
            "active_filters": payload.get("filters_summary", []),
            "search_summary": summary_rows,
            "sentiment_distribution": insights.sentiment.as_distribution_rows(),
            "top_publishers": [item.as_dict() for item in insights.top_publishers],
            "top_trends": [item.as_dict() for item in insights.top_trends],
            "matching_articles": self._build_article_table_rows(insights),
        }

    def _build_article_table_rows(self, insights: DatastoreInsights) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in insights.article_facts:
            raw_dt = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            date_value, time_value = format_swiss_date_time(raw_dt)
            normalized = dict(row)
            normalized["date"] = date_value
            normalized["time"] = time_value
            normalized.pop("published_date", None)
            normalized.pop("published_at", None)
            rows.append(normalized)
        return rows

    @staticmethod
    def _parse_company_tokens(raw_value: str) -> list[str]:
        seen: set[str] = set()
        tokens: list[str] = []
        for token in str(raw_value).split(","):
            clean = token.strip()
            key = clean.casefold()
            if not clean or key in seen:
                continue
            seen.add(key)
            tokens.append(clean)
        return tokens

    def _resolve_date_range(self, records: list[dict[str, Any]]) -> tuple[str, str]:
        parsed_dates: list[datetime] = []
        for row in records:
            raw_dt = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            parsed = self._parse_datetime(raw_dt)
            if parsed is not None:
                parsed_dates.append(parsed)

        if not parsed_dates:
            return "-", "-"

        parsed_dates.sort()
        oldest_date, oldest_time = format_swiss_date_time(parsed_dates[0])
        newest_date, newest_time = format_swiss_date_time(parsed_dates[-1])
        oldest = f"{oldest_date} | {oldest_time}"
        newest = f"{newest_date} | {newest_time}"
        return oldest, newest

    @staticmethod
    def _resolve_date_filters(date_range: Any, enabled: bool) -> tuple[str | None, str | None]:
        if not enabled:
            return None, None

        if isinstance(date_range, tuple):
            values = list(date_range)
        elif isinstance(date_range, list):
            values = date_range
        else:
            values = [date_range]

        if not values:
            return None, None

        start_value = values[0]
        end_value = values[-1]
        if not isinstance(start_value, date) or not isinstance(end_value, date):
            return None, None

        start_dt = datetime.combine(start_value, datetime.min.time()).isoformat()
        end_dt = datetime.combine(end_value, datetime.max.time().replace(microsecond=0)).isoformat()
        return start_dt, end_dt

    @staticmethod
    def _format_range_label(date_from: str | None, date_to: str | None) -> str:
        if not date_from or not date_to:
            return "Any"

        from_date, _ = format_swiss_date_time(date_from)
        to_date, _ = format_swiss_date_time(date_to)
        return f"{from_date} to {to_date}"

    def _render_long_term_analysis_mode(self) -> None:
        """Render Long-Term Ticker analysis with dropdown selector and trend data."""
        # Get available tickers from the long-term config
        available_tickers = [str(t).strip() for t in DEFAULT_LONG_TERM_TICKERS if str(t).strip()]
        if not available_tickers:
            st.warning("No long-term tickers are configured.")
            return

        left_pad, center, right_pad = st.columns([1, 3, 1])
        del left_pad, right_pad

        with center:
            render_search_panel_header(
                title="Drill into a tracked ticker",
                subtitle="Pick a ticker and click 'Run search' to load its saved coverage.",
            )

            with st.container(border=True):
                with st.form("article_library_long_term_form"):
                    if st.session_state.get("long_term_selected_ticker") not in available_tickers:
                        st.session_state["long_term_selected_ticker"] = available_tickers[0]

                    selected_ticker = st.selectbox(
                        "Tracked ticker",
                        options=available_tickers,
                        index=available_tickers.index(
                            st.session_state.get("long_term_selected_ticker", available_tickers[0])
                        ),
                        key="long_term_selected_ticker",
                        help="Type to filter the list. Click 'Run search' to load the selected ticker.",
                    )
                    st.caption(f"{len(available_tickers)} ticker(s) tracked by the long-term collector.")

                    run_search_clicked = st.form_submit_button(
                        "Run search", type="primary", width="stretch"
                    )

        payload_key = "long_term_analysis_payload"
        state_ticker_key = "long_term_analysis_ticker"
        message_key = "long_term_analysis_message"
        ok_key = "long_term_analysis_ok"

        ticker_changed = (
            payload_key not in st.session_state
            or st.session_state.get(state_ticker_key) != selected_ticker
        )
        should_reload = ticker_changed or run_search_clicked

        # Single slot for everything below the selector — guarantees stale data
        # is removed the moment a new ticker is loaded.
        content_zone = st.empty()

        if should_reload:
            with content_zone.container():
                st.markdown(
                    render_loading_card_html(
                        title=f"Loading articles for {selected_ticker}…",
                        subtitle="Filtering the datastore for matches and computing sentiment.",
                    ),
                    unsafe_allow_html=True,
                )
            self._load_long_term_payload(ticker=selected_ticker, force_reload=run_search_clicked)

        payload = st.session_state.get(payload_key, {})
        message = str(st.session_state.get(message_key, ""))
        ok = bool(st.session_state.get(ok_key, True))

        with content_zone.container():
            self._render_message(message=message, ok=ok)

            if not isinstance(payload, dict) or not payload:
                render_empty_state(
                    title=f"No saved articles for {selected_ticker}",
                    message="The collector hasn't yet stored articles for this ticker.",
                    icon="📭",
                    hint="Open the Long-Term Trends page and click 'Collect now' to trigger a fresh cycle.",
                )
                return

            records = payload.get("records", [])
            if not records:
                render_empty_state(
                    title=f"No matches for {selected_ticker}",
                    message="No saved articles contain this ticker yet.",
                    icon="🪹",
                )
                return

            insights = build_datastore_insights(records)

            st.divider()
            self._render_long_term_facts(records=records, ticker=selected_ticker, insights=insights)
            self._render_sentiment_section(insights=insights)
            self._render_trend_chart(insights=insights)
            self._render_entity_chart(insights=insights)
            self._render_publisher_chart(insights=insights)
            self._render_article_table(insights=insights, title=f"Articles matching '{selected_ticker}'")

            st.divider()
            render_section_heading("Export")
            render_export_downloads(
                sections=self._build_long_term_export_sections(ticker=selected_ticker, records=records, insights=insights),
                file_stem=build_export_file_stem(prefix="article_library_long_term", parts=[selected_ticker]),
                key_prefix="article_library_long_term_export",
                caption=f"Export the '{selected_ticker}' analysis as CSV, JSON, or Excel.",
            )

    def _load_long_term_payload(self, ticker: str, force_reload: bool) -> None:
        """Load articles matching the selected long-term ticker."""
        payload_key = "long_term_analysis_payload"
        state_ticker_key = "long_term_analysis_ticker"

        if (
            not force_reload
            and payload_key in st.session_state
            and st.session_state.get(state_ticker_key) == ticker
        ):
            return

        # Query datastore for articles matching the ticker
        query = DatastoreQuery(
            company_keyword=ticker,
            limit=self._LIMIT,
        )

        response = self.presenter.query_datastore(query)
        payload = response.payload if isinstance(response.payload, dict) else {}

        st.session_state[payload_key] = payload
        st.session_state[state_ticker_key] = ticker
        st.session_state["long_term_analysis_message"] = response.message
        st.session_state["long_term_analysis_ok"] = response.ok

    def _render_long_term_facts(
        self,
        records: list[dict[str, Any]],
        ticker: str,
        insights: DatastoreInsights,
    ) -> None:
        """Render overview metrics for the selected long-term ticker."""
        render_section_heading("Overview")

        oldest, newest = self._resolve_date_range(records)
        metrics = st.columns(5)
        metrics[0].metric("Matching articles", str(len(records)))
        metrics[1].metric("Unique publishers", str(int(insights.unique_publishers)))
        metrics[2].metric("Unique trends", str(int(insights.unique_trends)))
        metrics[3].metric("Unique entities", str(int(insights.unique_entities)))
        metrics[4].metric("Avg sentiment", f"{insights.sentiment.average_score:+.3f}")

        time_col_a, time_col_b = st.columns(2)
        with time_col_a:
            st.markdown("**Oldest article · Zurich**")
            st.caption(oldest)
        with time_col_b:
            st.markdown("**Newest article · Zurich**")
            st.caption(newest)

    def _build_long_term_export_sections(
        self,
        ticker: str,
        records: list[dict[str, Any]],
        insights: DatastoreInsights,
    ) -> dict[str, list[dict[str, Any]]]:
        """Build export sections for long-term ticker analysis."""
        oldest, newest = self._resolve_date_range(records)
        summary_rows = [
            {
                "ticker": ticker,
                "matching_articles": len(records),
                "unique_publishers": int(insights.unique_publishers),
                "unique_trends": int(insights.unique_trends),
                "unique_entities": int(insights.unique_entities),
                "avg_sentiment_score": float(insights.sentiment.average_score),
                "avg_sentiment_magnitude": float(insights.sentiment.average_magnitude),
                "oldest_article_zurich": oldest,
                "newest_article_zurich": newest,
            }
        ]
        return {
            "ticker_summary": summary_rows,
            "sentiment_distribution": insights.sentiment.as_distribution_rows(),
            "top_trends": [item.as_dict() for item in insights.top_trends],
            "top_entities": [item.as_dict() for item in insights.top_entities],
            "top_publishers": [item.as_dict() for item in insights.top_publishers],
            "matching_articles": self._build_article_table_rows(insights),
        }

    @staticmethod
    def _render_message(message: str, ok: bool) -> None:
        if not message:
            return
        if ok:
            st.success(message)
        else:
            st.error(message)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = date_parser.parse(value)
        except Exception:  # noqa: BLE001
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
