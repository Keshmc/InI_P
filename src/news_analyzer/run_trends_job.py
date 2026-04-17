"""One-shot trend collection — for Cloud Run Jobs triggered by Cloud Scheduler."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news_analyzer.app import build_presenter
from news_analyzer.model.trends import get_long_term_trend_scheduler, load_long_term_trend_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> None:
    LOGGER.info("Long-term trend job starting.")
    presenter = build_presenter()
    config = load_long_term_trend_config()
    scheduler = get_long_term_trend_scheduler(pipeline=presenter.pipeline, config=config)
    outcome = scheduler.run_once()
    LOGGER.info("Job finished. last_run_at=%s result=%s", outcome["last_run_at"], outcome["result"])
    if outcome["error"]:
        LOGGER.error("Job error: %s", outcome["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
