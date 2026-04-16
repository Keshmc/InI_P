"""Dataclasses for publisher search and sentiment reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..insights import CountMetric


@dataclass
class PublisherMatch:
    """Compact publisher result used in search lists."""

    publisher: str
    article_count: int
    average_score: float
    dominant_sentiment: str
    latest_published_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            "article_count": int(self.article_count),
            "average_score": float(self.average_score),
            "dominant_sentiment": self.dominant_sentiment,
            "latest_published_at": self.latest_published_at,
        }


@dataclass
class PublisherArticleFact:
    """Article row displayed in the publisher detail view."""

    title: str
    trend: str
    sentiment_score: float
    sentiment_magnitude: float
    sentiment_label: str
    published_at: str
    url: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "trend": self.trend,
            "sentiment_score": float(self.sentiment_score),
            "sentiment_magnitude": float(self.sentiment_magnitude),
            "sentiment_label": self.sentiment_label,
            "published_at": self.published_at,
            "url": self.url,
        }


@dataclass
class PublisherReport:
    """Detailed sentiment report for one publisher."""

    publisher: str
    article_count: int
    average_score: float
    average_magnitude: float
    dominant_sentiment: str
    positive_count: int
    neutral_count: int
    negative_count: int
    earliest_published_at: str
    latest_published_at: str
    top_trends: list[CountMetric] = field(default_factory=list)
    article_rows: list[PublisherArticleFact] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            "article_count": int(self.article_count),
            "average_score": float(self.average_score),
            "average_magnitude": float(self.average_magnitude),
            "dominant_sentiment": self.dominant_sentiment,
            "positive_count": int(self.positive_count),
            "neutral_count": int(self.neutral_count),
            "negative_count": int(self.negative_count),
            "earliest_published_at": self.earliest_published_at,
            "latest_published_at": self.latest_published_at,
            "sentiment_distribution": [
                {"label": "Positive", "count": int(self.positive_count)},
                {"label": "Neutral", "count": int(self.neutral_count)},
                {"label": "Negative", "count": int(self.negative_count)},
            ],
            "top_trends": [item.as_dict() for item in self.top_trends],
            "article_rows": [item.as_dict() for item in self.article_rows],
        }


@dataclass
class PublisherDirectory:
    """Search result package for publisher discovery."""

    query: str
    total_publishers: int
    matched_publishers: int
    selected_publisher: str
    matches: list[PublisherMatch] = field(default_factory=list)
    reports: dict[str, PublisherReport] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "total_publishers": int(self.total_publishers),
            "matched_publishers": int(self.matched_publishers),
            "selected_publisher": self.selected_publisher,
            "matches": [item.as_dict() for item in self.matches],
            "reports": {name: report.as_dict() for name, report in self.reports.items()},
        }
