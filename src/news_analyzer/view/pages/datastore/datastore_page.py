"""Datastore dashboard page with aggregated analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.model import DatastoreInsights, DatastoreQuery, build_datastore_insights
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.search.sentiment_score import render_sentiment_meter
from news_analyzer.view.utils import format_swiss_date_time


class DataStorePage:
    """Datastore dashboard with trend/entity/sentiment analytics."""

    _STATE_KEY = "datastore_dashboard_payload"
    _MESSAGE_KEY = "datastore_dashboard_message"
    _OK_KEY = "datastore_dashboard_ok"
    _LIMIT = 5000

    def __init__(self, presenter: NewsPresenter) -> None:
        self.presenter = presenter

    def render(self) -> None:
        st.title("Datastore")
        st.caption("Allgemeine Daten und Trends aus allen gespeicherten Artikeln.")
        st.caption("Datum/Zeit im UI: Schweiz (Europe/Zurich), Format dd.mm.yyyy und hh:mm.")

        refresh_col, info_col = st.columns([1, 3])
        with refresh_col:
            refresh_clicked = st.button("Reload Datastore", width="stretch")
        with info_col:
            st.caption(
                f"Datastore wird automatisch geladen (bis zu {self._LIMIT} Artikel). "
                "Mit Reload werden die neuesten Daten neu abgerufen."
            )

        if refresh_clicked:
            self._load_payload(force_reload=True)
        else:
            self._load_payload(force_reload=False)

        payload = st.session_state.get(self._STATE_KEY, {})
        message = st.session_state.get(self._MESSAGE_KEY, "")
        if message:
            if st.session_state.get(self._OK_KEY, True):
                st.success(message)
            else:
                st.error(message)

        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records:
            st.info("Keine Datastore-Daten vorhanden oder geladen.")
            return

        insights = build_datastore_insights(records)
        self._render_facts(records=records, payload=payload, insights=insights)
        self._render_sentiment_section(insights=insights)
        self._render_trend_chart(insights=insights)
        self._render_entity_chart(insights=insights)
        self._render_publisher_chart(insights=insights)
        self._render_article_table(insights=insights)

    def _load_payload(self, force_reload: bool) -> None:
        if not force_reload and self._STATE_KEY in st.session_state:
            return

        response = self.presenter.query_datastore(DatastoreQuery(limit=self._LIMIT))
        st.session_state[self._STATE_KEY] = response.payload
        st.session_state[self._MESSAGE_KEY] = response.message
        st.session_state[self._OK_KEY] = response.ok

    def _render_facts(self, records: list[dict[str, Any]], payload: dict[str, Any], insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Stored Articles and Facts")

        oldest, newest = self._resolve_date_range(records)
        metrics = st.columns(6)
        metrics[0].metric("Stored Articles", str(int(payload.get("count", len(records)))))
        metrics[1].metric("Unique Publishers", str(int(insights.unique_publishers)))
        metrics[2].metric("Unique Trends", str(int(insights.unique_trends)))
        metrics[3].metric("Unique Entities", str(int(insights.unique_entities)))
        metrics[4].metric("Oldest Article (CH)", oldest)
        metrics[5].metric("Newest Article (CH)", newest)

    def _render_sentiment_section(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Allgemeines Sentiment und Stimmung")

        col_stats, col_meter = st.columns([1.4, 3])
        with col_stats:
            st.metric("Average Score", f"{insights.sentiment.average_score:+.3f}")
            st.metric("Average Magnitude", f"{insights.sentiment.average_magnitude:.3f}")
        with col_meter:
            render_sentiment_meter(insights.sentiment.average_score)

        st.markdown("#### Positive / Neutral / Negative")
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
            use_container_width=True,
        )

    def _render_trend_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Top Trends (Rangliste)")
        if not insights.top_trends:
            st.info("Keine Trends vorhanden.")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_trends]
        self._render_ranked_bar(rows=rows, label_field="Trend", value_field="Articles", color="#2471A3")

    def _render_entity_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Top Entities (Rangliste)")
        if not insights.top_entities:
            st.info("Keine Entities vorhanden.")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_entities]
        self._render_ranked_bar(rows=rows, label_field="Entity", value_field="Count", color="#0E6655")

    def _render_publisher_chart(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Most News by Publisher (Rangliste)")
        if not insights.top_publishers:
            st.info("Keine Publisher-Daten vorhanden.")
            return

        rows = [{"label": item.label, "count": int(item.count)} for item in insights.top_publishers]
        self._render_ranked_bar(rows=rows, label_field="Publisher", value_field="Articles", color="#935116")

    def _render_article_table(self, insights: DatastoreInsights) -> None:
        st.divider()
        st.markdown("#### Stored Articles")
        display_rows: list[dict[str, Any]] = []
        for row in insights.article_facts:
            raw_dt = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            date_value, time_value = format_swiss_date_time(raw_dt)
            normalized = dict(row)
            normalized["date"] = date_value
            normalized["time"] = time_value
            normalized.pop("published_date", None)
            normalized.pop("published_at", None)
            display_rows.append(normalized)
        st.dataframe(display_rows, width="stretch", hide_index=True)

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
                use_container_width=True,
            )
        with table_col:
            st.dataframe(ranked_rows, width="stretch", hide_index=True)

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
