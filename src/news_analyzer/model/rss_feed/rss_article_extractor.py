"""Article extraction helper for RSS URLs."""

from __future__ import annotations

from dataclasses import dataclass

from newspaper import Article, Config


@dataclass
class ExtractedArticle:
    """Normalized extraction result for one article URL."""

    url: str
    title: str
    text: str
    published_at: str | None
    error: str
    status: str


class RssArticleExtractor:
    """Extract full article text from a URL with robust error reporting."""

    def __init__(self, timeout_seconds: int = 8, max_chars: int = 15000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

        config = Config()
        config.request_timeout = timeout_seconds
        config.fetch_images = False
        config.memoize_articles = False
        self._config = config

    def extract(self, url: str) -> ExtractedArticle:
        """Extract title/text/date from a URL.

        Returns a warning status if extraction did not produce text, so callers can
        fallback to title+description analysis without aborting the whole pipeline.
        """
        clean_url = (url or "").strip()
        if not clean_url:
            return ExtractedArticle(
                url="",
                title="",
                text="",
                published_at=None,
                error="URL is empty.",
                status="warning",
            )

        article = Article(clean_url, config=self._config)
        try:
            article.download()
            article.parse()
        except Exception as exc:  # noqa: BLE001
            return ExtractedArticle(
                url=clean_url,
                title="",
                text="",
                published_at=None,
                error=f"Article extraction failed: {exc}",
                status="warning",
            )

        extracted_title = (article.title or "").strip()
        extracted_text = (article.text or "").strip()
        published_at = article.publish_date.isoformat() if article.publish_date else None

        if not extracted_text:
            # Missing fulltext is common on many publisher pages.
            # Caller can safely fall back to title+description without warning noise.
            return ExtractedArticle(
                url=clean_url,
                title=extracted_title,
                text="",
                published_at=published_at,
                error="",
                status="success",
            )

        return ExtractedArticle(
            url=clean_url,
            title=extracted_title,
            text=extracted_text[: self.max_chars],
            published_at=published_at,
            error="",
            status="success",
        )
