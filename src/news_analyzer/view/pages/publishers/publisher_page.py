"""Dedicated publisher search and sentiment page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.search.sentiment_score import render_sentiment_meter
from news_analyzer.view.utils import format_swiss_date_time


class PublisherPage:
    """Search publishers from the datastore and show sentiment feedback."""

    _SUMMARY_PAYLOAD_KEY = "publisher_sentiment_summary_payload"
    _SUMMARY_MESSAGE_KEY = "publisher_sentiment_summary_message"
    _SUMMARY_OK_KEY = "publisher_sentiment_summary_ok"

    _DATASTORE_LIMIT = 5000
    _SUMMARY_MATCH_LIMIT = 5000

    def __init__(self, presenter: NewsPresenter) -> None:
        self.presenter = presenter

    def render(self) -> None:
        form_col, spacer_col = st.columns([2.4, 1.6])
        del spacer_col

        with form_col:
            st.title("Publisher Sentiment")
            st.caption("Ueberblick ueber alle Publisher aus dem Datastore.")
            summary_reload = st.button("Summary laden", type="primary", width="stretch")
            if summary_reload or self._SUMMARY_PAYLOAD_KEY not in st.session_state:
                self._load_summary_payload()

        self._render_summary_mode()

    def _render_summary_mode(self) -> None:
        payload = st.session_state.get(self._SUMMARY_PAYLOAD_KEY, {})
        message = st.session_state.get(self._SUMMARY_MESSAGE_KEY, "")
        if message:
            if st.session_state.get(self._SUMMARY_OK_KEY, True):
                st.success(message)
            else:
                st.error(message)

        if not isinstance(payload, dict):
            st.info("Keine Publisher-Daten geladen.")
            return

        matches = payload.get("matches", [])
        if not matches:
            st.info("Keine Publisher-Daten im Datastore vorhanden.")
            return

        total_publishers = int(payload.get("total_publishers", 0))
        record_count = int(payload.get("record_count", 0))
        positive_count, neutral_count, negative_count = self._count_sentiment_groups(matches)
        average_score = self._average_match_score(matches)
        most_active = self._resolve_most_active_publisher(matches)

        st.divider()
        metric_cols = st.columns(5)
        metric_cols[0].metric("Stored Articles", str(record_count))
        metric_cols[1].metric("Publishers", str(total_publishers))
        metric_cols[2].metric("Positive", str(positive_count))
        metric_cols[3].metric("Neutral", str(neutral_count))
        metric_cols[4].metric("Negative", str(negative_count))

        insight_col, meter_col = st.columns([1.2, 2.3])
        with insight_col:
            st.metric("Average Publisher Score", f"{average_score:+.3f}")
            st.metric("Most Active Publisher", most_active)
        with meter_col:
            render_sentiment_meter(average_score)

        st.divider()
        st.markdown("#### Publisher Distribution")
        distribution_rows = [
            {"label": "Positive", "count": positive_count},
            {"label": "Neutral", "count": neutral_count},
            {"label": "Negative", "count": negative_count},
        ]
        chart_col, table_col = st.columns([2.4, 1.2])
        with chart_col:
            st.vega_lite_chart(
                distribution_rows,
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
                            {"field": "count", "type": "quantitative", "title": "Publishers"},
                        ],
                    },
                },
                use_container_width=True,
            )
        with table_col:
            st.dataframe(
                [{"Label": row["label"], "Publishers": row["count"]} for row in distribution_rows],
                width="stretch",
                hide_index=True,
            )

        st.divider()
        st.markdown("#### Most Active Publishers")
        top_activity_rows = sorted(
            self._build_match_rows(matches),
            key=lambda row: int(row.get("articles", 0)),
            reverse=True,
        )[:15]
        if top_activity_rows:
            ranked_rows = [
                {
                    "Rank": index + 1,
                    "Publisher": str(row.get("publisher", "")).strip(),
                    "Articles": int(row.get("articles", 0)),
                }
                for index, row in enumerate(top_activity_rows)
            ]
            st.vega_lite_chart(
                ranked_rows,
                {
                    "mark": {"type": "bar", "cornerRadiusEnd": 3},
                    "encoding": {
                        "y": {"field": "Publisher", "type": "nominal", "sort": "-x", "title": "Publisher"},
                        "x": {"field": "Articles", "type": "quantitative", "title": "Articles"},
                        "color": {"value": "#2471A3"},
                        "tooltip": [
                            {"field": "Rank", "type": "quantitative", "title": "Rank"},
                            {"field": "Publisher", "type": "nominal", "title": "Publisher"},
                            {"field": "Articles", "type": "quantitative", "title": "Articles"},
                        ],
                    },
                },
                use_container_width=True,
            )
        else:
            st.info("Keine Publisher-Rangliste vorhanden.")

        st.divider()
        st.markdown("#### Strongest Sentiment by Publisher")
        positive_rows = sorted(
            self._build_match_rows(matches),
            key=lambda row: float(row.get("avg_score", 0.0)),
            reverse=True,
        )[:10]
        negative_rows = sorted(
            self._build_match_rows(matches),
            key=lambda row: float(row.get("avg_score", 0.0)),
        )[:10]
        col_positive, col_negative = st.columns(2)
        with col_positive:
            st.caption("Top Positive")
            st.dataframe(positive_rows, width="stretch", hide_index=True)
        with col_negative:
            st.caption("Top Negative")
            st.dataframe(negative_rows, width="stretch", hide_index=True)

        st.divider()
        st.markdown("#### All Publishers")
        st.dataframe(self._build_match_rows(matches), width="stretch", hide_index=True)

    def _load_summary_payload(self) -> None:
        response = self.presenter.search_publishers(
            query="",
            datastore_limit=self._DATASTORE_LIMIT,
            match_limit=self._SUMMARY_MATCH_LIMIT,
            article_limit=8,
        )
        st.session_state[self._SUMMARY_PAYLOAD_KEY] = response.payload
        st.session_state[self._SUMMARY_MESSAGE_KEY] = response.message
        st.session_state[self._SUMMARY_OK_KEY] = response.ok

    def _count_sentiment_groups(self, matches: list[dict[str, Any]]) -> tuple[int, int, int]:
        positive_count = 0
        neutral_count = 0
        negative_count = 0
        for item in matches:
            if not isinstance(item, dict):
                continue
            sentiment = str(item.get("dominant_sentiment", "neutral")).strip().lower()
            if sentiment == "positive":
                positive_count += 1
            elif sentiment == "negative":
                negative_count += 1
            else:
                neutral_count += 1
        return positive_count, neutral_count, negative_count

    def _average_match_score(self, matches: list[dict[str, Any]]) -> float:
        scores = [float(item.get("average_score", 0.0)) for item in matches if isinstance(item, dict)]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 4)

    def _resolve_most_active_publisher(self, matches: list[dict[str, Any]]) -> str:
        ranked = sorted(
            [item for item in matches if isinstance(item, dict)],
            key=lambda item: int(item.get("article_count", 0)),
            reverse=True,
        )
        if not ranked:
            return "-"
        best = ranked[0]
        return (
            f"{str(best.get('publisher', '')).strip() or 'Unknown'} "
            f"({int(best.get('article_count', 0))})"
        )

    def _build_match_rows(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in matches:
            if not isinstance(item, dict):
                continue
            latest_date = self._format_datetime_label(str(item.get("latest_published_at", "")).strip())
            rows.append(
                {
                    "publisher": str(item.get("publisher", "")).strip(),
                    "articles": int(item.get("article_count", 0)),
                    "avg_score": round(float(item.get("average_score", 0.0)), 4),
                    "sentiment": self._format_sentiment_label(str(item.get("dominant_sentiment", "neutral"))),
                    "latest_article": latest_date,
                }
            )
        return rows

    @staticmethod
    def _format_datetime_label(raw_value: str) -> str:
        if not raw_value:
            return "-"
        date_value, time_value = format_swiss_date_time(raw_value)
        if date_value == "-" and time_value == "-":
            return "-"
        return f"{date_value} | {time_value}"

    @staticmethod
    def _format_sentiment_label(value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized == "positive":
            return "Positive"
        if normalized == "negative":
            return "Negative"
        return "Neutral"
