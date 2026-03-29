"""News search and analysis pages."""

from __future__ import annotations

from collections import Counter
import time
from typing import Any

import streamlit as st

from news_analyzer.model import SearchRequest
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
        st.title("News Search")
        st.write("Search news by keyword or topic and analyze sentiment and extracted entities.")

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
                extract_full_text = st.checkbox("Extract full article text", value=True, key="search_extract_full_text")
                include_entities = st.checkbox("Include entity extraction", value=True, key="search_include_entities")
            with col_b:
                st.info("No artificial UI cap. Provider limits are handled automatically.")

        submitted = st.button("Search", type="primary", width="stretch", key="search_submit")

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
            store_to_datastore=False,
            industry_sector="",
        )

        if request.mode == "keyword" and not request.keyword:
            st.error("Please enter a keyword.")
            return

        # Remove previous results before loading the new search.
        st.session_state.pop(self._SEARCH_PAYLOAD_KEY, None)
        st.session_state.pop("news_search_message", None)
        st.session_state.pop("news_search_ok", None)

        self._show_loading_screen()
        response = self.presenter.run_news_search(request)
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
        st.caption("Results are shown from the most recently loaded dataset.")

        articles_found = int(summary.get("articles_found", 0))
        period_label = str(request.get("period", "")).strip() or "selected interval"
        status_ratio = min(articles_found / 100.0, 1.0)
        st.progress(status_ratio, text=f"Status: {articles_found} articles found in the last {period_label}")

        status_message = st.session_state.get("news_search_message", "Search completed.")
        if st.session_state.get("news_search_ok", True):
            st.success(f"Status: {status_message}")
        else:
            st.warning(f"Status: {status_message}")

        st.divider()

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
        col_metric, col_meter = st.columns([1, 3])
        with col_metric:
            st.metric("Average", f"{avg_sentiment:+.3f}")
        with col_meter:
            render_sentiment_meter(avg_sentiment)

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

        col_store, col_clear = st.columns([2, 1])
        with col_store:
            if st.button("Store loaded data to datastore", type="primary", width="stretch"):
                store_response = self.presenter.store_last_search_to_datastore()
                if store_response.ok:
                    st.success(store_response.message)
                else:
                    st.error(store_response.message)
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
    def _show_loading_screen() -> None:
        loading = st.empty()
        loading.markdown("### Loading search and analysis...")
        progress = st.progress(0, text="Initializing search")
        for value, label in [
            (20, "Loading sources"),
            (45, "Processing articles"),
            (70, "Computing sentiment"),
            (90, "Extracting entities"),
            (100, "Finalizing"),
        ]:
            time.sleep(0.12)
            progress.progress(value, text=label)
        loading.empty()
