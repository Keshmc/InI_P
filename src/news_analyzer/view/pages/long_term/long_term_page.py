"""Long-term trend monitoring dashboard for scheduler-driven ticker coverage."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.model import DatastoreQuery
from news_analyzer.model.trends import LongTermTrendConfig, LongTermTrendScheduler
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.general.topbar import (
    build_collector_status_pill,
    render_empty_state,
    render_loading_card_html,
    render_page_header,
    render_section_heading,
)
from news_analyzer.view.utils import (
    build_export_file_stem,
    format_swiss_date_time,
    format_swiss_timestamp,
    render_export_downloads,
)


class LongTermPage:
    """Render a dashboard for active long-term tickers and their stored coverage."""

    _STATE_KEY = "long_term_dashboard_payload"
    _MESSAGE_KEY = "long_term_dashboard_message"
    _OK_KEY = "long_term_dashboard_ok"
    _CONFIG_KEY = "long_term_dashboard_config_signature"
    _DATASTORE_LIMIT = 10000

    def __init__(
        self,
        presenter: NewsPresenter,
        trend_config: LongTermTrendConfig,
        trend_status: dict[str, Any],
        scheduler: LongTermTrendScheduler | None = None,
    ) -> None:
        self.presenter = presenter
        self.trend_config = trend_config
        self.trend_status = trend_status
        self.scheduler = scheduler

    def render(self) -> None:
        """Render scheduler status, active tickers, and datastore history charts."""
        render_page_header(
            eyebrow="Continuous monitoring",
            title="Long-Term Trends",
            subtitle=(
                "Track which tickers the background collector watches and how their saved "
                "article history grows over time."
            ),
            meta="Timestamps in Europe/Zurich",
        )

        ticker_count = len([item for item in self.trend_config.tickers if str(item).strip()])
        with st.container(border=True):
            action_col, info_col = st.columns([1, 3])
            with action_col:
                collect_clicked = st.button(
                    "Collect now",
                    type="primary",
                    width="stretch",
                    disabled=self.scheduler is None,
                    help=(
                        "Run one collection cycle immediately, instead of waiting for the "
                        f"next scheduled run (every {self.trend_config.interval_minutes} min)."
                    ),
                )
            with info_col:
                st.markdown(
                    f"**Tracks {ticker_count} ticker(s)** · "
                    f"runs every {self.trend_config.interval_minutes} min · "
                    f"scans up to {self._DATASTORE_LIMIT:,} saved records.",
                )
                st.caption(
                    "Charts prefer ingestion timestamps, falling back to analysis or publish times."
                )

        if collect_clicked and self.scheduler is not None:
            loading_zone = st.empty()
            loading_zone.markdown(
                render_loading_card_html(
                    title=f"Collecting articles for {ticker_count} ticker(s)…",
                    subtitle="Fetching feeds, deduplicating, scoring sentiment, and saving new records.",
                ),
                unsafe_allow_html=True,
            )
            try:
                self.scheduler.run_once()
            finally:
                loading_zone.empty()
            # Force a reload of the page-level payload so charts pick up the new records.
            st.session_state.pop(self._STATE_KEY, None)
            st.session_state.pop(self._CONFIG_KEY, None)
            # Drop the navbar's Firestore freshness cache so the pill updates immediately.
            st.session_state.pop("_long_term_latest_ingested_cache", None)
            self.trend_status = self.scheduler.status()
            st.rerun()

        if self._STATE_KEY not in st.session_state:
            loading_zone = st.empty()
            loading_zone.markdown(
                render_loading_card_html(
                    title="Loading long-term coverage…",
                    subtitle="Scanning saved articles for configured tickers and aggregating timelines.",
                ),
                unsafe_allow_html=True,
            )
            try:
                self._load_payload(force_reload=False)
            finally:
                loading_zone.empty()
        else:
            self._load_payload(force_reload=False)
        self._render_message(
            str(st.session_state.get(self._MESSAGE_KEY, "")),
            bool(st.session_state.get(self._OK_KEY, True)),
        )

        payload = st.session_state.get(self._STATE_KEY, {})
        if not isinstance(payload, dict):
            self._render_empty_state()
            return

        if int(payload.get("matched_articles", 0)) == 0:
            self._render_empty_state()
            self._render_scheduler_status()
            return

        self._render_scheduler_status()
        self._render_coverage_summary(payload)
        self._render_active_tickers(payload)
        self._render_history_charts(payload)
        self._render_recent_articles(payload)
        self._render_export(payload)

    def _render_empty_state(self) -> None:
        interval = int(self.trend_config.interval_minutes)
        render_empty_state(
            title="No long-term articles yet",
            message=(
                f"The background collector runs every {interval} min. "
                "Click 'Collect now' above to run one cycle immediately."
            ),
            icon="🌱",
            hint="Tip: a degraded status above means the last cycle failed — check the scheduler tooltip.",
        )

    def _load_payload(self, force_reload: bool) -> None:
        config_signature = "|".join(self.trend_config.tickers)
        if (
            not force_reload
            and self._STATE_KEY in st.session_state
            and st.session_state.get(self._CONFIG_KEY) == config_signature
        ):
            return

        response = self.presenter.query_datastore(DatastoreQuery(limit=self._DATASTORE_LIMIT))
        records = response.payload.get("records", []) if isinstance(response.payload, dict) else []
        payload = self._build_payload(records)

        st.session_state[self._STATE_KEY] = payload
        if response.ok:
            st.session_state[self._MESSAGE_KEY] = (
                f"Loaded {int(payload.get('matched_articles', 0))} long-term article(s) "
                f"across {int(payload.get('configured_tickers', 0))} configured ticker(s)."
            )
        else:
            st.session_state[self._MESSAGE_KEY] = response.message
        st.session_state[self._OK_KEY] = response.ok
        st.session_state[self._CONFIG_KEY] = config_signature

    def _build_payload(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        ticker_display = [str(item).strip() for item in self.trend_config.tickers if str(item).strip()]
        ticker_map = {ticker.casefold(): ticker for ticker in ticker_display}
        matched_records = [
            row for row in records if self._resolve_record_ticker(row, ticker_map) is not None
        ]

        # Derive the collector's "last run" from the most recent `ingested_at`
        # across *all* records (not just matched), because the production daily
        # job persists records from a separate process and the in-memory
        # `trend_status.last_run_at` is always empty in that setup.
        latest_ingested_at = self._compute_latest_ingested_at(records)

        ticker_rows = self._build_ticker_rows(ticker_display=ticker_display, records=matched_records, ticker_map=ticker_map)
        timeline_rows = self._build_timeline_rows(records=matched_records, ticker_map=ticker_map)
        cumulative_rows = self._build_cumulative_total_rows(timeline_rows)
        summary_rows = self._build_summary_rows(
            ticker_display=ticker_display,
            records=matched_records,
            ticker_rows=ticker_rows,
            latest_ingested_at=latest_ingested_at,
        )
        recent_articles = self._build_recent_article_rows(records=matched_records, ticker_map=ticker_map)

        return {
            "summary_rows": summary_rows,
            "ticker_rows": ticker_rows,
            "timeline_rows": timeline_rows,
            "cumulative_rows": cumulative_rows,
            "recent_articles": recent_articles,
            "matched_articles": len(matched_records),
            "configured_tickers": len(ticker_display),
            "latest_ingested_at": latest_ingested_at,
        }

    def _render_scheduler_status(self) -> None:
        render_section_heading(
            "Scheduler",
            "Status of the background collector that keeps long-term tickers up to date.",
        )

        effective_last_run_raw = self._effective_last_run_raw()
        last_run = format_swiss_timestamp(effective_last_run_raw)
        interval_minutes = int(self.trend_status.get("interval_minutes", self.trend_config.interval_minutes))
        configured_tickers = len([item for item in self.trend_config.tickers if str(item).strip()])
        last_result = self.trend_status.get("last_result", {})
        totals = last_result.get("totals", {}) if isinstance(last_result, dict) else {}

        # Pass an enriched status to the pill so it reflects external Cloud Run Job
        # executions (which never touch the webapp's in-memory scheduler state).
        enriched_status = dict(self.trend_status)
        enriched_status["last_run_at"] = effective_last_run_raw

        with st.container(border=True):
            st.markdown(
                (
                    '<div class="na-inline-status">'
                    f"{build_collector_status_pill(enriched_status)}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

            metric_cols = st.columns(3)
            metric_cols[0].metric("Interval", f"{interval_minutes} min")
            metric_cols[1].metric("Configured tickers", str(configured_tickers))
            metric_cols[2].metric("Last run · Zurich", last_run if last_run != "-" else "Not yet")

            detail_cols = st.columns(3)
            detail_cols[0].metric("Runs on startup", "Yes" if self.trend_config.run_on_startup else "No")
            detail_cols[1].metric("Lookback period", str(self.trend_config.period).strip() or "-")
            detail_cols[2].metric("Max results per ticker", str(int(self.trend_config.max_results)))

            if totals:
                st.caption("Latest scheduler cycle")
                result_cols = st.columns(5)
                result_cols[0].metric("Fetched", str(int(totals.get("fetched", 0))))
                result_cols[1].metric("Existing", str(int(totals.get("existing", 0))))
                result_cols[2].metric("New", str(int(totals.get("new", 0))))
                result_cols[3].metric("Saved", str(int(totals.get("saved", 0))))
                result_cols[4].metric("Loaded", str(int(totals.get("loaded", 0))))

    def _render_active_tickers(self, payload: dict[str, Any]) -> None:
        st.divider()
        render_section_heading(
            "Active Tickers",
            "Tickers currently configured for the automatic long-term collector.",
        )
        st.dataframe(payload.get("ticker_rows", []), width="stretch", hide_index=True)

    def _render_coverage_summary(self, payload: dict[str, Any]) -> None:
        st.divider()
        render_section_heading("Coverage Overview")

        summary_row = {}
        summary_rows = payload.get("summary_rows", [])
        if isinstance(summary_rows, list) and summary_rows:
            summary_row = summary_rows[0]

        metric_cols = st.columns(4)
        metric_cols[0].metric("Configured tickers", str(int(summary_row.get("configured_tickers", 0))))
        metric_cols[1].metric("Tickers with data", str(int(summary_row.get("tickers_with_saved_articles", 0))))
        metric_cols[2].metric("Saved long-term articles", str(int(summary_row.get("saved_articles", 0))))
        metric_cols[3].metric("Last run · Zurich", str(summary_row.get("last_run_at_zurich", "-")))

    def _render_history_charts(self, payload: dict[str, Any]) -> None:
        st.divider()
        render_section_heading(
            "Article Growth Over Time",
            "Cumulative total of all saved long-term articles, day by day.",
        )

        cumulative_rows = payload.get("cumulative_rows", [])
        timeline_rows = payload.get("timeline_rows", [])
        if not cumulative_rows or not timeline_rows:
            st.info(
                "No timeline data yet — once the collector saves articles, the growth chart appears here.",
                icon="🌱",
            )
            return

        date_order = self._build_date_order(cumulative_rows)

        st.vega_lite_chart(
            cumulative_rows,
            {
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": self._build_compact_date_axis(date_order),
                    "y": {"field": "total_articles", "type": "quantitative", "title": "Total saved articles"},
                    "tooltip": [
                        {"field": "date_label", "type": "nominal", "title": "Date"},
                        {"field": "daily_articles", "type": "quantitative", "title": "New articles that day"},
                        {"field": "total_articles", "type": "quantitative", "title": "Total saved articles"},
                    ],
                },
            },
            width="stretch",
        )

        render_section_heading(
            "Ticker Breakdown Over Time",
            "Daily saved article counts grouped by configured long-term ticker.",
        )
        st.vega_lite_chart(
            timeline_rows,
            {
                "mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
                "encoding": {
                    "x": self._build_compact_date_axis(date_order),
                    "y": {"field": "articles", "type": "quantitative", "title": "Saved articles"},
                    "color": {"field": "ticker", "type": "nominal", "title": "Ticker"},
                    "tooltip": [
                        {"field": "date_label", "type": "nominal", "title": "Date"},
                        {"field": "ticker", "type": "nominal", "title": "Ticker"},
                        {"field": "articles", "type": "quantitative", "title": "Articles"},
                    ],
                },
            },
            width="stretch",
        )

    def _render_recent_articles(self, payload: dict[str, Any]) -> None:
        st.divider()
        render_section_heading(
            "Recent Long-Term Articles",
            "Latest saved records matching the configured long-term tickers.",
        )
        st.dataframe(payload.get("recent_articles", []), width="stretch", hide_index=True)

    def _render_export(self, payload: dict[str, Any]) -> None:
        st.divider()
        render_section_heading("Export")
        render_export_downloads(
            sections={
                "summary": payload.get("summary_rows", []),
                "active_tickers": payload.get("ticker_rows", []),
                "article_growth_total": payload.get("cumulative_rows", []),
                "articles_over_time_by_ticker": payload.get("timeline_rows", []),
                "recent_articles": payload.get("recent_articles", []),
            },
            file_stem=build_export_file_stem(prefix="long_term_trends"),
            key_prefix="long_term_trends_export",
            caption="Export the current long-term monitoring view as CSV, JSON, or Excel.",
        )

    def _build_ticker_rows(
        self,
        ticker_display: list[str],
        records: list[dict[str, Any]],
        ticker_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in ticker_display}
        for row in records:
            resolved = self._resolve_record_ticker(row, ticker_map)
            if resolved:
                grouped.setdefault(resolved, []).append(row)

        ticker_rows: list[dict[str, Any]] = []
        for ticker in ticker_display:
            ticker_records = grouped.get(ticker, [])
            latest_ingested = self._resolve_latest_value(ticker_records, "ingested_at")
            latest_published = self._resolve_latest_published(ticker_records)
            average_sentiment = 0.0
            if ticker_records:
                average_sentiment = round(
                    sum(float(item.get("sentiment_score", 0.0)) for item in ticker_records) / len(ticker_records),
                    4,
                )

            ticker_rows.append(
                {
                    "ticker": ticker,
                    "saved_articles": len(ticker_records),
                    "average_sentiment": average_sentiment,
                    "latest_ingested_zurich": latest_ingested,
                    "latest_published_zurich": latest_published,
                }
            )
        return ticker_rows

    def _build_summary_rows(
        self,
        ticker_display: list[str],
        records: list[dict[str, Any]],
        ticker_rows: list[dict[str, Any]],
        latest_ingested_at: str = "",
    ) -> list[dict[str, Any]]:
        tickers_with_data = sum(1 for row in ticker_rows if int(row.get("saved_articles", 0)) > 0)
        last_run_raw = (
            str(self.trend_status.get("last_run_at", "") or "").strip()
            or str(latest_ingested_at or "").strip()
        )
        return [
            {
                "configured_tickers": len(ticker_display),
                "tickers_with_saved_articles": tickers_with_data,
                "saved_articles": len(records),
                "scheduler_running": bool(self.trend_status.get("running", False)),
                "interval_minutes": int(self.trend_status.get("interval_minutes", self.trend_config.interval_minutes)),
                "last_run_at_zurich": format_swiss_timestamp(last_run_raw),
            }
        ]

    def _build_timeline_rows(
        self,
        records: list[dict[str, Any]],
        ticker_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        daily_counts: dict[tuple[str, str], int] = defaultdict(int)
        for row in records:
            ticker = self._resolve_record_ticker(row, ticker_map)
            timestamp = self._resolve_record_timestamp(row)
            if not ticker or timestamp is None:
                continue
            date_value, _ = format_swiss_date_time(timestamp)
            daily_counts[(date_value, ticker)] += 1

        timeline_rows = [
            {
                "date": self._format_chart_date(date_label),
                "date_label": date_label,
                "ticker": ticker,
                "articles": count,
            }
            for (date_label, ticker), count in sorted(
                daily_counts.items(),
                key=lambda item: (self._sort_date_label(item[0][0]), item[0][1]),
            )
        ]
        return timeline_rows

    @staticmethod
    def _build_daily_total_rows(timeline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        totals: dict[str, int] = defaultdict(int)
        for row in timeline_rows:
            date_label = str(row.get("date_label", "")).strip()
            totals[date_label] += int(row.get("articles", 0))

        return [
            {
                "date": LongTermPage._format_chart_date(date_label),
                "date_label": date_label,
                "articles": count,
            }
            for date_label, count in sorted(totals.items(), key=lambda item: LongTermPage._sort_date_label(item[0]))
        ]

    @staticmethod
    def _build_cumulative_total_rows(timeline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cumulative_total = 0
        rows: list[dict[str, Any]] = []
        for row in LongTermPage._build_daily_total_rows(timeline_rows):
            daily_articles = int(row.get("articles", 0))
            cumulative_total += daily_articles
            rows.append(
                {
                    "date": row.get("date", ""),
                    "date_label": row.get("date_label", ""),
                    "daily_articles": daily_articles,
                    "total_articles": cumulative_total,
                }
            )
        return rows

    @staticmethod
    def _build_date_order(rows: list[dict[str, Any]]) -> list[str]:
        ordered_labels: list[str] = []
        seen: set[str] = set()
        for row in rows:
            date_label = str(row.get("date_label", "")).strip()
            if not date_label or date_label in seen:
                continue
            seen.add(date_label)
            ordered_labels.append(date_label)
        return ordered_labels

    @staticmethod
    def _build_compact_date_axis(date_order: list[str]) -> dict[str, Any]:
        return {
            "field": "date_label",
            "type": "ordinal",
            "title": "Date (Zurich)",
            "sort": date_order,
            "axis": {
                "labelAngle": -35,
                "labelLimit": 90,
                "labelOverlap": "greedy",
            },
        }

    def _build_recent_article_rows(
        self,
        records: list[dict[str, Any]],
        ticker_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        sorted_records = sorted(
            records,
            key=lambda row: self._sort_timestamp(row),
            reverse=True,
        )[:100]

        rows: list[dict[str, Any]] = []
        for row in sorted_records:
            published_raw = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            published_date, published_time = format_swiss_date_time(published_raw)
            rows.append(
                {
                    "ticker": self._resolve_record_ticker(row, ticker_map) or "-",
                    "title": str(row.get("title", "")).strip(),
                    "source": str(row.get("source", "")).strip(),
                    "published_date": published_date,
                    "published_time": published_time,
                    "sentiment_score": round(float(row.get("sentiment_score", 0.0)), 4),
                    "status": str(row.get("status", "")).strip(),
                }
            )
        return rows

    @staticmethod
    def _resolve_record_ticker(row: dict[str, Any], ticker_map: dict[str, str]) -> str | None:
        query = str(row.get("query", "")).strip()
        topic = str(row.get("topic", "")).strip()
        company_keyword = str(row.get("company_keyword", "")).strip()
        symbol = str(row.get("symbol", "")).strip()
        for candidate in (query, topic, company_keyword, symbol):
            if candidate and candidate.casefold() in ticker_map:
                return ticker_map[candidate.casefold()]

        raw_article = row.get("raw_article_json", "{}")
        try:
            raw_payload = json.loads(str(raw_article))
        except (TypeError, json.JSONDecodeError):
            raw_payload = {}
        if isinstance(raw_payload, dict):
            for candidate in (
                str(raw_payload.get("query", "")).strip(),
                str(raw_payload.get("topic", "")).strip(),
            ):
                if candidate and candidate.casefold() in ticker_map:
                    return ticker_map[candidate.casefold()]
        return None

    def _resolve_latest_value(self, records: list[dict[str, Any]], field_name: str) -> str:
        latest_raw = ""
        latest_timestamp: datetime | None = None
        for row in records:
            raw_value = str(row.get(field_name, "")).strip()
            parsed = self._parse_datetime(raw_value)
            if parsed is None:
                continue
            if latest_timestamp is None or parsed > latest_timestamp:
                latest_timestamp = parsed
                latest_raw = raw_value
        return format_swiss_timestamp(latest_raw) if latest_raw else "-"

    def _resolve_latest_published(self, records: list[dict[str, Any]]) -> str:
        latest_raw = ""
        latest_timestamp: datetime | None = None
        for row in records:
            raw_value = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            parsed = self._parse_datetime(raw_value)
            if parsed is None:
                continue
            if latest_timestamp is None or parsed > latest_timestamp:
                latest_timestamp = parsed
                latest_raw = raw_value
        return format_swiss_timestamp(latest_raw) if latest_raw else "-"

    def _resolve_record_timestamp(self, row: dict[str, Any]) -> str | None:
        for field_name in ("ingested_at", "analysis_timestamp", "published_at", "published_date"):
            raw_value = str(row.get(field_name, "")).strip()
            if self._parse_datetime(raw_value) is not None:
                return raw_value
        return None

    def _sort_timestamp(self, row: dict[str, Any]) -> float:
        raw_value = self._resolve_record_timestamp(row)
        parsed = self._parse_datetime(raw_value)
        if parsed is None:
            return 0.0
        return parsed.timestamp()

    @staticmethod
    def _format_chart_date(date_label: str) -> str:
        parts = str(date_label).split(".")
        if len(parts) != 3:
            return date_label
        day, month, year = parts
        return f"{year}-{month}-{day}"

    @staticmethod
    def _sort_date_label(date_label: str) -> str:
        return LongTermPage._format_chart_date(date_label)

    def _effective_last_run_raw(self) -> str:
        """Pick the in-memory last_run_at if present, else the datastore-derived value."""
        in_memory = str(self.trend_status.get("last_run_at", "") or "").strip()
        if in_memory:
            return in_memory
        payload = st.session_state.get(self._STATE_KEY, {})
        if isinstance(payload, dict):
            return str(payload.get("latest_ingested_at", "") or "").strip()
        return ""

    @classmethod
    def _compute_latest_ingested_at(cls, records: list[dict[str, Any]]) -> str:
        latest_raw = ""
        latest_dt: datetime | None = None
        for row in records:
            raw_value = str(row.get("ingested_at", "")).strip()
            parsed = cls._parse_datetime(raw_value)
            if parsed is None:
                continue
            if latest_dt is None or parsed > latest_dt:
                latest_dt = parsed
                latest_raw = raw_value
        return latest_raw

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

    @staticmethod
    def _render_message(message: str, ok: bool) -> None:
        if not message:
            return
        if ok:
            st.success(message)
        else:
            st.error(message)
