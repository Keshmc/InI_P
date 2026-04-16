"""Builders for publisher search and sentiment reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from ..insights import CountMetric, build_sentiment_overview, sentiment_label

from .publisher_models import PublisherArticleFact, PublisherDirectory, PublisherMatch, PublisherReport


def build_publisher_directory(
    records: list[dict[str, Any]],
    query: str = "",
    result_limit: int = 12,
    article_limit: int = 30,
    trend_limit: int = 8,
) -> PublisherDirectory:
    """Build searchable publisher summaries and detailed reports."""
    grouped_records = _group_records_by_publisher(records)
    normalized_query = str(query).strip()

    publisher_names = list(grouped_records.keys())
    if normalized_query:
        matched_names = [
            name
            for name in publisher_names
            if normalized_query.casefold() in name.casefold()
        ]
        matched_names.sort(
            key=lambda name: _query_sort_key(
                name=name,
                query=normalized_query,
                article_count=len(grouped_records.get(name, [])),
            )
        )
    else:
        matched_names = sorted(
            publisher_names,
            key=lambda name: (-len(grouped_records.get(name, [])), name.casefold()),
        )

    limited_names = matched_names[: max(1, int(result_limit))]
    reports: dict[str, PublisherReport] = {}
    matches: list[PublisherMatch] = []

    for name in limited_names:
        report = build_publisher_report(
            records=grouped_records.get(name, []),
            publisher=name,
            article_limit=article_limit,
            trend_limit=trend_limit,
        )
        reports[name] = report
        matches.append(
            PublisherMatch(
                publisher=name,
                article_count=report.article_count,
                average_score=report.average_score,
                dominant_sentiment=report.dominant_sentiment,
                latest_published_at=report.latest_published_at,
            )
        )

    selected_publisher = limited_names[0] if limited_names else ""
    return PublisherDirectory(
        query=normalized_query,
        total_publishers=len(grouped_records),
        matched_publishers=len(matched_names),
        selected_publisher=selected_publisher,
        matches=matches,
        reports=reports,
    )


def build_publisher_report(
    records: list[dict[str, Any]],
    publisher: str,
    article_limit: int = 30,
    trend_limit: int = 8,
) -> PublisherReport:
    """Build detailed sentiment report for a single publisher."""
    sorted_records = sorted(records, key=_record_sort_key, reverse=True)
    sentiment = build_sentiment_overview(sorted_records)

    trend_counter: Counter[str] = Counter()
    article_rows: list[PublisherArticleFact] = []
    parsed_dates: list[datetime] = []

    for row in sorted_records:
        trend = _trend_from_row(row)
        if trend:
            trend_counter[trend] += 1

        published_at = str(row.get("published_at", "")).strip() or str(row.get("published_date", "")).strip()
        published_dt = _parse_datetime(published_at)
        if published_dt is not None:
            parsed_dates.append(published_dt)

        if len(article_rows) < max(1, int(article_limit)):
            score = float(row.get("sentiment_score", 0.0))
            article_rows.append(
                PublisherArticleFact(
                    title=str(row.get("title", "")).strip(),
                    trend=trend,
                    sentiment_score=round(score, 4),
                    sentiment_magnitude=round(float(row.get("sentiment_magnitude", 0.0)), 4),
                    sentiment_label=sentiment_label(score),
                    published_at=published_at,
                    url=str(row.get("url", "")).strip(),
                )
            )

    earliest_published_at = min(parsed_dates).isoformat() if parsed_dates else ""
    latest_published_at = max(parsed_dates).isoformat() if parsed_dates else ""
    top_trends = [
        CountMetric(label=label, count=count)
        for label, count in trend_counter.most_common(max(1, int(trend_limit)))
    ]

    return PublisherReport(
        publisher=publisher,
        article_count=len(sorted_records),
        average_score=sentiment.average_score,
        average_magnitude=sentiment.average_magnitude,
        dominant_sentiment=sentiment_label(sentiment.average_score),
        positive_count=sentiment.positive_count,
        neutral_count=sentiment.neutral_count,
        negative_count=sentiment.negative_count,
        earliest_published_at=earliest_published_at,
        latest_published_at=latest_published_at,
        top_trends=top_trends,
        article_rows=article_rows,
    )


def _group_records_by_publisher(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        publisher = str(row.get("source", "")).strip() or "Unknown"
        grouped[publisher].append(row)
    return dict(grouped)


def _query_sort_key(name: str, query: str, article_count: int) -> tuple[int, int, int, int, str]:
    lower_name = name.casefold()
    lower_query = query.casefold()
    position = lower_name.find(lower_query)
    exact_match = 0 if lower_name == lower_query else 1
    starts_with = 0 if lower_name.startswith(lower_query) else 1
    safe_position = position if position >= 0 else 9999
    return (exact_match, starts_with, safe_position, -article_count, lower_name)


def _trend_from_row(row: dict[str, Any]) -> str:
    query = str(row.get("query", "")).strip()
    if query:
        return query
    topic = str(row.get("topic", "")).strip()
    if topic:
        return topic
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


def _record_sort_key(row: dict[str, Any]) -> datetime:
    return (
        _parse_datetime(str(row.get("published_at", "")).strip())
        or _parse_datetime(str(row.get("published_date", "")).strip())
        or _parse_datetime(str(row.get("analysis_timestamp", "")).strip())
        or _parse_datetime(str(row.get("ingested_at", "")).strip())
        or datetime.min.replace(tzinfo=timezone.utc)
    )
