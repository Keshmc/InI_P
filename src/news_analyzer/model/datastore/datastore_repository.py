"""Firestore (Datastore-mode) persistence and query module for analyzed news records."""

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

try:
    from google.cloud import datastore
except Exception:  # noqa: BLE001
    datastore = None  # type: ignore[assignment]

SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "technology": (
        "technology",
        "tech",
        "software",
        "semiconductor",
        "semiconductors",
        "chip",
        "chips",
        "artificial intelligence",
        "cloud computing",
        "cybersecurity",
    ),
    "energy": (
        "energy",
        "oil",
        "gas",
        "lng",
        "renewable",
        "renewables",
        "solar",
        "wind power",
        "utilities",
    ),
    "healthcare": (
        "healthcare",
        "health care",
        "biotech",
        "biotechnology",
        "pharma",
        "pharmaceutical",
        "pharmaceuticals",
        "medical device",
        "hospital",
    ),
    "financials": (
        "financials",
        "financial",
        "bank",
        "banking",
        "insurance",
        "asset management",
        "fintech",
        "investment",
    ),
    "industrials": (
        "industrials",
        "industrial",
        "manufacturing",
        "aerospace",
        "defense",
        "transportation",
        "logistics",
        "construction",
    ),
    "consumer": (
        "consumer",
        "retail",
        "e-commerce",
        "ecommerce",
        "apparel",
        "luxury",
        "food",
        "beverage",
        "automotive",
    ),
    "communication services": (
        "communication services",
        "media",
        "telecom",
        "telecommunications",
        "streaming",
        "advertising",
        "social media",
    ),
    "materials": (
        "materials",
        "mining",
        "metals",
        "chemicals",
        "steel",
        "copper",
        "gold",
        "lithium",
    ),
    "real estate": (
        "real estate",
        "reit",
        "property",
        "commercial real estate",
        "housing",
    ),
    "utilities": (
        "utilities",
        "power grid",
        "electric utility",
        "water utility",
    ),
}


@dataclass
class FirestoreConfig:
    """Configuration for Firestore Datastore-mode connection."""

    project_id: str = ""
    collection: str = ""
    kind: str = "AnalyzedArticle"  # Backward-compat alias.
    credentials_path: str | None = None
    database_id: str | None = None


@dataclass
class FirestoreQuery:
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
    urls: list[str] | None = None
    limit: int = 500


