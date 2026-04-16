"""Background scheduler for long-term trend ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
from typing import Any

import yaml

from news_analyzer.model.model import NewsAnalysisPipeline, SearchRequest

LOGGER = logging.getLogger(__name__)

DEFAULT_LONG_TERM_TICKERS = ["Trump", "Iran", "Oil", "Gold", "NVDA", "Tesla", "MSFT", "Apple", "USA"]


@dataclass
class LongTermTrendConfig:
    """Configuration for automatic long-term trend ingestion."""

    enabled: bool = True
    interval_minutes: int = 360
    run_on_startup: bool = True
    period: str = "1d"
    max_results: int = 100
    extract_full_text: bool = True
    include_entities: bool = True
    tickers: list[str] = field(default_factory=lambda: list(DEFAULT_LONG_TERM_TICKERS))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> LongTermTrendConfig:
        if not isinstance(payload, dict):
            return cls()

        raw_tickers = payload.get("tickers", DEFAULT_LONG_TERM_TICKERS)
        tickers = [str(item).strip() for item in raw_tickers if str(item).strip()]
        if not tickers:
            tickers = list(DEFAULT_LONG_TERM_TICKERS)

        return cls(
            enabled=bool(payload.get("enabled", True)),
            interval_minutes=max(1, int(payload.get("interval_minutes", 360))),
            run_on_startup=bool(payload.get("run_on_startup", True)),
            period=str(payload.get("period", "1d")).strip().lower() or "1d",
            max_results=max(1, int(payload.get("max_results", 100))),
            extract_full_text=bool(payload.get("extract_full_text", True)),
            include_entities=bool(payload.get("include_entities", True)),
            tickers=tickers,
        )


def load_long_term_trend_config(config_path: Path | None = None) -> LongTermTrendConfig:
    """Load long-term trend config from YAML file."""
    path = config_path or (Path.cwd() / "config.yaml")
    if not path.exists():
        return LongTermTrendConfig()

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Long-term config load failed: %s", exc)
        return LongTermTrendConfig()

    section = {}
    if isinstance(payload, dict):
        section = payload.get("long_term_trends", {}) or {}
    return LongTermTrendConfig.from_payload(section if isinstance(section, dict) else {})


class LongTermTrendScheduler:
    """Process-wide background scheduler that collects trend data periodically."""

    def __init__(self, pipeline: NewsAnalysisPipeline, config: LongTermTrendConfig) -> None:
        self.pipeline = pipeline
        self.config = config

        self._enabled = bool(config.enabled)
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._stop_event = threading.Event()

        self.last_run_at: str | None = None
        self.last_result: dict[str, Any] = {}
        self.last_error: str = ""

    def start(self) -> None:
        """Start scheduler thread if enabled."""
        if not self._enabled:
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="long-term-trend-scheduler",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "Long-term trend scheduler started. interval=%s minute(s), tickers=%s",
            self.config.interval_minutes,
            self.config.tickers,
        )

    def stop(self) -> None:
        """Stop scheduler thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        LOGGER.info("Long-term trend scheduler stopped.")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable scheduler at runtime."""
        enabled_flag = bool(enabled)
        with self._state_lock:
            self._enabled = enabled_flag

        if enabled_flag:
            self.start()
        else:
            self.stop()

    def status(self) -> dict[str, Any]:
        """Return scheduler status for UI display."""
        with self._state_lock:
            enabled = self._enabled
            last_run_at = self.last_run_at
            last_result = dict(self.last_result)
            last_error = self.last_error
        running = bool(self._thread and self._thread.is_alive())
        return {
            "enabled": enabled,
            "running": running,
            "last_run_at": last_run_at,
            "last_result": last_result,
            "last_error": last_error,
            "interval_minutes": self.config.interval_minutes,
            "tickers": list(self.config.tickers),
        }

    def _loop(self) -> None:
        if self.config.run_on_startup and not self._stop_event.is_set():
            self._run_once()

        while True:
            wait_seconds = max(60, int(self.config.interval_minutes) * 60)
            if self._stop_event.wait(wait_seconds):
                break
            self._run_once()

    def _run_once(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            LOGGER.info("Long-term trend run skipped: previous run still active.")
            return

        try:
            result = self._collect_cycle()
            timestamp = datetime.now(timezone.utc).isoformat()
            with self._state_lock:
                self.last_run_at = timestamp
                self.last_result = result
                self.last_error = ""
            LOGGER.info("Long-term trend run finished: %s", result)
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self.last_error = str(exc)
            LOGGER.exception("Long-term trend run failed: %s", exc)
        finally:
            self._run_lock.release()

    def _collect_cycle(self) -> dict[str, Any]:
        ticker_results: list[dict[str, Any]] = []
        totals = {
            "fetched": 0,
            "existing": 0,
            "new": 0,
            "saved": 0,
            "loaded": 0,
        }

        for ticker in self.config.tickers:
            request = SearchRequest(
                mode="keyword",
                keyword=ticker,
                topic="",
                period=self.config.period,
                max_results=self.config.max_results,
                extract_full_text=self.config.extract_full_text,
                include_entities=self.config.include_entities,
                use_mock_nlp=False,
                fallback_to_mock_on_error=False,
                store_to_datastore=True,
                industry_sector="",
            )
            result = self.pipeline.run_search(request)

            summary = result.summary
            ticker_payload = {
                "ticker": ticker,
                "fetched": int(summary.articles_found),
                "existing": int(summary.existing_articles),
                "new": int(summary.new_articles),
                "saved": int(summary.saved_articles),
                "loaded": int(summary.loaded_articles),
                "warnings": len(result.warnings),
                "errors": len(result.errors),
            }
            ticker_results.append(ticker_payload)

            totals["fetched"] += ticker_payload["fetched"]
            totals["existing"] += ticker_payload["existing"]
            totals["new"] += ticker_payload["new"]
            totals["saved"] += ticker_payload["saved"]
            totals["loaded"] += ticker_payload["loaded"]

        return {"totals": totals, "tickers": ticker_results}


_GLOBAL_LOCK = threading.Lock()
_GLOBAL_SCHEDULER: LongTermTrendScheduler | None = None


def get_long_term_trend_scheduler(
    pipeline: NewsAnalysisPipeline,
    config: LongTermTrendConfig,
) -> LongTermTrendScheduler:
    """Return a singleton scheduler instance for this process."""
    global _GLOBAL_SCHEDULER
    with _GLOBAL_LOCK:
        if _GLOBAL_SCHEDULER is None:
            _GLOBAL_SCHEDULER = LongTermTrendScheduler(pipeline=pipeline, config=config)
        else:
            _GLOBAL_SCHEDULER.config = config
        return _GLOBAL_SCHEDULER
