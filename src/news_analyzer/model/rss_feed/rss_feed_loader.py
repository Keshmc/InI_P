"""RSS loader for keyword and topic-based Google News search."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from gnews import GNews


LOGGER = logging.getLogger(__name__)
GNEWS_MAX_RESULTS_CAP = 100

VALID_PERIODS = {"1h", "6h", "12h", "1d", "3d", "7d"}
VALID_TOPICS = {
    "WORLD",
    "NATION",
    "BUSINESS",
    "TECHNOLOGY",
    "ENTERTAINMENT",
    "SPORTS",
    "SCIENCE",
    "HEALTH",
}


@dataclass
class NewsArticle:
    """Normalized article data used by presenter/view layers."""

    title: str
    description: str
    url: str
    published_date: str
    source: str
    search_mode: str
    query: str
    topic: str


class RssFeedLoader:
    """Google News RSS loader with keyword and topic search."""

    def __init__(
        self,
        language: str = "en",
        country: str = "US",
        default_period: str = "1d",
        default_max_results: int = 25,
    ) -> None:
        self.language = language
        self.country = country
        self.default_period = default_period
        self.default_max_results = default_max_results
        self.last_error: str | None = None

    def search_by_keyword(
        self,
        keyword: str,
        period: str | None = None,
        max_results: int | None = None,
    ) -> list[NewsArticle]:
        """Search Google News by free-form keyword."""
        self.last_error = None
        clean_keyword = (keyword or "").strip()
        if not clean_keyword:
            return []

        gnews = self._build_client(period=period, max_results=max_results)
        query_candidates = [clean_keyword]

        articles: list[NewsArticle] = []
        seen_urls: set[str] = set()
        for query in query_candidates:
            try:
                raw_items = gnews.get_news(query)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"Keyword search failed for '{query}': {exc}"
                LOGGER.warning("Keyword search failed for query '%s': %s", query, exc)
                continue

            for item in raw_items:
                article = self._normalize_item(item=item, search_mode="keyword", query=clean_keyword, topic="")
                if not article.url or article.url in seen_urls:
                    continue
                seen_urls.add(article.url)
                articles.append(article)
                if len(articles) >= gnews.max_results:
                    self.last_error = None
                    return articles

        if articles:
            self.last_error = None
        return articles

    def search_by_topic(
        self,
        topic: str,
        period: str | None = None,
        max_results: int | None = None,
    ) -> list[NewsArticle]:
        """Search Google News by topic only."""
        self.last_error = None
        clean_topic = (topic or "").strip().upper()
        if clean_topic not in VALID_TOPICS:
            raise ValueError(f"Invalid topic '{topic}'. Valid topics: {sorted(VALID_TOPICS)}")

        gnews = self._build_client(period=period, max_results=max_results)
        try:
            raw_items = gnews.get_news_by_topic(clean_topic)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Topic search failed for '{clean_topic}': {exc}"
            LOGGER.warning("Topic search failed for topic '%s': %s", clean_topic, exc)
            return []

        articles: list[NewsArticle] = []
        seen_urls: set[str] = set()
        for item in raw_items:
            article = self._normalize_item(item=item, search_mode="topic", query=clean_topic, topic=clean_topic)
            if not article.url or article.url in seen_urls:
                continue
            seen_urls.add(article.url)
            articles.append(article)
            if len(articles) >= gnews.max_results:
                break
        self.last_error = None
        return articles

    def search(
        self,
        mode: str,
        keyword: str = "",
        topic: str = "",
        period: str | None = None,
        max_results: int | None = None,
    ) -> list[NewsArticle]:
        """Unified search entrypoint for presenter."""
        clean_mode = (mode or "").strip().lower()
        if clean_mode == "topic":
            return self.search_by_topic(topic=topic, period=period, max_results=max_results)
        return self.search_by_keyword(keyword=keyword, period=period, max_results=max_results)

    def _build_client(self, period: str | None, max_results: int | None) -> GNews:
        resolved_period = (period or self.default_period).strip().lower()
        if resolved_period not in VALID_PERIODS:
            raise ValueError(f"Invalid period '{resolved_period}'. Valid periods: {sorted(VALID_PERIODS)}")

        resolved_max_results = max_results if max_results is not None else self.default_max_results
        resolved_max_results = max(1, int(resolved_max_results))
        resolved_max_results = min(resolved_max_results, GNEWS_MAX_RESULTS_CAP)

        return GNews(
            language=self.language,
            country=self.country,
            period=resolved_period,
            max_results=resolved_max_results,
        )

    @staticmethod
    def _normalize_item(item: dict, search_mode: str, query: str, topic: str) -> NewsArticle:
        publisher = item.get("publisher", {})
        source = publisher.get("title", "") if isinstance(publisher, dict) else ""

        return NewsArticle(
            title=item.get("title", ""),
            description=item.get("description", ""),
            url=item.get("url", ""),
            published_date=item.get("published date", ""),
            source=source,
            search_mode=search_mode,
            query=query,
            topic=topic,
        )