class FirestoreRepository:
    """Store and query records in Firestore Datastore mode using Datastore client."""

    def __init__(self, config: FirestoreConfig) -> None:
        self.config = config
        self.client: Any | None = None
        self.init_error: str | None = None
        self.last_error: str | None = None
        self.database_id = (config.database_id or "").strip() or "(default)"
        self.credentials_path_resolved: str | None = None
        self.collection_name = (
            str(config.collection).strip() or str(config.kind).strip() or "AnalyzedArticle"
        )

        if datastore is None:
            self.init_error = (
                "google-cloud-datastore package is not installed. "
                "Install it to enable Firestore Datastore-mode storage."
            )
            return

        credentials_path = self._resolve_credentials_path(config.credentials_path)
        self.credentials_path_resolved = credentials_path
        if credentials_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        try:
            database = None if self.database_id == "(default)" else self.database_id
            project = str(config.project_id).strip() or None

            if project:
                try:
                    self.client = datastore.Client(project=project, database=database)
                except TypeError:
                    self.client = datastore.Client(project=project)
            else:
                try:
                    self.client = datastore.Client(database=database)
                except TypeError:
                    self.client = datastore.Client()
        except DefaultCredentialsError as exc:
            self.init_error = f"Datastore credentials missing/invalid: {exc}"
        except Exception as exc:  # noqa: BLE001
            self.init_error = f"Datastore init failed: {exc}"

    @property
    def is_available(self) -> bool:
        """Return True if Datastore client is initialized."""
        return self.client is not None

    def get_existing_urls(self, urls: list[str]) -> set[str]:
        """Return the subset of URLs that already exist."""
        if not self.is_available:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return set()

        clean_urls = [str(url).strip() for url in urls if str(url).strip()]
        if not clean_urls:
            self.last_error = None
            return set()

        keys = [self._build_key_from_url(url) for url in clean_urls]
        id_to_url = {key.name: url for key, url in zip(keys, clean_urls, strict=False)}
        try:
            entities = self.client.get_multi(keys)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Datastore read failed: {exc}"
            return set()

        existing: set[str] = set()
        for entity in entities:
            if not entity:
                continue
            payload_url = str(entity.get("url", "")).strip()
            if payload_url:
                existing.add(payload_url)
                continue
            if entity.key and entity.key.name:
                mapped = id_to_url.get(entity.key.name)
                if mapped:
                    existing.add(mapped)

        self.last_error = None
        return existing

    def load_records_for_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        """Load stored records for a list of URLs, sorted by published datetime."""
        if not self.is_available:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return []

        clean_urls = [str(url).strip() for url in urls if str(url).strip()]
        if not clean_urls:
            self.last_error = None
            return []

        keys = [self._build_key_from_url(url) for url in dict.fromkeys(clean_urls)]
        try:
            entities = self.client.get_multi(keys)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Datastore read failed: {exc}"
            return []

        rows: list[dict[str, Any]] = []
        for entity in entities:
            if not entity:
                continue
            rows.append(self._normalize_row(dict(entity)))

        self.last_error = None
        rows.sort(key=self._sort_key, reverse=True)
        return rows

    def save_record(self, record: dict[str, Any]) -> bool:
        """Upsert one analyzed article record."""
        if not self.is_available:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return False

        url = str(record.get("url", "")).strip()
        if not url:
            self.last_error = "Record has no URL."
            return False

        key = self._build_key_from_url(url)
        entity = datastore.Entity(
            key=key,
            exclude_from_indexes=(
                "article_text",
                "description",
                "entities_json",
                "raw_article_json",
                "analysis_error",
                "extraction_error",
            ),
        )

        entities = self._normalize_entities(record.get("entities", []))
        raw_article = record.get("raw_article", {})
        if not isinstance(raw_article, dict):
            raw_article = {}

        entity.update(
            {
                "document_id": key.name or "",
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
                "raw_article_json": json.dumps(raw_article, ensure_ascii=True, sort_keys=True),
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

    def get_latest_ingested_at(self) -> str:
        """Return the most recent `ingested_at` ISO string across all records, or ''.

        Used by the UI to derive the collector's "last run" from persisted records
        instead of in-process scheduler state — in production the Cloud Run Job
        writes to Firestore from a different process, so the webapp's in-memory
        `last_run_at` is always empty.
        """
        if not self.is_available:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return ""

        query = self.client.query(kind=self.collection_name)
        try:
            query.order = ["-ingested_at"]
            rows = list(query.fetch(limit=1))
        except Exception as exc:  # noqa: BLE001
            # Index missing or other ordering failure — fall back to a small scan.
            try:
                fallback_query = self.client.query(kind=self.collection_name)
                rows = list(fallback_query.fetch(limit=200))
            except Exception as fallback_exc:  # noqa: BLE001
                self.last_error = f"Latest-ingested lookup failed: {fallback_exc} (initial: {exc})"
                return ""

        latest = ""
        latest_dt: datetime | None = None
        for entity in rows:
            raw = str(dict(entity).get("ingested_at", "")).strip()
            parsed = self._parse_datetime(raw)
            if parsed is None:
                continue
            if latest_dt is None or parsed > latest_dt:
                latest_dt = parsed
                latest = raw

        self.last_error = None
        return latest

    def query_records(self, query_filter: FirestoreQuery | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        """Query stored records with filter support."""
        if not self.is_available:
            self.last_error = self.init_error or "Datastore client is not initialized."
            return []

        filters = query_filter or FirestoreQuery(**kwargs)
        fetch_limit = max(1, int(filters.limit))
        scan_limit = max(fetch_limit, 10000)

        query = self.client.query(kind=self.collection_name)
        try:
            rows = [self._normalize_row(dict(item)) for item in query.fetch(limit=scan_limit)]
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Datastore query failed: {exc}"
            return []

        filtered = [row for row in rows if self._matches_filters(row, filters)]
        filtered.sort(key=self._sort_key, reverse=True)
        self.last_error = None
        return filtered[:fetch_limit]

    def _build_key_from_url(self, url: str) -> Any:
        return self.client.key(self.collection_name, self._build_document_id_from_url(url))

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
    def _build_document_id_from_url(url: str) -> str:
        clean_url = str(url).strip()
        return hashlib.sha1(clean_url.encode("utf-8")).hexdigest()

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)

        try:
            normalized["entities"] = json.loads(normalized.get("entities_json", "[]"))
        except (TypeError, json.JSONDecodeError):
            normalized["entities"] = []

        if "article_text" not in normalized:
            normalized["article_text"] = normalized.get("full_text", "")
        if "raw_article_json" not in normalized:
            normalized["raw_article_json"] = "{}"
        return normalized

    def _matches_filters(self, row: dict[str, Any], filters: FirestoreQuery) -> bool:
        if filters.urls:
            url_set = {str(url).strip() for url in filters.urls if str(url).strip()}
            if url_set and str(row.get("url", "")).strip() not in url_set:
                return False

        company_tokens = []
        if filters.company_keyword:
            company_tokens.append(filters.company_keyword.strip().lower())
        if filters.company_keywords:
            company_tokens.extend([token.strip().lower() for token in filters.company_keywords if token.strip()])

        if company_tokens and not any(self._record_contains_text(row, token) for token in company_tokens):
            return False

        sector_token = (filters.industry_sector or "").strip().lower()
        if sector_token and not self._record_matches_sector(row, sector_token):
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

    @classmethod
    def _record_matches_sector(cls, row: dict[str, Any], requested_sector: str) -> bool:
        """Match a record against a canonical sector using stored or inferred labels."""
        normalized_requested = cls._normalize_sector_label(requested_sector)
        if not normalized_requested:
            return True

        stored_sector = cls._normalize_sector_label(str(row.get("industry_sector", "")).strip())
        if stored_sector:
            return stored_sector == normalized_requested

        inferred_sector = cls._infer_sector_from_record(row)
        return inferred_sector == normalized_requested

    @classmethod
    def _infer_sector_from_record(cls, row: dict[str, Any]) -> str:
        """Infer a sector from targeted metadata fields when no stored sector exists."""
        search_texts: list[str] = [
            str(row.get("company_keyword", "")).lower(),
            str(row.get("query", "")).lower(),
            str(row.get("title", "")).lower(),
            str(row.get("description", "")).lower(),
        ]

        entities = row.get("entities", [])
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            search_texts.append(str(entity.get("name", "")).lower())

        combined_text = " ".join(part for part in search_texts if part).strip()
        if not combined_text:
            return ""

        for canonical, aliases in SECTOR_ALIASES.items():
            if any(alias in combined_text for alias in aliases):
                return canonical
        return ""

    @staticmethod
    def _normalize_sector_label(value: str) -> str:
        normalized = str(value).strip().lower()
        if not normalized:
            return ""

        for canonical, aliases in SECTOR_ALIASES.items():
            if normalized == canonical or normalized in aliases:
                return canonical
        return normalized

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


# Backward-compatible aliases for existing imports.
DatastoreConfig = FirestoreConfig
DatastoreQuery = FirestoreQuery
DatastoreRepository = FirestoreRepository
