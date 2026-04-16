"""Article library page with overview analytics and filtered search."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.model import DatastoreInsights, DatastoreQuery, build_datastore_insights
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.search.sentiment_score import render_sentiment_meter
from news_analyzer.view.utils import build_export_file_stem, format_swiss_date_time, render_export_downloads


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

    _MODE_KEY = "article_library_mode"

    _OVERVIEW_STATE_KEY = "article_library_overview_payload"
    _OVERVIEW_MESSAGE_KEY = "article_library_overview_message"
    _OVERVIEW_OK_KEY = "article_library_overview_ok"

    _SEARCH_STATE_KEY = "article_library_search_payload"
    _SEARCH_MESSAGE_KEY = "article_library_search_message"
    _SEARCH_OK_KEY = "article_library_search_ok"

    _LIMIT = 10000

    def __init__(self, presenter: NewsPresenter) -> None:
        self.presenter = presenter

    def render(self) -> None:
        st.title("Article Library")
        st.caption("Browse the saved article collection or search it with detailed filters.")
        st.caption("All timestamps are shown in Europe/Zurich.")

        if st.session_state.get(self._MODE_KEY) not in {"Overview", "Search"}:
            st.session_state[self._MODE_KEY] = "Overview"

        mode = st.radio(
            "View Mode",
            options=["Overview", "Search"],
            horizontal=True,
            key=self._MODE_KEY,
        )

        if mode == "Overview":
            self._render_overview_mode()
            return

        self._render_search_mode()

    def _render_overview_mode(self) -> None:
        refresh_col, info_col = st.columns([1, 3])
        with refresh_col:
            refresh_clicked = st.button("Refresh library", width="stretch")
        with info_col:
            st.caption(
                f"The library loads automatically (up to {self._LIMIT} articles). "
                "Use refresh to fetch the newest saved records."
            )

        if refresh_clicked:
            self._load_overview_payload(force_reload=True)
        else:
            self._load_overview_payload(force_reload=False)

        payload = st.session_state.get(self._OVERVIEW_STATE_KEY, {})
        self._render_message(
            message=str(st.session_state.get(self._OVERVIEW_MESSAGE_KEY, "")),
            ok=bool(st.session_state.get(self._OVERVIEW_OK_KEY, True)),
        )

        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records:
            st.info("No saved articles are available yet.")
            return

        insights = build_datastore_insights(records)
        self._render_facts(records=records, payload=payload, insights=insights)
        self._render_sentiment_section(insights=insights)
        self._render_trend_chart(insights=insights)
        self._render_entity_chart(insights=insights)
        self._render_publisher_chart(insights=insights)
        self._render_article_table(insights=insights, title="Stored Articles")
        st.divider()
        st.markdown("#### Export")
        render_export_downloads(
            sections=self._build_overview_export_sections(records=records, payload=payload, insights=insights),
            file_stem=build_export_file_stem(prefix="article_library_overview"),
            key_prefix="article_library_overview_export",
            caption="Export the full library overview as CSV, JSON, or Excel.",
        )

    def _render_search_mode(self) -> None:
        st.markdown("#### Saved Article Search")
        st.caption(
            "Retrieve articles that mention one or more companies, match an industry sector, "
            "meet a sentiment threshold, and fall within a publication date range."
        )

        default_start = date.today() - timedelta(days=30)
        default_end = date.today()

        with st.form("article_library_search_form"):
            company_text = st.text_input(
                "Company names",
                placeholder="e.g. NVIDIA, Apple, Tesla",
                help="Separate multiple companies with commas.",
                key="article_library_search_companies",
            ).strip()

            filter_col_a, filter_col_b, filter_col_c = st.columns(3)
            with filter_col_a:
                sector_text = st.selectbox(
                    "Industry sector",
                    options=self._INDUSTRY_SECTOR_OPTIONS,
                    key="article_library_search_sector",
                    help="Choose a standard sector label for a more reliable match.",
                )
                use_min_sentiment = st.checkbox(
                    "Use minimum sentiment threshold",
                    value=False,
                    key="article_library_use_min_sentiment",
                )
                min_sentiment = st.slider(
                    "Minimum sentiment",
                    min_value=-1.0,
                    max_value=1.0,
                    value=0.1,
                    step=0.05,
                    disabled=not use_min_sentiment,
                    key="article_library_min_sentiment",
                )
            with filter_col_b:
                use_date_range = st.checkbox(
                    "Use publication date range",
                    value=False,
                    key="article_library_use_date_range",
                )
                date_range = st.date_input(
                    "Publication range",
                    value=(default_start, default_end),
                    disabled=not use_date_range,
                    key="article_library_date_range",
                )
            with filter_col_c:
                result_limit = st.selectbox(
                    "Result limit",
                    options=[50, 100, 250, 500, 1000, 2500, 5000, 10000],
                    index=4,
                    key="article_library_result_limit",
                    help="Higher limits can take longer to load.",
                )

            search_clicked = st.form_submit_button("Run search", type="primary")

        clear_clicked = st.button("Clear search results", width="stretch")

        if clear_clicked:
            st.session_state.pop(self._SEARCH_STATE_KEY, None)
            st.session_state.pop(self._SEARCH_MESSAGE_KEY, None)
            st.session_state.pop(self._SEARCH_OK_KEY, None)
            st.rerun()

        if search_clicked:
            self._run_filtered_search(
                company_text=company_text,
                sector_text="" if sector_text == "Any" else sector_text,
                use_min_sentiment=use_min_sentiment,
                min_sentiment=min_sentiment,
                use_date_range=use_date_range,
                date_range=date_range,
                result_limit=int(result_limit),
            )

        payload = st.session_state.get(self._SEARCH_STATE_KEY, {})
        self._render_message(
            message=str(st.session_state.get(self._SEARCH_MESSAGE_KEY, "")),
            ok=bool(st.session_state.get(self._SEARCH_OK_KEY, True)),
        )

        if not isinstance(payload, dict) or not payload:
            st.info("Run a search to see matching saved articles.")
            return

        records = payload.get("records", [])
        filters_summary = payload.get("filters_summary", [])
        if filters_summary:
            st.markdown("#### Active Filters")
            st.dataframe(filters_summary, width="stretch", hide_index=True)

        if not records:
            st.info("No saved articles matched the selected filters.")
            return

        insights = build_datastore_insights(records)
        self._render_search_summary(records=records, payload=payload, insights=insights)
        self._render_sentiment_section(insights=insights)
        self._render_publisher_chart(insights=insights)
        self._render_trend_chart(insights=insights)
        self._render_article_table(insights=insights, title="Matching Articles")
        st.divider()
        st.markdown("#### Export")
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
        use_min_sentiment: bool,
        min_sentiment: float,
        use_date_range: bool,
        date_range: Any,
        result_limit: int,
    ) -> None:
        company_tokens = self._parse_company_tokens(company_text)
        date_from, date_to = self._resolve_date_filters(date_range=date_range, enabled=use_date_range)

        st.session_state.pop(self._SEARCH_STATE_KEY, None)
        st.session_state.pop(self._SEARCH_MESSAGE_KEY, None)
        st.session_state.pop(self._SEARCH_OK_KEY, None)

        query = DatastoreQuery(
            company_keyword=company_tokens[0] if len(company_tokens) == 1 else None,
            company_keywords=company_tokens if len(company_tokens) > 1 else None,
            industry_sector=sector_text or None,
            date_from=date_from,
            date_to=date_to,
            min_sentiment=min_sentiment if use_min_sentiment else None,
            limit=max(1, min(int(result_limit), self._LIMIT)),
        )

        response = self.presenter.query_datastore(query)
        payload = dict(response.payload)
        payload["filters_summary"] = self._build_filters_summary(
            company_tokens=company_tokens,
            sector_text=sector_text,
            use_min_sentiment=use_min_sentiment,
            min_sentiment=min_sentiment,
            use_date_range=use_date_range,
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
        st.markdown("#### Search Results")
        st.caption("These metrics summarize the articles returned by your current filters.")

        oldest, newest = self._resolve_date_range(records)
        metrics = st.columns(5)
        metrics[0].metric("Matching Articles", str(int(payload.get("count", len(records)))))
        metrics[1].metric("Average Score", f"{float(payload.get('avg_sentiment_score', 0.0)):+.3f}")
        metrics[2].metric("Average Magnitude", f"{float(payload.get('avg_sentiment_magnitude', 0.0)):.3f}")
        metrics[3].metric("Unique Publishers", str(int(insights.unique_publishers)))
        metrics[4].metric("Unique Trends", str(int(insights.unique_trends)))

        time_col_a, time_col_b = st.columns(2)
        with time_col_a:
            st.markdown("**Oldest Match (Zurich)**")
            st.caption(oldest)
        with time_col_b:
            st.markdown("**Newest Match (Zurich)**")
            st.caption(newest)

    def _render_facts(self, records: list[dict[str, Any]], payload: dict[str, Any], insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Overview")

        oldest, newest = self._resolve_date_range(records)
        metrics = st.columns(4)
        metrics[0].metric("Stored Articles", str(int(payload.get("count", len(records)))))
        metrics[1].metric("Unique Publishers", str(int(insights.unique_publishers)))
        metrics[2].metric("Unique Trends", str(int(insights.unique_trends)))
        metrics[3].metric("Unique Entities", str(int(insights.unique_entities)))

        time_col_a, time_col_b = st.columns(2)
        with time_col_a:
            st.markdown("**Oldest Article (Zurich)**")
            st.caption(oldest)
        with time_col_b:
            st.markdown("**Newest Article (Zurich)**")
            st.caption(newest)

    def _render_sentiment_section(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Sentiment Overview")

        col_stats, col_meter = st.columns([1.4, 3])
        with col_stats:
            st.metric("Average Score", f"{insights.sentiment.average_score:+.3f}")
            st.metric("Average Magnitude", f"{insights.sentiment.average_magnitude:.3f}")
        with col_meter:
            render_sentiment_meter(insights.sentiment.average_score)

        st.markdown("#### Positive / Neutral / Negative Share")
        pie_values = insights.sentiment.as_distribution_rows()
        st.vega_lite_chart(
            pie_values,
            {
                "mark": {"type": "arc", "innerRadius": 20},
                "encoding": {
                    "theta": {"field": "count", "type": "quantitative"},
                    "color": {
                        "field": "label",
                        "type": "nominal",
                        "scale": {
                            "domain": ["Positive", "Neutral", "Negative"],
                            "range": ["#1e8449", "#f4d03f", "#c0392b"],
                        },
                        "legend": {"title": "Label"},
                    },
                    "tooltip": [
                        {"field": "label", "type": "nominal", "title": "Label"},
                        {"field": "count", "type": "quantitative", "title": "Articles"},
                    ],
                },
            },
            width="stretch",
        )

    def _render_trend_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Top Trends")
        if not insights.top_trends:
            st.info("No trend data is available yet.")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_trends]
        self._render_ranked_bar(rows=rows, label_field="Trend", value_field="Articles", color="#2471A3")

    def _render_entity_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Top Entities")
        if not insights.top_entities:
            st.info("No entities are available yet.")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_entities]
        self._render_ranked_bar(rows=rows, label_field="Entity", value_field="Count", color="#0E6655")

    def _render_publisher_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Top Publishers")
        if not insights.top_publishers:
            st.info("No publisher data is available yet.")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_publishers]
        self._render_ranked_bar(rows=rows, label_field="Publisher", value_field="Articles", color="#935116")

    def _render_article_table(self, insights: DatastoreInsights, title: str) -> None:
        st.divider()
        st.markdown(f"#### {title}")
        st.caption("Use the table to review article headlines, publishers, trends, and sentiment scores.")
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
        use_min_sentiment: bool,
        min_sentiment: float,
        use_date_range: bool,
        date_from: str | None,
        date_to: str | None,
        result_limit: int,
    ) -> list[dict[str, str]]:
        """Build a compact summary table for the current search filters."""
        rows = [
            {
                "Companies": ", ".join(company_tokens) if company_tokens else "Any",
                "Industry Sector": sector_text or "Any",
                "Minimum Sentiment": f"{min_sentiment:+.2f}" if use_min_sentiment else "Any",
                "Publication Range": self._format_range_label(date_from, date_to) if use_date_range else "Any",
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
