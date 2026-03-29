"""Core model pipeline for RSS fetching, analysis, and persistence."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from news_analyzer.model.analysis import EntityAnalyzer, EntityResult, SentimentAnalyzer
from news_analyzer.model.datastore import DatastoreRepository
from news_analyzer.model.rss_feed import RssArticleExtractor, RssFeedLoader


@dataclass
class SearchRequest:
    """Input payload for one search + analysis run."""

    mode: str  # "keyword" or "topic"
    keyword: str = ""
    topic: str = ""
    period: str = "1d"
    max_results: int = 10
    extract_full_text: bool = False
    include_entities: bool = True
    use_mock_nlp: bool = False
    fallback_to_mock_on_error: bool = True
    sentiment_max_chars: int = 4000
    entity_max_chars: int = 4000
    entity_max_items: int = 30
    store_to_datastore: bool = False
    industry_sector: str = ""


@dataclass
class SearchSummary:
    """Computed summary statistics for a run."""

    articles_found: int
    avg_sentiment_score: float
    avg_sentiment_magnitude: float
    positive_count: int
    neutral_count: int
    negative_count: int
    top_entities: list[dict[str, Any]]


@dataclass
class SearchResult:
    """Output payload returned to presenter/view."""

    request: SearchRequest
    records: list[dict[str, Any]]
    summary: SearchSummary
    warnings: list[str]
    errors: list[str]


class NewsAnalysisPipeline:
    """Orchestrate RSS -> extraction -> sentiment/entities -> optional persistence."""

    def __init__(
        self,
        rss_loader: RssFeedLoader,
        article_extractor: RssArticleExtractor,
        datastore_repository: DatastoreRepository | None = None,
    ) -> None:
        self.rss_loader = rss_loader
        self.article_extractor = article_extractor
        self.datastore_repository = datastore_repository

    def run_search(
        self,
        request: SearchRequest,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> SearchResult:
        """Run end-to-end processing for one user request."""
        mode = request.mode.strip().lower()
        if mode not in {"keyword", "topic"}:
            raise ValueError("request.mode must be either 'keyword' or 'topic'.")

        raw_articles = self.rss_loader.search(
            mode=mode,
            keyword=request.keyword,
            topic=request.topic,
            period=request.period,
            max_results=request.max_results,
        )
        total_articles = len(raw_articles)
        if progress_callback is not None:
            progress_callback(0, total_articles)

        sentiment_analyzer = SentimentAnalyzer(
            use_mock=request.use_mock_nlp,
            max_chars=request.sentiment_max_chars,
            fallback_to_mock_on_error=request.fallback_to_mock_on_error,
        )
        entity_analyzer = EntityAnalyzer(
            use_mock=request.use_mock_nlp,
            max_chars=request.entity_max_chars,
            max_entities=request.entity_max_items,
            fallback_to_mock_on_error=request.fallback_to_mock_on_error,
        )

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []

        for index, item in enumerate(raw_articles, start=1):
            base_text = f"{item.title}. {item.description}".strip()
            text_for_analysis = base_text
            extracted_title = item.title
            extracted_published_at = ""
            extraction_error = ""
            extraction_status = "success"

            if request.extract_full_text:
                extraction = self.article_extractor.extract(item.url)
                extraction_error = extraction.error
                extraction_status = extraction.status
                extracted_title = extraction.title or item.title
                extracted_published_at = extraction.published_at or ""
                if extraction.text:
                    text_for_analysis = extraction.text

            sentiment = sentiment_analyzer.analyze(text_for_analysis)

            if request.include_entities:
                entity_result = entity_analyzer.analyze(text_for_analysis)
            else:
                entity_result = EntityResult(
                    entities=[],
                    status="success",
                    error="",
                    provider="disabled",
                )

            analysis_error = " | ".join(
                [part for part in [sentiment.error, entity_result.error] if part]
            ).strip()

            status = self._calculate_status(
                extraction_status=extraction_status,
                sentiment_status=sentiment.status,
                entity_status=entity_result.status,
            )

            if extraction_error:
                warnings.append(f"{item.url}: {extraction_error}")
            if analysis_error:
                if status == "error":
                    errors.append(f"{item.url}: {analysis_error}")
                else:
                    warnings.append(f"{item.url}: {analysis_error}")

            record = {
                "symbol": request.keyword.upper().strip() if mode == "keyword" else "",
                "company_keyword": request.keyword.strip() if mode == "keyword" else "",
                "query": request.keyword.strip() if mode == "keyword" else request.topic.strip().upper(),
                "search_mode": mode,
                "industry_sector": request.industry_sector.strip(),
                "topic": request.topic.strip().upper() if mode == "topic" else "",
                "period": request.period.strip().lower(),
                "title": extracted_title,
                "description": item.description,
                "source": item.source,
                "url": item.url,
                "published_date": item.published_date,
                "published_at": extracted_published_at,
                "article_text": text_for_analysis,
                "sentiment_score": float(sentiment.score),
                "sentiment_magnitude": float(sentiment.magnitude),
                "entities": [asdict(entity) for entity in entity_result.entities],
                "analysis_error": analysis_error,
                "extraction_error": extraction_error,
                "status": status,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                "sentiment_provider": sentiment.provider,
                "entity_provider": entity_result.provider,
            }
            records.append(record)
            if progress_callback is not None:
                progress_callback(index, total_articles)

        if request.store_to_datastore and self.datastore_repository and self.datastore_repository.is_available:
            self.datastore_repository.save_records(records)

        summary = self._build_summary(records)
        return SearchResult(
            request=request,
            records=records,
            summary=summary,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def _calculate_status(extraction_status: str, sentiment_status: str, entity_status: str) -> str:
        if "error" in {extraction_status, sentiment_status, entity_status}:
            return "error"
        if "warning" in {extraction_status, sentiment_status, entity_status}:
            return "warning"
        return "success"

    @staticmethod
    def _build_summary(records: list[dict[str, Any]]) -> SearchSummary:
        if not records:
            return SearchSummary(
                articles_found=0,
                avg_sentiment_score=0.0,
                avg_sentiment_magnitude=0.0,
                positive_count=0,
                neutral_count=0,
                negative_count=0,
                top_entities=[],
            )

        scores = [float(record.get("sentiment_score", 0.0)) for record in records]
        magnitudes = [float(record.get("sentiment_magnitude", 0.0)) for record in records]

        positive_count = sum(score > 0.1 for score in scores)
        negative_count = sum(score < -0.1 for score in scores)
        neutral_count = len(scores) - positive_count - negative_count

        entity_counter: Counter[str] = Counter()
        for record in records:
            for entity in record.get("entities", []):
                if not isinstance(entity, dict):
                    continue
                name = str(entity.get("name", "")).strip()
                if name:
                    entity_counter[name] += 1

        top_entities = [{"name": name, "count": count} for name, count in entity_counter.most_common(15)]

        return SearchSummary(
            articles_found=len(records),
            avg_sentiment_score=round(sum(scores) / len(scores), 4),
            avg_sentiment_magnitude=round(sum(magnitudes) / len(magnitudes), 4),
            positive_count=positive_count,
            neutral_count=neutral_count,
            negative_count=negative_count,
            top_entities=top_entities,
        )
