"""News search and analysis pages."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from typing import Any
import zipfile

import streamlit as st

from news_analyzer.model import PipelineProgress, SearchRequest, build_datastore_insights, entities_to_display, sentiment_label
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view.pages.search.sentiment_score import render_sentiment_meter
from news_analyzer.view.utils import format_swiss_date_time

PERIOD_OPTIONS = ["1h", "6h", "12h", "1d", "3d", "7d"]
TREND_OPTIONS = ["Trump", "Iran", "Oil", "Gold", "NVDA", "USA"]


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
            st.caption("Search by keyword or choose a trending topic to analyze recent coverage.")
            st.caption("New articles are analyzed and added to the saved article library automatically.")

            if st.session_state.get("search_mode") not in {"Keyword", "Trend"}:
                st.session_state["search_mode"] = "Keyword"

            mode = st.radio("Search Mode", options=["Keyword", "Trend"], horizontal=True, key="search_mode")

            keyword = ""
            trend = ""
            if mode == "Keyword":
                keyword = st.text_input("Keyword", placeholder="e.g. NVIDIA, Tesla, Apple", key="search_keyword")
            else:
                if st.session_state.get("search_trend") not in TREND_OPTIONS:
                    st.session_state["search_trend"] = TREND_OPTIONS[0]
                trend = st.selectbox("Trending Topic", options=TREND_OPTIONS, key="search_trend")
                keyword = trend

            period_default_index = PERIOD_OPTIONS.index("1d")
            period = st.selectbox(
                "Time Interval",
                options=PERIOD_OPTIONS,
                index=period_default_index,
                key="search_period",
            )
            st.caption("All matching articles in the selected interval will be processed.")
            if mode == "Trend":
                st.caption("Trend mode treats the selected topic as a keyword and keeps building a saved history.")

            with st.expander("Advanced Settings", expanded=False):
                st.caption("Use these options if you want deeper analysis for each article.")
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
                    st.info("The UI does not cap results. Provider limits are handled automatically.")

            submitted = st.button("Run analysis", type="primary", width="stretch", key="search_submit")

            if not submitted:
                return

            request = SearchRequest(
                mode="trend" if mode == "Trend" else "keyword",
                keyword=keyword.strip(),
                topic=trend.strip().upper(),
                period=period,
                max_results=1000,
                extract_full_text=extract_full_text,
                include_entities=include_entities,
                use_mock_nlp=False,
                fallback_to_mock_on_error=False,
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

        st.title("Search Analysis")
        st.caption("These results reflect the latest saved records for this search.")
        st.caption("All timestamps are shown in Europe/Zurich.")

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
            text=f"{loaded_articles}/{total_articles} saved article(s) are available for the selected {period_label} window.",
        )

        status_message = st.session_state.get("news_search_message", "Search completed.")
        if st.session_state.get("news_search_ok", True):
            st.success(status_message)
        else:
            st.warning(status_message)

        st.divider()
        metric_cols = st.columns(6)
        metric_cols[0].metric("Fetched", str(articles_found))
        metric_cols[1].metric("Already Saved", str(existing_articles))
        metric_cols[2].metric("New", str(new_articles))
        metric_cols[3].metric("Analyzed", str(analyzed_articles))
        metric_cols[4].metric("Saved", str(saved_articles))
        metric_cols[5].metric("Loaded", str(loaded_articles))

        st.info("New articles are saved automatically before the results view is refreshed.")

        if warnings:
            with st.expander(f"Processing notes ({len(warnings)})"):
                for warning in warnings:
                    st.write(f"- {warning}")
        if errors:
            with st.expander(f"Issues ({len(errors)})"):
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

        sentiment_distribution = insights.sentiment.as_distribution_rows()
        st.markdown("#### Sentiment Distribution")
        pie_values = sentiment_distribution
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
        st.markdown("#### Sentiment Over Time")
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
                use_container_width=True,
            )
        else:
            st.info("No trend data available (published date/time missing).")

        st.divider()
        st.markdown("#### Top Extracted Entities")
        top_entity_rows = [{"entity": item.label, "count": item.count} for item in insights.top_entities]
        if top_entity_rows:
            chart_rows = [{"Entity": item["entity"], "Count": item["count"]} for item in top_entity_rows]
            st.bar_chart(chart_rows, x="Entity", y="Count", horizontal=True)
        else:
            st.info("No entities extracted.")

        st.divider()
        st.markdown("#### Results Table")
        filtered_rows = self._render_table_filters_and_data(records)
        st.caption(f"Showing: {len(filtered_rows)} / {len(records)} rows")

        st.divider()
        st.markdown("#### Export")
        export_sections = self._build_export_sections(
            request=request,
            summary=summary,
            records=records,
            filtered_rows=filtered_rows,
            sentiment_distribution=sentiment_distribution,
            top_entities=top_entity_rows,
            trend_rows=trend_rows,
        )
        self._render_export_actions(
            sections=export_sections,
            file_stem=self._build_export_file_stem(request=request),
        )

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

    def _render_export_actions(self, sections: dict[str, list[dict[str, Any]]], file_stem: str) -> None:
        csv_zip_bytes = self._build_csv_zip_bytes(sections)
        json_bytes = json.dumps(sections, ensure_ascii=True, indent=2).encode("utf-8")
        excel_bytes, excel_error = self._build_excel_bytes(sections)

        col_csv, col_json, col_excel = st.columns(3)
        with col_csv:
            st.download_button(
                "CSV Export (ZIP)",
                data=csv_zip_bytes,
                file_name=f"{file_stem}_tables.zip",
                mime="application/zip",
            )
        with col_json:
            st.download_button(
                "JSON Export",
                data=json_bytes,
                file_name=f"{file_stem}_tables.json",
                mime="application/json",
            )
        with col_excel:
            st.download_button(
                "Excel Export",
                data=excel_bytes or b"",
                file_name=f"{file_stem}_tables.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                disabled=excel_bytes is None,
            )
        if excel_error:
            st.caption(excel_error)

    def _build_csv_zip_bytes(self, sections: dict[str, list[dict[str, Any]]]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, rows in sections.items():
                csv_text = self._rows_to_csv_text(rows)
                archive.writestr(f"{name}.csv", csv_text)
        return buffer.getvalue()

    def _rows_to_csv_text(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""

        fieldnames: list[str] = list(rows[0].keys())
        for row in rows[1:]:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: self._to_export_cell(row.get(key)) for key in fieldnames})
        return output.getvalue()

    def _build_excel_bytes(self, sections: dict[str, list[dict[str, Any]]]) -> tuple[bytes | None, str | None]:
        try:
            import pandas as pd  # type: ignore[import-not-found]
        except ImportError:
            return None, "Excel export disabled: install pandas + openpyxl."

        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                for name, rows in sections.items():
                    dataframe = pd.DataFrame(rows)
                    if dataframe.empty:
                        dataframe = pd.DataFrame([{}])
                    dataframe.to_excel(writer, sheet_name=name[:31], index=False)
        except Exception as exc:  # noqa: BLE001
            return None, f"Excel export failed: {exc}"
        return buffer.getvalue(), None

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
            export_row[str(key)] = self._to_export_cell(value)
        export_row["entities_display"] = entities_to_display(row.get("entities", []))
        export_row["trend"] = self._trend_from_record(row)
        date_value, time_value = format_swiss_date_time(
            str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
        )
        export_row["date"] = date_value
        export_row["time"] = time_value
        return export_row

    def _build_export_file_stem(self, request: dict[str, Any]) -> str:
        query = str(request.get("keyword", "")).strip() or str(request.get("topic", "")).strip()
        clean_query = "".join(ch if ch.isalnum() else "_" for ch in query)[:40].strip("_")
        if not clean_query:
            clean_query = "query"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"news_analysis_{clean_query}_{timestamp}"

    @staticmethod
    def _trend_from_record(row: dict[str, Any]) -> str:
        query = str(row.get("query", "")).strip()
        if query:
            return query
        return str(row.get("topic", "")).strip()

    @staticmethod
    def _to_export_cell(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        return value

    def _show_loading_screen(self, request: SearchRequest):
        progress_placeholder = st.empty()
        caption_placeholder = st.empty()
        progress = progress_placeholder.progress(0.0, text="Starting analysis...")
        caption_placeholder.caption("This can take a little longer for larger time windows.")

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
            text=(
                "Analysis complete. "
                f"{len(records)} of {final_total} saved article(s) are ready."
            ),
        )
        progress_placeholder.empty()
        caption_placeholder.empty()
        return response

    @staticmethod
    def _build_progress_message(update: PipelineProgress, processed: int, total: int) -> str:
        """Return a short, user-friendly progress label for the loading bar."""
        phase_messages = {
            "collect": "Collecting articles...",
            "check_existing": "Checking which articles are already saved...",
            "analyze": f"Analyzing articles ({processed}/{total})...",
            "persist": "Saving new articles...",
            "reload": "Refreshing the saved results...",
            "done": "Analysis complete.",
        }
        return phase_messages.get(update.phase, "Processing...")

    def _build_progress_ratio(self, phase: str, processed: int, total: int) -> float:
        if phase == "done":
            return 1.0

        try:
            phase_index = self._PROGRESS_PHASES.index(phase)
        except ValueError:
            phase_index = 0

        phase_ratio = processed / max(total, 1)
        return min(((phase_index + phase_ratio) / max(len(self._PROGRESS_PHASES), 1)), 0.99)
