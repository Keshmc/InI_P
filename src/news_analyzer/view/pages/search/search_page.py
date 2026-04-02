"""News search and analysis pages."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser
import streamlit as st

from news_analyzer.model import PipelineProgress, SearchRequest
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.search.sentiment_score import render_sentiment_meter

TOPIC_OPTIONS = [
    "WORLD",
    "NATION",
    "BUSINESS",
    "TECHNOLOGY",
    "ENTERTAINMENT",
    "SPORTS",
    "SCIENCE",
    "HEALTH",
]
PERIOD_OPTIONS = ["1h", "6h", "12h", "1d", "3d", "7d"]


class NewsSearchPage:
    """Owns state + rendering for the complete news search flow."""

    _SEARCH_PAYLOAD_KEY = "news_search_payload"
    _PROGRESS_PHASES = ["collect", "check_existing", "analyze", "persist", "reload", "done"]

    def __init__(self, presenter: NewsPresenter) -> None:
        self.presenter = presenter

    def render(self) -> None:
        """Render search form and append analysis below when available."""
        self._render_search_form()
        payload = st.session_state.get(self._SEARCH_PAYLOAD_KEY)
        if payload:
            st.divider()
            self._render_analysis(payload)

    def _render_search_form(self) -> None:
        form_col, spacer_col = st.columns([2.4, 1.6])
        del spacer_col

        with form_col:
            st.title("News Search")
            st.write(
                "Pipeline: bestehende Firestore-Artikel uberspringen, neue Artikel analysieren,"
                " speichern und danach fur die Darstellung erneut aus Firestore laden."
            )

            mode = st.radio("Search Mode", options=["Keyword", "Topic"], horizontal=True, key="search_mode")

            keyword = ""
            topic = ""
            if mode == "Keyword":
                keyword = st.text_input("Keyword", placeholder="e.g. NVIDIA, Tesla, Apple", key="search_keyword")
            else:
                topic = st.selectbox("Topic", options=TOPIC_OPTIONS, key="search_topic")

            period_default_index = PERIOD_OPTIONS.index("1d")
            period = st.selectbox(
                "Time Interval",
                options=PERIOD_OPTIONS,
                index=period_default_index,
                key="search_period",
            )
            st.caption("All available matches in the selected time interval will be processed.")

            with st.expander("Advanced Settings", expanded=False):
                col_a, col_b = st.columns(2)
                with col_a:
                    extract_full_text = st.checkbox(
                        "Extract full article text",
                        value=True,
                        key="search_extract_full_text",
                    )
                    include_entities = st.checkbox(
                        "Include entity extraction",
                        value=True,
                        key="search_include_entities",
                    )
                with col_b:
                    st.info("No artificial UI cap. Provider limits are handled automatically.")

            submitted = st.button("Pipeline starten", type="primary", width="stretch", key="search_submit")

            if not submitted:
                return

            request = SearchRequest(
                mode=mode.lower(),
                keyword=keyword.strip(),
                topic=topic.strip().upper(),
                period=period,
                max_results=1000,
                extract_full_text=extract_full_text,
                include_entities=include_entities,
                use_mock_nlp=False,
                fallback_to_mock_on_error=False,
                store_to_datastore=True,
                industry_sector="",
            )

            if request.mode == "keyword" and not request.keyword:
                st.error("Please enter a keyword.")
                return

            # Remove previous results before loading the new search.
            st.session_state.pop(self._SEARCH_PAYLOAD_KEY, None)
            st.session_state.pop("news_search_message", None)
            st.session_state.pop("news_search_ok", None)

            response = self._show_loading_screen(request)
            st.session_state[self._SEARCH_PAYLOAD_KEY] = response.payload
            st.session_state["news_search_message"] = response.message
            st.session_state["news_search_ok"] = response.ok

    def _render_analysis(self, payload: dict[str, Any]) -> None:
        records = payload.get("records", [])
        summary = payload.get("summary", {})
        warnings = payload.get("warnings", [])
        errors = payload.get("errors", [])
        request = payload.get("request", {})

        st.title("Search Analysis")
        st.caption("Results are shown from the latest Firestore reload.")

        articles_found = int(summary.get("articles_found", 0))
        existing_articles = int(summary.get("existing_articles", 0))
        new_articles = int(summary.get("new_articles", 0))
        analyzed_articles = int(summary.get("analyzed_articles", 0))
        saved_articles = int(summary.get("saved_articles", 0))
        loaded_articles = int(summary.get("loaded_articles", len(records)))
        total_articles = max(articles_found, loaded_articles, 1)
        period_label = str(request.get("period", "")).strip() or "selected interval"
        status_ratio = min(loaded_articles / total_articles, 1.0)
        st.progress(
            status_ratio,
            text=f"Status: {loaded_articles}/{total_articles} article(s) loaded from Firestore in the last {period_label}",
        )

        status_message = st.session_state.get("news_search_message", "Search completed.")
        if st.session_state.get("news_search_ok", True):
            st.success(f"Status: {status_message}")
        else:
            st.warning(f"Status: {status_message}")

        st.divider()
        metric_cols = st.columns(6)
        metric_cols[0].metric("Fetched", str(articles_found))
        metric_cols[1].metric("Already in DB", str(existing_articles))
        metric_cols[2].metric("New", str(new_articles))
        metric_cols[3].metric("Analyzed", str(analyzed_articles))
        metric_cols[4].metric("Saved", str(saved_articles))
        metric_cols[5].metric("Loaded", str(loaded_articles))

        st.info("Neue Artikel wurden automatisch in Firestore gespeichert und danach neu geladen.")

        if warnings:
            with st.expander(f"Warnings ({len(warnings)})"):
                for warning in warnings:
                    st.write(f"- {warning}")
        if errors:
            with st.expander(f"Errors ({len(errors)})"):
                for error in errors:
                    st.write(f"- {error}")

        st.markdown("#### Sentiment Score")
        avg_sentiment = float(summary.get("avg_sentiment_score", 0.0))
        avg_magnitude = float(summary.get("avg_sentiment_magnitude", 0.0))
        col_metric, col_meter = st.columns([1.4, 3])
        with col_metric:
            metric_a, metric_b = st.columns(2)
            with metric_a:
                st.metric("Average Score", f"{avg_sentiment:+.3f}")
            with metric_b:
                st.metric("Average Magnitude", f"{avg_magnitude:.3f}")
        with col_meter:
            render_sentiment_meter(avg_sentiment)

        sentiment_distribution = self._build_sentiment_distribution(records)
        st.markdown("#### Sentiment Distribution")
        pie_values = [
            {"label": "Positive", "count": int(sentiment_distribution.get("positive", 0))},
            {"label": "Neutral", "count": int(sentiment_distribution.get("neutral", 0))},
            {"label": "Negative", "count": int(sentiment_distribution.get("negative", 0))},
        ]
        total_distribution = sum(item["count"] for item in pie_values)
        if total_distribution <= 0:
            st.info("No sentiment distribution available yet.")
        else:
            chart_col, table_col = st.columns([2.6, 1.4])
            with chart_col:
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
            with table_col:
                st.dataframe(
                    [
                        {"Label": "Positive", "Articles": pie_values[0]["count"]},
                        {"Label": "Neutral", "Articles": pie_values[1]["count"]},
                        {"Label": "Negative", "Articles": pie_values[2]["count"]},
                    ],
                    width="stretch",
                    hide_index=True,
                )

        st.divider()
        st.markdown("#### Sentiment Trend (Publication Time)")
        trend_rows = self._build_trend_rows(records)
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
            st.info("No trend data available (published date/time missing).")

        st.divider()
        st.markdown("#### Top Extracted Entities")
        entity_counts = self._build_entity_counts(records)
        if entity_counts:
            chart_rows = [{"Entity": name, "Count": count} for name, count in entity_counts[:15]]
            st.bar_chart(chart_rows, x="Entity", y="Count", horizontal=True)
        else:
            st.info("No entities extracted.")

        st.divider()
        st.markdown("#### Extracted Data")
        filtered_rows = self._render_table_filters_and_data(records)
        st.caption(f"Showing: {len(filtered_rows)} / {len(records)} rows")

        col_clear = st.columns([1, 2])[0]
        with col_clear:
            if st.button("Clear results", width="stretch"):
                st.session_state.pop(self._SEARCH_PAYLOAD_KEY, None)
                st.session_state.pop("news_search_message", None)
                st.session_state.pop("news_search_ok", None)
                st.rerun()

    def _render_table_filters_and_data(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            text_filter = st.text_input("Filter Text (Title/Source/Query)", value="").strip().lower()
        with col_b:
            sentiment_min, sentiment_max = st.slider(
                "Sentiment Range",
                min_value=-1.0,
                max_value=1.0,
                value=(-1.0, 1.0),
                step=0.05,
            )
        with col_c:
            all_statuses = sorted({str(row.get("status", "unknown")) for row in records})
            selected_status = st.multiselect(
                "Status",
                options=all_statuses,
                default=all_statuses,
            )

        filtered: list[dict[str, Any]] = []
        for row in records:
            sentiment = float(row.get("sentiment_score", 0.0))
            if sentiment < sentiment_min or sentiment > sentiment_max:
                continue

            status = str(row.get("status", "unknown"))
            if selected_status and status not in selected_status:
                continue

            if text_filter:
                searchable = " ".join(
                    [
                        str(row.get("title", "")),
                        str(row.get("source", "")),
                        str(row.get("query", "")),
                        str(row.get("topic", "")),
                    ]
                ).lower()
                if text_filter not in searchable:
                    continue

            filtered.append(row)

        table_rows = [
            {
                "title": str(row.get("title", "")).strip(),
                "source": str(row.get("source", "")).strip(),
                "published_date": str(row.get("published_date", "")).strip(),
                "sentiment_score": round(float(row.get("sentiment_score", 0.0)), 4),
                "sentiment_magnitude": round(float(row.get("sentiment_magnitude", 0.0)), 4),
                "sentiment_label": self._sentiment_label(float(row.get("sentiment_score", 0.0))),
                "status": str(row.get("status", "")).strip(),
                "url": str(row.get("url", "")).strip(),
            }
            for row in filtered
        ]
        st.dataframe(table_rows, width="stretch", hide_index=True)
        return filtered

    @staticmethod
    def _build_entity_counts(records: list[dict[str, Any]]) -> list[tuple[str, int]]:
        counter: Counter[str] = Counter()
        for row in records:
            entities = row.get("entities", [])
            if not isinstance(entities, list):
                continue
            for entity in entities:
                if isinstance(entity, dict):
                    name = str(entity.get("name", "")).strip()
                    if name:
                        counter[name] += 1
        return counter.most_common()

    @staticmethod
    def _sentiment_label(score: float) -> str:
        if score > 0.1:
            return "positive"
        if score < -0.1:
            return "negative"
        return "neutral"

    def _build_sentiment_distribution(self, records: list[dict[str, Any]]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for row in records:
            score = float(row.get("sentiment_score", 0.0))
            counts[self._sentiment_label(score)] += 1
        return {
            "positive": int(counts.get("positive", 0)),
            "neutral": int(counts.get("neutral", 0)),
            "negative": int(counts.get("negative", 0)),
        }

    def _show_loading_screen(self, request: SearchRequest):
        progress = st.progress(0.0, text="Pipeline started...")
        status_line = st.empty()
        stat_line = st.empty()

        def _on_progress(update: PipelineProgress) -> None:
            safe_total = max(int(update.total), 1)
            safe_processed = max(0, min(int(update.processed), safe_total))
            ratio = self._build_progress_ratio(update.phase, safe_processed, safe_total)
            progress.progress(
                ratio,
                text=update.message,
            )
            status_line.caption(
                f"Phase: {update.phase} | Step: {safe_processed}/{safe_total}"
            )
            stat_line.caption(
                "Existing/New/Analyzed/Saved/Loaded: "
                f"{update.existing_articles}/{update.new_articles}/"
                f"{update.analyzed_articles}/{update.saved_articles}/{update.loaded_articles}"
            )

        response = self.presenter.run_news_search(request, progress_callback=_on_progress)

        payload = response.payload if isinstance(response.payload, dict) else {}
        summary = payload.get("summary", {})
        records = payload.get("records", [])
        final_total = max(int(summary.get("articles_found", len(records))), 1)
        progress.progress(
            1.0,
            text=(
                "Pipeline completed. "
                f"{len(records)} out of {final_total} article(s) loaded from Firestore."
            ),
        )
        status_line.caption("Status: pipeline completed")
        stat_line.caption(
            "Fetched/Existing/New/Analyzed/Saved/Loaded: "
            f"{int(summary.get('articles_found', 0))}/"
            f"{int(summary.get('existing_articles', 0))}/"
            f"{int(summary.get('new_articles', 0))}/"
            f"{int(summary.get('analyzed_articles', 0))}/"
            f"{int(summary.get('saved_articles', 0))}/"
            f"{int(summary.get('loaded_articles', len(records)))}"
        )
        return response

    def _build_progress_ratio(self, phase: str, processed: int, total: int) -> float:
        if phase == "done":
            return 1.0

        try:
            phase_index = self._PROGRESS_PHASES.index(phase)
        except ValueError:
            phase_index = 0

        phase_ratio = processed / max(total, 1)
        return min(((phase_index + phase_ratio) / max(len(self._PROGRESS_PHASES), 1)), 0.99)

    def _build_trend_rows(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in records:
            published_value = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
            parsed_dt = self._parse_datetime(published_value)
            if parsed_dt is None:
                continue

            rows.append(
                {
                    "published_time": parsed_dt.isoformat(),
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
