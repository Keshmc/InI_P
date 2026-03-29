"""Presenter layer: bridges view inputs and model pipeline outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from news_analyzer.model.datastore import DatastoreQuery, DatastoreRepository
from news_analyzer.model.model import NewsAnalysisPipeline, SearchRequest, SearchResult


@dataclass
class PresenterResponse:
    """Generic response object returned to view code."""

    ok: bool
    message: str
    payload: dict[str, Any]


class NewsPresenter:
    """Coordinates data flow from view to model and back."""

    def __init__(self, pipeline: NewsAnalysisPipeline, datastore_repository: DatastoreRepository | None = None) -> None:
        self.pipeline = pipeline
        self.datastore_repository = datastore_repository or pipeline.datastore_repository
        self.last_search_result: SearchResult | None = None

    def run_startup_check(self) -> PresenterResponse:
        """Run startup checks for RSS, credentials, and datastore access."""
        checks: list[dict[str, str]] = []

        rss_loader = self.pipeline.rss_loader
        try:
            preview = rss_loader.search_by_topic(topic="BUSINESS", period="1d", max_results=1)
            if rss_loader.last_error:
                checks.append({"name": "RSS Feed", "status": "error", "message": rss_loader.last_error})
            elif preview:
                checks.append({"name": "RSS Feed", "status": "ok", "message": f"Connected ({len(preview)} article preview)."})
            else:
                checks.append(
                    {"name": "RSS Feed", "status": "warn", "message": "Connection works, but no preview article returned."}
                )
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "RSS Feed", "status": "error", "message": f"RSS check failed: {exc}"})

        if self.datastore_repository is None:
            checks.append({"name": "Datastore Client", "status": "error", "message": "Datastore repository not configured."})
            overall_ok = False
        else:
            if self.datastore_repository.is_available:
                checks.append(
                    {
                        "name": "Datastore Client",
                        "status": "ok",
                        "message": (
                            f"Client initialized (project={self.datastore_repository.config.project_id or 'default'}, "
                            f"database={self.datastore_repository.database_id}, kind={self.datastore_repository.config.kind})."
                        ),
                    }
                )
            else:
                checks.append(
                    {
                        "name": "Datastore Client",
                        "status": "error",
                        "message": self.datastore_repository.init_error or "Datastore client could not be initialized.",
                    }
                )

            credentials = self.datastore_repository.credentials_path_resolved
            if not credentials:
                env_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
                if env_credentials:
                    credentials = env_credentials

            if credentials:
                if Path(credentials).exists():
                    checks.append({"name": "Credentials Path", "status": "ok", "message": credentials})
                else:
                    checks.append(
                        {
                            "name": "Credentials Path",
                            "status": "error",
                            "message": f"Credentials file not found: {credentials}",
                        }
                    )
                    credentials = ""
            else:
                checks.append(
                    {
                        "name": "Credentials Path",
                        "status": "warn",
                        "message": "No explicit credentials_path configured, relying on environment/default credentials.",
                    }
                )

            if not credentials and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""):
                checks.append(
                    {
                        "name": "Credentials Hint",
                        "status": "warn",
                        "message": "Set GOOGLE_APPLICATION_CREDENTIALS or datastore.credentials_path for deterministic startup.",
                    }
                )

            if self.datastore_repository.is_available:
                self.datastore_repository.query_records(DatastoreQuery(limit=1))
                if self.datastore_repository.last_error:
                    checks.append(
                        {
                            "name": "Datastore Access",
                            "status": "error",
                            "message": self.datastore_repository.last_error,
                        }
                    )
                else:
                    checks.append(
                        {
                            "name": "Datastore Access",
                            "status": "ok",
                            "message": "Read access test succeeded.",
                        }
                    )

            overall_ok = not any(item["status"] == "error" for item in checks)

        payload = {
            "overall_ok": overall_ok,
            "checks": checks,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if overall_ok:
            message = "Startup check passed."
            return PresenterResponse(ok=True, message=message, payload=payload)

        message = "Startup check found issues."
        return PresenterResponse(ok=False, message=message, payload=payload)

    @staticmethod
    def build_search_request(view_data: dict[str, Any]) -> SearchRequest:
        """Create validated SearchRequest from raw view data."""
        mode = str(view_data.get("mode", "keyword")).strip().lower()
        keyword = str(view_data.get("keyword", "")).strip()
        topic = str(view_data.get("topic", "")).strip().upper()
        period = str(view_data.get("period", "1d")).strip().lower()
        max_results = int(view_data.get("max_results", 10))

        if mode == "keyword" and not keyword:
            raise ValueError("Keyword mode requires a non-empty keyword.")
        if mode == "topic" and not topic:
            raise ValueError("Topic mode requires a non-empty topic.")

        return SearchRequest(
            mode=mode,
            keyword=keyword,
            topic=topic,
            period=period,
            max_results=max_results,
            extract_full_text=bool(view_data.get("extract_full_text", False)),
            include_entities=bool(view_data.get("include_entities", True)),
            use_mock_nlp=bool(view_data.get("use_mock_nlp", False)),
            fallback_to_mock_on_error=bool(view_data.get("fallback_to_mock_on_error", True)),
            sentiment_max_chars=int(view_data.get("sentiment_max_chars", 4000)),
            entity_max_chars=int(view_data.get("entity_max_chars", 4000)),
            entity_max_items=int(view_data.get("entity_max_items", 30)),
            store_to_datastore=bool(view_data.get("store_to_datastore", False)),
            industry_sector=str(view_data.get("industry_sector", "")).strip(),
        )

    def run_news_search(self, request: SearchRequest) -> PresenterResponse:
        """Execute search pipeline and prepare view-friendly payload."""
        result = self.pipeline.run_search(request)
        self.last_search_result = result

        payload = {
            "request": asdict(result.request),
            "summary": asdict(result.summary),
            "records": result.records,
            "warnings": result.warnings,
            "errors": result.errors,
        }

        if result.errors:
            return PresenterResponse(
                ok=False,
                message=f"Search finished with {len(result.errors)} error(s).",
                payload=payload,
            )

        message = f"Search finished. {result.summary.articles_found} article(s) analyzed."
        if result.warnings:
            message += f" {len(result.warnings)} warning(s)."
        return PresenterResponse(ok=True, message=message, payload=payload)

    def store_last_search_to_datastore(self) -> PresenterResponse:
        """Persist latest analyzed records to Datastore."""
        if self.last_search_result is None:
            return PresenterResponse(
                ok=False,
                message="No search result available to store.",
                payload={"saved_count": 0},
            )

        if self.datastore_repository is None or not self.datastore_repository.is_available:
            return PresenterResponse(
                ok=False,
                message="Datastore is not available.",
                payload={"saved_count": 0},
            )

        saved_count = self.datastore_repository.save_records(self.last_search_result.records)
        total = len(self.last_search_result.records)
        if saved_count < total:
            detail = self.datastore_repository.last_error or "Unknown datastore write issue."
            return PresenterResponse(
                ok=False,
                message=f"Stored {saved_count}/{total} record(s). Last error: {detail}",
                payload={"saved_count": saved_count, "total_count": total, "error": detail},
            )
        return PresenterResponse(
            ok=True,
            message=f"Stored {saved_count} record(s) in Datastore.",
            payload={"saved_count": saved_count},
        )

    def query_datastore(self, query: DatastoreQuery) -> PresenterResponse:
        """Query Datastore with filters and return records + summary."""
        if self.datastore_repository is None or not self.datastore_repository.is_available:
            return PresenterResponse(
                ok=False,
                message="Datastore is not available.",
                payload={"records": [], "count": 0},
            )

        records = self.datastore_repository.query_records(query_filter=query)
        if self.datastore_repository.last_error:
            return PresenterResponse(
                ok=False,
                message=f"Datastore query failed: {self.datastore_repository.last_error}",
                payload={"records": [], "count": 0, "error": self.datastore_repository.last_error},
            )

        avg_score = 0.0
        avg_magnitude = 0.0
        if records:
            avg_score = round(sum(float(item.get("sentiment_score", 0.0)) for item in records) / len(records), 4)
            avg_magnitude = round(
                sum(float(item.get("sentiment_magnitude", 0.0)) for item in records) / len(records),
                4,
            )

        payload = {
            "records": records,
            "count": len(records),
            "avg_sentiment_score": avg_score,
            "avg_sentiment_magnitude": avg_magnitude,
        }
        return PresenterResponse(
            ok=True,
            message=f"Loaded {len(records)} record(s) from Datastore.",
            payload=payload,
        )
