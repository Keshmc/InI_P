"""Datastore persistence and query module for analyzed news records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import datastore
from google.cloud.datastore.query import PropertyFilter


@dataclass
class DatastoreConfig:
    """Configuration for Datastore connection."""

    project_id: str = ""
    kind: str = "AnalyzedArticle"
    credentials_path: str | None = None
    database_id: str | None = None


@dataclass
class DatastoreQuery:
    """Query filters for stored analyzed articles."""

    company_keyword: str | None = None
    company_keywords: list[str] | None = None
    industry_sector: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_sentiment: float | None = None
    max_sentiment: float | None = None
    entity_type: str | None = None
    source_contains: str | None = None
    topic: str | None = None
    limit: int = 500


class DatastoreRepository:
    """Store and query analyzed article records in Google Datastore."""

    def __init__(self, config: DatastoreConfig) -> None:
        self.config = config
        self.client: datastore.Client | None = None
        self.init_error: str | None = None
        self.last_error: str | None = None
        self.database_id = (config.database_id or "").strip() or "(default)"
        self.credentials_path_resolved: str | None = None

        credentials_path = self._resolve_credentials_path(config.credentials_path)
        self.credentials_path_resolved = credentials_path
        if credentials_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        try:
            database = None if self.database_id == "(default)" else self.database_id
            if config.project_id:
                self.client = datastore.Client(project=config.project_id, database=database)
            else:
                self.client = datastore.Client(database=database)
        except DefaultCredentialsError as exc:
            self.init_error = f"Datastore credentials missing/invalid: {exc}"
        except Exception as exc:  # noqa: BLE001
            self.init_error = f"Datastore init failed: {exc}"

    @property
    def is_available(self) -> bool:
        """Return True if Datastore client is initialized."""
        return self.client is not None

    def save_record(self, record: dict[str, Any]) -> bool:
        """Upsert one analyzed article record."""
        if self.client is None:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return False

        url = str(record.get("url", "")).strip()
        if not url:
            self.last_error = "Record has no URL."
            return False

        key_name = self._build_key_name(record)
        key = self.client.key(self.config.kind, key_name)
        entity = datastore.Entity(
            key=key,
            exclude_from_indexes=("article_text", "description", "entities_json", "analysis_error", "extraction_error"),
        )

        entities = self._normalize_entities(record.get("entities", []))
        entity.update(
            {
                "symbol": str(record.get("symbol", "")).strip().upper(),
                "company_keyword": str(record.get("company_keyword", record.get("query", ""))).strip(),
                "query": str(record.get("query", "")).strip(),
                "search_mode": str(record.get("search_mode", "keyword")).strip().lower(),
                "industry_sector": str(record.get("industry_sector", "")).strip(),
                "topic": str(record.get("topic", "")).strip().upper(),
                "period": str(record.get("period", "")).strip().lower(),
                "title": str(record.get("title", "")).strip(),
                "description": str(record.get("description", "")).strip(),
                "source": str(record.get("source", "")).strip(),
                "url": url,
                "published_date": str(record.get("published_date", "")).strip(),
                "published_at": str(record.get("published_at", "")).strip(),
                "article_text": str(record.get("article_text", record.get("full_text", ""))).strip(),
                "sentiment_score": float(record.get("sentiment_score", 0.0)),
                "sentiment_magnitude": float(record.get("sentiment_magnitude", 0.0)),
                "entities_json": json.dumps(entities, ensure_ascii=True),
                "analysis_error": str(record.get("analysis_error", "")).strip(),
                "extraction_error": str(record.get("extraction_error", "")).strip(),
                "status": str(record.get("status", "success")).strip().lower(),
                "analysis_timestamp": str(record.get("analysis_timestamp", "")).strip(),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        try:
            self.client.put(entity)
            self.last_error = None
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Datastore write failed: {exc}"
            return False

    def save_records(self, records: list[dict[str, Any]]) -> int:
        """Store multiple records and return number of successful writes."""
        saved = 0
        for record in records:
            if self.save_record(record):
                saved += 1
        return saved

    def query_records(self, query_filter: DatastoreQuery | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        """Query stored records with filter support."""
        if self.client is None:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return []

        filters = query_filter or DatastoreQuery(**kwargs)
        fetch_limit = max(1, int(filters.limit))

        query = self.client.query(kind=self.config.kind)
        if filters.company_keyword:
            keyword = filters.company_keyword.strip()
            if keyword and keyword.upper() == keyword and len(keyword) <= 6 and " " not in keyword:
                query.add_filter(filter=PropertyFilter("symbol", "=", keyword.upper()))

        try:
            rows = [dict(item) for item in query.fetch(limit=fetch_limit)]
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Datastore query failed: {exc}"
            return []

        self.last_error = None
        normalized = [self._normalize_row(row) for row in rows]
        filtered = [row for row in normalized if self._matches_filters(row, filters)]
        filtered.sort(key=self._sort_key, reverse=True)
        return filtered

    @staticmethod
    def _resolve_credentials_path(raw_path: str | None) -> str | None:
        if not raw_path:
            return None

        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return str(candidate) if candidate.exists() else None

    @staticmethod
    def _normalize_entities(raw_entities: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_entities, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw_entities:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "name": str(item.get("name", "")).strip(),
                        "entity_type": str(item.get("entity_type", "")).strip().upper(),
                        "salience": float(item.get("salience", 0.0)),
                    }
                )
            elif hasattr(item, "name") and hasattr(item, "entity_type"):
                normalized.append(
                    {
                        "name": str(getattr(item, "name", "")).strip(),
                        "entity_type": str(getattr(item, "entity_type", "")).strip().upper(),
                        "salience": float(getattr(item, "salience", 0.0)),
                    }
                )
        return normalized

    @staticmethod
    def _build_key_name(record: dict[str, Any]) -> str:
        symbol = str(record.get("symbol", record.get("query", ""))).strip().upper()
        url = str(record.get("url", "")).strip()
        return hashlib.sha1(f"{symbol}|{url}".encode("utf-8")).hexdigest()

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)

        try:
            normalized["entities"] = json.loads(normalized.get("entities_json", "[]"))
        except (TypeError, json.JSONDecodeError):
            normalized["entities"] = []

        if "article_text" not in normalized:
            normalized["article_text"] = normalized.get("full_text", "")
        return normalized

    def _matches_filters(self, row: dict[str, Any], filters: DatastoreQuery) -> bool:
        company_tokens = []
        if filters.company_keyword:
            company_tokens.append(filters.company_keyword.strip().lower())
        if filters.company_keywords:
            company_tokens.extend([token.strip().lower() for token in filters.company_keywords if token.strip()])

        if company_tokens and not any(self._record_contains_text(row, token) for token in company_tokens):
            return False

        sector_token = (filters.industry_sector or "").strip().lower()
        if sector_token and not self._record_contains_text(row, sector_token):
            return False

        source_token = (filters.source_contains or "").strip().lower()
        if source_token and source_token not in str(row.get("source", "")).lower():
            return False

        topic_token = (filters.topic or "").strip().upper()
        if topic_token and topic_token != str(row.get("topic", "")).upper():
            return False

        entity_type_token = (filters.entity_type or "").strip().upper()
        if entity_type_token:
            entities = row.get("entities", [])
            has_entity_type = any(
                str(item.get("entity_type", "")).upper() == entity_type_token for item in entities if isinstance(item, dict)
            )
            if not has_entity_type:
                return False

        score = float(row.get("sentiment_score", 0.0))
        if filters.min_sentiment is not None and score < filters.min_sentiment:
            return False
        if filters.max_sentiment is not None and score > filters.max_sentiment:
            return False

        published_dt = self._parse_published_datetime(row)
        dt_from = self._parse_datetime(filters.date_from)
        dt_to = self._parse_datetime(filters.date_to)
        if dt_from and (published_dt is None or published_dt < dt_from):
            return False
        if dt_to and (published_dt is None or published_dt > dt_to):
            return False

        return True

    @staticmethod
    def _record_contains_text(row: dict[str, Any], token: str) -> bool:
        if not token:
            return True

        searchable = [
            str(row.get("symbol", "")).lower(),
            str(row.get("company_keyword", "")).lower(),
            str(row.get("query", "")).lower(),
            str(row.get("industry_sector", "")).lower(),
            str(row.get("topic", "")).lower(),
            str(row.get("title", "")).lower(),
            str(row.get("description", "")).lower(),
            str(row.get("article_text", "")).lower(),
            str(row.get("source", "")).lower(),
        ]
        if any(token in value for value in searchable):
            return True

        entities = row.get("entities", [])
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name", "")).lower()
            entity_type = str(entity.get("entity_type", "")).lower()
            if token in name or token in entity_type:
                return True
        return False

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = date_parser.parse(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    def _parse_published_datetime(cls, row: dict[str, Any]) -> datetime | None:
        return cls._parse_datetime(row.get("published_at")) or cls._parse_datetime(row.get("published_date"))

    @classmethod
    def _sort_key(cls, row: dict[str, Any]) -> datetime:
        return (
            cls._parse_published_datetime(row)
            or cls._parse_datetime(row.get("analysis_timestamp"))
            or cls._parse_datetime(row.get("ingested_at"))
            or datetime.min.replace(tzinfo=timezone.utc)
        )
