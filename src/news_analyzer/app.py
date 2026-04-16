"""Single application entrypoint: wires model, presenter, and view."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_analyzer.model import (
    DatastoreConfig,
    DatastoreRepository,
    NewsAnalysisPipeline,
    RssArticleExtractor,
    RssFeedLoader,
)
from news_analyzer.presenter import NewsPresenter
from news_analyzer.view import run_view

DEFAULT_CONFIG_PATH = ROOT / "config.yaml"


def _is_cloud_run() -> bool:
    """Return True when the app is running inside Cloud Run."""
    return any(os.getenv(name) for name in ("K_SERVICE", "K_REVISION", "K_CONFIGURATION"))


def _resolve_path(path_value: str | None) -> Path | None:
    """Resolve a config/env path into an existing absolute file path."""
    if not path_value:
        return None

    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT / candidate

    if candidate.exists():
        return candidate.resolve()
    return None


def _discover_secret_credentials_path() -> Path | None:
    """Auto-discover a service account JSON in ROOT/secrets."""
    secrets_dir = ROOT / "secrets"
    if not secrets_dir.exists():
        return None

    json_files = sorted(
        [item for item in secrets_dir.glob("*.json") if item.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not json_files:
        return None

    return json_files[0].resolve()


def _bootstrap_credentials(datastore_payload: dict[str, Any]) -> str | None:
    """Set GOOGLE_APPLICATION_CREDENTIALS using env/config/secrets fallback order."""
    env_candidate = _resolve_path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
    if env_candidate is not None:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(env_candidate)
        return str(env_candidate)

    if _is_cloud_run():
        return None

    raw_config_path = datastore_payload.get("credentials_path")
    config_candidate = _resolve_path(str(raw_config_path).strip())
    if config_candidate is not None:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(config_candidate)
        return str(config_candidate)

    secret_candidate = _discover_secret_credentials_path()
    if secret_candidate is not None:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(secret_candidate)
        return str(secret_candidate)

    return None


def build_presenter(config_path: Path | None = None) -> NewsPresenter:
    """Build and return a fully-wired presenter instance."""
    path = config_path or DEFAULT_CONFIG_PATH
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}

    rss = payload.get("rss", {}) if isinstance(payload, dict) else {}
    extractor = payload.get("extractor", {}) if isinstance(payload, dict) else {}

    raw_datastore_payload: Any = {}
    if isinstance(payload, dict):
        raw_datastore_payload = payload.get("datastore", payload.get("gcp", {}))
    datastore_payload = raw_datastore_payload if isinstance(raw_datastore_payload, dict) else {}

    credentials_path = _bootstrap_credentials(datastore_payload)

    rss_loader = RssFeedLoader(
        language=str(rss.get("language", "en")),
        country=str(rss.get("country", "US")),
        default_period=str(rss.get("period", "1d")),
        default_max_results=int(rss.get("max_results", 25)),
    )
    article_extractor = RssArticleExtractor(
        timeout_seconds=int(extractor.get("request_timeout_seconds", 8)),
        max_chars=int(extractor.get("max_chars", 15000)),
    )

    datastore_repo = DatastoreRepository(
        DatastoreConfig(
            project_id=str(datastore_payload.get("project_id")), 
            kind=str(datastore_payload.get("kind", datastore_payload.get("datastore_kind", "AnalyzedArticle"))),
            credentials_path=credentials_path,
            database_id=str(datastore_payload.get("database_id", "")).strip() or None,
        )
    )

    pipeline = NewsAnalysisPipeline(
        rss_loader=rss_loader,
        article_extractor=article_extractor,
        datastore_repository=datastore_repo,
    )
    return NewsPresenter(pipeline=pipeline, datastore_repository=datastore_repo)


def run() -> None:
    """Launch Streamlit view with wired dependencies."""
    presenter = build_presenter()
    run_view(presenter)


if __name__ == "__main__":
    run()
