"""Firestore data browser page."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.model import DatastoreQuery
from news_analyzer.presenter import NewsPresenter


class DataStorePage:
    """Simple Firestore query and visualization page."""

    _STATE_KEY = "firestore_page_payload"

    def __init__(self, presenter: NewsPresenter) -> None:
        self.presenter = presenter

    def render(self) -> None:
        st.title("Firestore")
        st.caption("Load analyzed articles directly from Firestore and inspect sentiment trend.")

        with st.form("firestore_query_form"):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                keyword = st.text_input("Keyword contains", value="").strip()
            with col_b:
                topic = st.text_input("Topic (optional)", value="").strip().upper()
            with col_c:
                limit = int(st.number_input("Limit", min_value=1, max_value=1000, value=200, step=25))

            submitted = st.form_submit_button("Load from Firestore", type="primary")

        if submitted:
            response = self.presenter.query_datastore(
                DatastoreQuery(
                    company_keyword=keyword or None,
                    topic=topic or None,
                    limit=limit,
                )
            )
            st.session_state[self._STATE_KEY] = response.payload
            if response.ok:
                st.success(response.message)
            else:
                st.error(response.message)

        payload = st.session_state.get(self._STATE_KEY, {})
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records:
            st.info("No Firestore data loaded yet.")
            return

        st.divider()
        metric_col_a, metric_col_b, metric_col_c = st.columns(3)
        metric_col_a.metric("Records", str(int(payload.get("count", len(records)))))
        metric_col_b.metric("Avg Sentiment", f"{float(payload.get('avg_sentiment_score', 0.0)):+.3f}")
        metric_col_c.metric("Avg Magnitude", f"{float(payload.get('avg_sentiment_magnitude', 0.0)):.3f}")

        trend_rows = self._build_trend_rows(records)
        st.markdown("#### Sentiment Trend")
        if trend_rows:
            st.vega_lite_chart(
                trend_rows,
                {
                    "mark": {"type": "line", "point": True},
                    "encoding": {
                        "x": {"field": "published_time", "type": "temporal", "title": "Zeit"},
                        "y": {
                            "field": "sentiment_score",
                            "type": "quantitative",
                            "title": "Sentiment",
                            "scale": {"domain": [-1.0, 1.0]},
                        },
                        "tooltip": [
                            {"field": "title", "type": "nominal", "title": "Title"},
                            {"field": "source", "type": "nominal", "title": "Source"},
                            {"field": "published_time", "type": "temporal", "title": "Published"},
                            {"field": "sentiment_score", "type": "quantitative", "title": "Sentiment"},
                        ],
                    },
                },
                use_container_width=True,
            )
        else:
            st.info("No records with parseable publication date were found.")

        st.markdown("#### Records")
        rows = [
            {
                "title": str(item.get("title", "")).strip(),
                "source": str(item.get("source", "")).strip(),
                "query": str(item.get("query", "")).strip(),
                "published_date": str(item.get("published_date", "")).strip(),
                "sentiment_score": round(float(item.get("sentiment_score", 0.0)), 4),
                "sentiment_magnitude": round(float(item.get("sentiment_magnitude", 0.0)), 4),
                "status": str(item.get("status", "")).strip(),
                "url": str(item.get("url", "")).strip(),
            }
            for item in records
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

    def _build_trend_rows(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in records:
            raw_dt = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            parsed = self._parse_datetime(raw_dt)
            if parsed is None:
                continue
            rows.append(
                {
                    "published_time": parsed.isoformat(),
                    "sentiment_score": float(row.get("sentiment_score", 0.0)),
                    "title": str(row.get("title", "")).strip(),
                    "source": str(row.get("source", "")).strip(),
                }
            )
        rows.sort(key=lambda item: item["published_time"])
        return rows

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = date_parser.parse(value)
        except Exception:  # noqa: BLE001
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
