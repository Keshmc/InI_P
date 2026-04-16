"""Dataclasses for reusable datastore/search analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CountMetric:
    """Simple label-count metric for charts."""

    label: str
    count: int

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "count": int(self.count)}


@dataclass
class SentimentOverview:
    """Sentiment overview across a list of records."""

    average_score: float
    average_magnitude: float
    positive_count: int
    neutral_count: int
    negative_count: int
    total_count: int

    def as_distribution_rows(self) -> list[dict[str, Any]]:
        return [
            {"label": "Positive", "count": int(self.positive_count)},
            {"label": "Neutral", "count": int(self.neutral_count)},
            {"label": "Negative", "count": int(self.negative_count)},
        ]


@dataclass
class TrendPoint:
    """One trend datapoint for sentiment over publication time."""

    published_time: str
    sentiment_score: float
    title: str
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "published_time": self.published_time,
            "sentiment_score": float(self.sentiment_score),
            "title": self.title,
            "source": self.source,
        }


@dataclass
class DatastoreInsights:
    """Aggregate insights package used in Search and Datastore pages."""

    sentiment: SentimentOverview
    top_trends: list[CountMetric] = field(default_factory=list)
    top_entities: list[CountMetric] = field(default_factory=list)
    top_publishers: list[CountMetric] = field(default_factory=list)
    trend_points: list[TrendPoint] = field(default_factory=list)
    article_facts: list[dict[str, Any]] = field(default_factory=list)
    unique_publishers: int = 0
    unique_trends: int = 0
    unique_entities: int = 0

    @property
    def top_topics(self) -> list[CountMetric]:
        """Backward-compatible alias for old UI code."""
        return self.top_trends

    @property
    def unique_topics(self) -> int:
        """Backward-compatible alias for old UI code."""
        return self.unique_trends
