"""News search and analysis pages."""

from __future__ import annotations

from typing import Any

import streamlit as st

from news_analyzer.model import PipelineProgress, SearchRequest, build_datastore_insights, entities_to_display, sentiment_label
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
    to_export_cell,
)

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
        render_page_header(
            eyebrow="Discover",
            title="News Search",
            subtitle=(
                "Search recent coverage by keyword. New matches are analyzed and saved to your "
                "article library automatically."
            ),
            meta="Timestamps in Europe/Zurich",
        )

        left_pad, center, right_pad = st.columns([1, 3, 1])
        del left_pad, right_pad

        with center:
            render_search_panel_header(
                title="Find recent coverage",
                subtitle="Type a keyword, pick a time window, and we'll do the rest.",
            )

            with st.container(border=True):
                keyword = st.text_input(
                    "Keyword",
                    placeholder="e.g. NVIDIA, Tesla, Apple",
                    key="search_keyword",
                    label_visibility="collapsed",
                    help="Enter a company, ticker, or topic to search for in recent news.",
                )

                st.caption("Time window")
                period = st.segmented_control(
                    "Time window",
                    options=PERIOD_OPTIONS,
                    default=st.session_state.get("search_period", "1d"),
                    key="search_period",
                    label_visibility="collapsed",
                )
                if period is None:
                    period = "1d"

                st.markdown('<div class="na-toggle-row">', unsafe_allow_html=True)
                toggle_col_a, toggle_col_b = st.columns([1, 1], gap="small")
                with toggle_col_a:
                    extract_full_text = st.toggle(
                        "Full article text",
                        value=True,
                        key="search_extract_full_text",
                        help="Fetch and analyze the full article body instead of just the headline + summary.",
                    )
                with toggle_col_b:
                    include_entities = st.toggle(
                        "Entity extraction",
                        value=True,
                        key="search_include_entities",
                        help="Identify named entities (companies, people, locations) per article.",
                    )
                st.markdown("</div>", unsafe_allow_html=True)

                submitted = st.button(
                    "Analyze coverage",
                    type="primary",
                    width="stretch",
                    key="search_submit",
                )

            st.caption(
                "Tracking the same ticker over weeks? Open **Article Library → Long-Term Ticker**."
            )

            if not submitted:
                return

            request = SearchRequest(
                mode="keyword",
                keyword=keyword.strip(),
                topic="",
                period=period,
                max_results=1000,
                extract_full_text=extract_full_text,
                include_entities=include_entities,
                use_mock_nlp=False,
                fallback_to_mock_on_error=True,
                store_to_datastore=True,
                industry_sector="",
            )

            if not request.keyword:
                st.error("Please enter a keyword.")
                return

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
        insights = build_datastore_insights(records)

        render_section_heading(
            "Search Analysis",
            "Latest saved records for this query, with timestamps in Europe/Zurich.",
        )

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
            text=f"{loaded_articles} of {total_articles} saved article(s) loaded for the {period_label} window.",
        )

        status_message = st.session_state.get("news_search_message", "Search completed.")
        if st.session_state.get("news_search_ok", True):
            st.success(status_message)
        else:
            st.warning(status_message)

        st.divider()
        with st.container(border=True):
            row_a = st.columns(3)
            row_a[0].metric("Fetched", str(articles_found))
            row_a[1].metric("Already in library", str(existing_articles))
            row_a[2].metric("New", str(new_articles))
            row_b = st.columns(3)
            row_b[0].metric("Analyzed", str(analyzed_articles))
            row_b[1].metric("Saved", str(saved_articles))
            row_b[2].metric("Loaded", str(loaded_articles))

        if warnings:
            with st.expander(f"Processing notes ({len(warnings)})"):
                for warning in warnings:
                    st.write(f"- {warning}")
        if errors:
            with st.expander(f"Issues ({len(errors)})"):
                for error in errors:
                    st.write(f"- {error}")

        render_section_heading(
            "Sentiment Score",
            "Average tone and strength of coverage in this window.",
        )
        avg_sentiment = float(summary.get("avg_sentiment_score", 0.0))
        avg_magnitude = float(summary.get("avg_sentiment_magnitude", 0.0))
        col_metric, col_meter = st.columns([1.4, 3])
        with col_metric:
            metric_a, metric_b = st.columns(2)
            with metric_a:
                st.metric("Average score", f"{avg_sentiment:+.3f}")
            with metric_b:
                st.metric("Average magnitude", f"{avg_magnitude:.3f}")
        with col_meter:
            render_sentiment_meter(avg_sentiment)

        sentiment_distribution = insights.sentiment.as_distribution_rows()
        render_section_heading("Sentiment Distribution")
        chart_col, table_col = st.columns([2.6, 1.4])
        with chart_col:
            render_sentiment_donut(sentiment_distribution)
        with table_col:
            st.dataframe(
                [{"Label": item["label"], "Articles": item["count"]} for item in sentiment_distribution],
                width="stretch",
                hide_index=True,
            )

        st.divider()
        render_section_heading("Sentiment Over Time")
        trend_rows: list[dict[str, Any]] = []
        for item in insights.trend_points:
            row = item.as_dict()
            date_value, time_value = format_swiss_date_time(row.get("published_time", ""))
            row["published_date_local"] = date_value
            row["published_time_local"] = time_value
            trend_rows.append(row)
        if trend_rows:
            st.vega_lite_chart(
                trend_rows,
                {
                    "mark": {"type": "line", "point": True},
                    "encoding": {
                        "x": {
                            "field": "published_time",
                            "type": "temporal",
                            "title": "Published time (Zurich)",
                            "axis": {"format": "%d.%m.%Y %H:%M"},
                        },
                        "y": {
                            "field": "sentiment_score",
                            "type": "quantitative",
                            "title": "Sentiment",
                            "scale": {"domain": [-1.0, 1.0]},
                        },
                        "tooltip": [
                            {"field": "title", "type": "nominal", "title": "Title"},
                            {"field": "source", "type": "nominal", "title": "Source"},
                            {"field": "published_date_local", "type": "nominal", "title": "Date"},
                            {"field": "published_time_local", "type": "nominal", "title": "Time (Zurich)"},
                            {"field": "sentiment_score", "type": "quantitative", "title": "Sentiment"},
                        ],
                    },
                },
                width="stretch",
            )
        else:
            st.info("No trend data available (published date/time missing).")

        st.divider()
        render_section_heading("Top Extracted Entities")
        top_entity_rows = [{"entity": item.label, "count": item.count} for item in insights.top_entities]
        if top_entity_rows:
            chart_rows = [{"Entity": item["entity"], "Count": item["count"]} for item in top_entity_rows]
            st.bar_chart(chart_rows, x="Entity", y="Count", horizontal=True)
        else:
            st.info("No entities extracted.")

        st.divider()
        render_section_heading(
            "Results Table",
            "Filter, sort, and review every loaded article.",
        )
        filtered_rows = self._render_table_filters_and_data(records)
        st.caption(f"Showing {len(filtered_rows)} of {len(records)} rows")

        st.divider()
        render_section_heading("Export")
        export_sections = self._build_export_sections(
            request=request,
            summary=summary,
            records=records,
            filtered_rows=filtered_rows,
            sentiment_distribution=sentiment_distribution,
            top_entities=top_entity_rows,
            trend_rows=trend_rows,
        )
        render_export_downloads(
            sections=export_sections,
            file_stem=build_export_file_stem(
                prefix="news_search",
                parts=[str(request.get("keyword", "")).strip() or str(request.get("topic", "")).strip()],
            ),
            key_prefix="news_search_export",
            caption="Export the current search results as CSV, JSON, or Excel.",
        )

    def _render_table_filters_and_data(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            text_filter = st.text_input("Search title, source, trend, or entities", value="").strip().lower()
        with col_b:
            sentiment_min, sentiment_max = st.slider(
                "Sentiment range",
                min_value=-1.0,
                max_value=1.0,
                value=(-1.0, 1.0),
                step=0.05,
            )
        with col_c:
            all_statuses = sorted({str(row.get("status", "unknown")) for row in records})
            selected_status = st.multiselect(
                "Processing status",
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
                entity_text = entities_to_display(row.get("entities", []))
                searchable = " ".join(
                    [
                        str(row.get("title", "")),
                        str(row.get("source", "")),
                        str(row.get("query", "")),
                        self._trend_from_record(row),
                        entity_text,
                    ]
                ).lower()
                if text_filter not in searchable:
                    continue

            filtered.append(row)

        table_rows = [
            {
                "title": str(row.get("title", "")).strip(),
                "source": str(row.get("source", "")).strip(),
                "date": format_swiss_date_time(
                    str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
                )[0],
                "time": format_swiss_date_time(
                    str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
                )[1],
                "trend": self._trend_from_record(row),
                "sentiment_score": round(float(row.get("sentiment_score", 0.0)), 4),
                "sentiment_magnitude": round(float(row.get("sentiment_magnitude", 0.0)), 4),
                "sentiment_label": sentiment_label(float(row.get("sentiment_score", 0.0))),
                "entities": entities_to_display(row.get("entities", [])),
                "status": str(row.get("status", "")).strip(),
                "url": str(row.get("url", "")).strip(),
            }
            for row in filtered
        ]
        st.dataframe(table_rows, width="stretch", hide_index=True)
        return filtered

    def _build_export_sections(
        self,
        request: dict[str, Any],
        summary: dict[str, Any],
        records: list[dict[str, Any]],
        filtered_rows: list[dict[str, Any]],
        sentiment_distribution: list[dict[str, Any]],
        top_entities: list[dict[str, Any]],
        trend_rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        summary_row = {
            "mode": str(request.get("mode", "")).strip(),
            "keyword": str(request.get("keyword", "")).strip(),
            "trend": str(request.get("topic", "")).strip() or str(request.get("keyword", "")).strip(),
            "period": str(request.get("period", "")).strip(),
            "articles_found": int(summary.get("articles_found", 0)),
            "existing_articles": int(summary.get("existing_articles", 0)),
            "new_articles": int(summary.get("new_articles", 0)),
            "analyzed_articles": int(summary.get("analyzed_articles", 0)),
            "saved_articles": int(summary.get("saved_articles", 0)),
            "loaded_articles": int(summary.get("loaded_articles", len(records))),
            "avg_sentiment_score": float(summary.get("avg_sentiment_score", 0.0)),
            "avg_sentiment_magnitude": float(summary.get("avg_sentiment_magnitude", 0.0)),
            "positive_count": int(summary.get("positive_count", 0)),
            "neutral_count": int(summary.get("neutral_count", 0)),
            "negative_count": int(summary.get("negative_count", 0)),
        }

        sentiment_rows = [
            {"label": str(item.get("label", "")).lower(), "count": int(item.get("count", 0))}
            for item in sentiment_distribution
        ]
        extracted_filtered_rows = self._build_extracted_table_rows(filtered_rows)
        extracted_all_rows = self._build_extracted_table_rows(records)
        article_rows = [self._build_article_export_row(row) for row in records]

        return {
            "summary": [summary_row],
            "sentiment_distribution": sentiment_rows,
            "top_entities": top_entities,
            "sentiment_trend": trend_rows,
            "extracted_data_filtered": extracted_filtered_rows,
            "extracted_data_all": extracted_all_rows,
            "articles_full": article_rows,
        }

    def _build_extracted_table_rows(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": str(row.get("title", "")).strip(),
                "source": str(row.get("source", "")).strip(),
                "date": format_swiss_date_time(
                    str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
                )[0],
                "time": format_swiss_date_time(
                    str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
                )[1],
                "trend": self._trend_from_record(row),
                "sentiment_score": round(float(row.get("sentiment_score", 0.0)), 4),
                "sentiment_magnitude": round(float(row.get("sentiment_magnitude", 0.0)), 4),
                "sentiment_label": sentiment_label(float(row.get("sentiment_score", 0.0))),
                "entities": entities_to_display(row.get("entities", [])),
                "status": str(row.get("status", "")).strip(),
                "url": str(row.get("url", "")).strip(),
            }
            for row in records
        ]

    def _build_article_export_row(self, row: dict[str, Any]) -> dict[str, Any]:
        export_row: dict[str, Any] = {}
        for key, value in row.items():
            export_row[str(key)] = to_export_cell(value)
        export_row["entities_display"] = entities_to_display(row.get("entities", []))
        export_row["trend"] = self._trend_from_record(row)
        date_value, time_value = format_swiss_date_time(
            str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
        )
        export_row["date"] = date_value
        export_row["time"] = time_value
        return export_row

    @staticmethod
    def _trend_from_record(row: dict[str, Any]) -> str:
        query = str(row.get("query", "")).strip()
        if query:
            return query
        return str(row.get("topic", "")).strip()

    def _show_loading_screen(self, request: SearchRequest):
        keyword_label = request.keyword.strip() or "your query"
        loading_zone = st.empty()
        with loading_zone.container():
            st.markdown(
                render_loading_card_html(
                    title=f"Analyzing coverage for “{keyword_label}”",
                    subtitle="Fetching articles, scoring sentiment, and saving results to your library.",
                ),
                unsafe_allow_html=True,
            )
            progress_placeholder = st.empty()
            progress = progress_placeholder.progress(0.0, text="Starting analysis…")

            def _on_progress(update: PipelineProgress) -> None:
                safe_total = max(int(update.total), 1)
                safe_processed = max(0, min(int(update.processed), safe_total))
                ratio = self._build_progress_ratio(update.phase, safe_processed, safe_total)
                progress.progress(
                    ratio,
                    text=self._build_progress_message(update, safe_processed, safe_total),
                )

            response = self.presenter.run_news_search(request, progress_callback=_on_progress)

            payload = response.payload if isinstance(response.payload, dict) else {}
            summary = payload.get("summary", {})
            records = payload.get("records", [])
            final_total = max(int(summary.get("articles_found", len(records))), 1)
            progress.progress(
                1.0,
                text=f"Done — {len(records)} of {final_total} saved article(s) ready.",
            )

        loading_zone.empty()
        return response

    @staticmethod
    def _build_progress_message(update: PipelineProgress, processed: int, total: int) -> str:
        """Return a short, user-friendly progress label for the loading bar."""
        phase_messages = {
            "collect": "Fetching articles…",
            "check_existing": "Checking for duplicates…",
            "analyze": f"Running sentiment & entity analysis ({processed}/{total})…",
            "persist": "Saving new articles…",
            "reload": "Refreshing view…",
            "done": "Done.",
        }
        return phase_messages.get(update.phase, "Processing…")

    def _build_progress_ratio(self, phase: str, processed: int, total: int) -> float:
        if phase == "done":
            return 1.0

        try:
            phase_index = self._PROGRESS_PHASES.index(phase)
        except ValueError:
            phase_index = 0

        phase_ratio = processed / max(total, 1)
        return min(((phase_index + phase_ratio) / max(len(self._PROGRESS_PHASES), 1)), 0.99)
