"""Shared builders for datastore/search insight objects."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from .insights_models import CountMetric, DatastoreInsights, SentimentOverview, TrendPoint


def sentiment_label(score: float) -> str:
    """Map score to sentiment label."""
    if score > 0.1:
        return "positive"
    if score < -0.1:
        return "negative"
    return "neutral"


def entities_to_display(raw_entities: Any) -> str:
    """Convert list of entity dicts into a readable string."""
    if not isinstance(raw_entities, list):
        return ""

    parts: list[str] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        entity_type = str(item.get("entity_type", "")).strip().upper()
        if not name:
            continue
        parts.append(f"{name} ({entity_type})" if entity_type else name)
    return ", ".join(parts)


def build_sentiment_overview(records: list[dict[str, Any]]) -> SentimentOverview:
    """Build aggregate sentiment overview."""
    if not records:
        return SentimentOverview(
            average_score=0.0,
            average_magnitude=0.0,
            positive_count=0,
            neutral_count=0,
            negative_count=0,
            total_count=0,
        )

    scores = [float(row.get("sentiment_score", 0.0)) for row in records]
    magnitudes = [float(row.get("sentiment_magnitude", 0.0)) for row in records]
    positive_count = sum(score > 0.1 for score in scores)
    negative_count = sum(score < -0.1 for score in scores)
    neutral_count = len(scores) - positive_count - negative_count

    return SentimentOverview(
        average_score=round(sum(scores) / len(scores), 4),
        average_magnitude=round(sum(magnitudes) / len(magnitudes), 4),
        positive_count=int(positive_count),
        neutral_count=int(neutral_count),
        negative_count=int(negative_count),
        total_count=len(records),
    )


def build_datastore_insights(records: list[dict[str, Any]], top_n: int = 15) -> DatastoreInsights:
    """Build reusable insights package from analyzed records."""
    sentiment = build_sentiment_overview(records)

    topic_counter: Counter[str] = Counter()
    entity_counter: Counter[str] = Counter()
    publisher_counter: Counter[str] = Counter()
    trend_points: list[TrendPoint] = []
    article_facts: list[dict[str, Any]] = []
    unique_entities_set: set[str] = set()
    unique_topics_set: set[str] = set()
    unique_publishers_set: set[str] = set()

    for row in records:
        topic = _topic_from_row(row)
        if topic:
            topic_counter[topic] += 1
            unique_topics_set.add(topic)

        source = str(row.get("source", "")).strip() or "Unknown"
        publisher_counter[source] += 1
        unique_publishers_set.add(source)

        entities = row.get("entities", [])
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                name = str(entity.get("name", "")).strip()
                if not name:
                    continue
                entity_counter[name] += 1
                unique_entities_set.add(name)

        trend_dt = _parse_datetime(str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip())
        if trend_dt is not None:
            trend_points.append(
                TrendPoint(
                    published_time=trend_dt.isoformat(),
                    sentiment_score=float(row.get("sentiment_score", 0.0)),
                    title=str(row.get("title", "")).strip(),
                    source=source,
                )
            )

        article_facts.append(
            {
                "title": str(row.get("title", "")).strip(),
                "source": source,
                "topic": topic,
                "query": str(row.get("query", "")).strip(),
                "published_date": str(row.get("published_date", "")).strip(),
                "sentiment_score": round(float(row.get("sentiment_score", 0.0)), 4),
                "sentiment_magnitude": round(float(row.get("sentiment_magnitude", 0.0)), 4),
                "sentiment_label": sentiment_label(float(row.get("sentiment_score", 0.0))),
                "entities": entities_to_display(entities),
                "status": str(row.get("status", "")).strip(),
                "url": str(row.get("url", "")).strip(),
            }
        )

    trend_points.sort(key=lambda item: item.published_time)

    top_topics = [CountMetric(label=label, count=count) for label, count in topic_counter.most_common(top_n)]
    top_entities = [CountMetric(label=label, count=count) for label, count in entity_counter.most_common(top_n)]
    top_publishers = [CountMetric(label=label, count=count) for label, count in publisher_counter.most_common(top_n)]

    return DatastoreInsights(
        sentiment=sentiment,
        top_topics=top_topics,
        top_entities=top_entities,
        top_publishers=top_publishers,
        trend_points=trend_points,
        article_facts=article_facts,
        unique_publishers=len(unique_publishers_set),
        unique_topics=len(unique_topics_set),
        unique_entities=len(unique_entities_set),
    )


def _topic_from_row(row: dict[str, Any]) -> str:
    topic = str(row.get("topic", "")).strip()
    if topic:
        return topic
    query = str(row.get("query", "")).strip()
    if query:
        return query
    return "UNKNOWN"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except Exception:  # noqa: BLE001
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
