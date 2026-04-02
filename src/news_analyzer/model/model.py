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
    existing_articles: int
    new_articles: int
    analyzed_articles: int
    saved_articles: int
    loaded_articles: int
    avg_sentiment_score: float
    avg_sentiment_magnitude: float
    positive_count: int
    neutral_count: int
    negative_count: int
    top_entities: list[dict[str, Any]]


@dataclass
class PipelineProgress:
    """Progress payload for multi-stage pipeline updates."""

    phase: str
    processed: int
    total: int
    message: str
    existing_articles: int = 0
    new_articles: int = 0
    analyzed_articles: int = 0
    saved_articles: int = 0
    loaded_articles: int = 0


@dataclass
class SearchResult:
    """Output payload returned to presenter/view."""

    request: SearchRequest
    records: list[dict[str, Any]]
    summary: SearchSummary
    warnings: list[str]
    errors: list[str]


class NewsAnalysisPipeline:
    """Orchestrate RSS -> dedupe -> analysis -> Firestore save -> Firestore reload."""

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
        progress_callback: Callable[[PipelineProgress], None] | None = None,
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
        self._emit_progress(
            callback=progress_callback,
            phase="collect",
            processed=total_articles,
            total=total_articles,
            message=f"Feed loaded. {total_articles} article(s) collected.",
        )

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        saved_count = 0

        urls = [item.url.strip() for item in raw_articles if item.url.strip()]
        existing_urls: set[str] = set()
        if self.datastore_repository and self.datastore_repository.is_available:
            existing_urls = self.datastore_repository.get_existing_urls(urls)
            if self.datastore_repository.last_error:
                warnings.append(self.datastore_repository.last_error)
        elif urls:
            reason = ""
            if self.datastore_repository:
                reason = str(self.datastore_repository.init_error or "").strip()
            reason_suffix = f" Reason: {reason}" if reason else ""
            warnings.append(
                "Firestore unavailable: duplicate check disabled. "
                f"All fetched articles will be analyzed in-memory.{reason_suffix}"
            )

        existing_articles = len(existing_urls)
        new_articles = 0
        self._emit_progress(
            callback=progress_callback,
            phase="check_existing",
            processed=existing_articles,
            total=total_articles,
            message=f"Duplicate check completed. {existing_articles} article(s) already in Firestore.",
            existing_articles=existing_articles,
        )

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

        articles_to_process = [item for item in raw_articles if item.url.strip() not in existing_urls]
        new_articles = len(articles_to_process)
        analyzed_count = 0

        for index, item in enumerate(articles_to_process, start=1):
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
                "raw_article": {
                    "title": item.title,
                    "description": item.description,
                    "url": item.url,
                    "published_date": item.published_date,
                    "source": item.source,
                    "search_mode": item.search_mode,
                    "query": item.query,
                    "topic": item.topic,
                },
            }
            records.append(record)
            analyzed_count = index
            self._emit_progress(
                callback=progress_callback,
                phase="analyze",
                processed=index,
                total=max(new_articles, 1),
                message=f"Analyzing new articles: {index}/{new_articles}.",
                existing_articles=existing_articles,
                new_articles=new_articles,
                analyzed_articles=analyzed_count,
            )

        if self.datastore_repository and self.datastore_repository.is_available and records:
            saved_count = self.datastore_repository.save_records(records)
            if self.datastore_repository.last_error:
                warnings.append(self.datastore_repository.last_error)
            self._emit_progress(
                callback=progress_callback,
                phase="persist",
                processed=saved_count,
                total=max(new_articles, 1),
                message=f"Saved {saved_count}/{new_articles} new article(s) to Firestore.",
                existing_articles=existing_articles,
                new_articles=new_articles,
                analyzed_articles=analyzed_count,
                saved_articles=saved_count,
            )

        if self.datastore_repository and self.datastore_repository.is_available:
            loaded_records = self.datastore_repository.load_records_for_urls(urls)
            if self.datastore_repository.last_error:
                errors.append(self.datastore_repository.last_error)
            final_records = loaded_records
        else:
            final_records = records

        loaded_count = len(final_records)
        self._emit_progress(
            callback=progress_callback,
            phase="reload",
            processed=loaded_count,
            total=max(total_articles, 1),
            message=f"Loaded {loaded_count}/{total_articles} article(s) from Firestore for display.",
            existing_articles=existing_articles,
            new_articles=new_articles,
            analyzed_articles=analyzed_count,
            saved_articles=saved_count,
            loaded_articles=loaded_count,
        )

        summary = self._build_summary(
            records=final_records,
            articles_found=total_articles,
            existing_articles=existing_articles,
            new_articles=new_articles,
            analyzed_articles=analyzed_count,
            saved_articles=saved_count,
            loaded_articles=loaded_count,
        )
        self._emit_progress(
            callback=progress_callback,
            phase="done",
            processed=loaded_count,
            total=max(total_articles, 1),
            message="Pipeline completed.",
            existing_articles=existing_articles,
            new_articles=new_articles,
            analyzed_articles=analyzed_count,
            saved_articles=saved_count,
            loaded_articles=loaded_count,
        )
        return SearchResult(
            request=request,
            records=final_records,
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
    def _build_summary(
        records: list[dict[str, Any]],
        articles_found: int,
        existing_articles: int,
        new_articles: int,
        analyzed_articles: int,
        saved_articles: int,
        loaded_articles: int,
    ) -> SearchSummary:
        if not records:
            return SearchSummary(
                articles_found=articles_found,
                existing_articles=existing_articles,
                new_articles=new_articles,
                analyzed_articles=analyzed_articles,
                saved_articles=saved_articles,
                loaded_articles=loaded_articles,
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
            articles_found=articles_found,
            existing_articles=existing_articles,
            new_articles=new_articles,
            analyzed_articles=analyzed_articles,
            saved_articles=saved_articles,
            loaded_articles=loaded_articles,
            avg_sentiment_score=round(sum(scores) / len(scores), 4),
            avg_sentiment_magnitude=round(sum(magnitudes) / len(magnitudes), 4),
            positive_count=positive_count,
            neutral_count=neutral_count,
            negative_count=negative_count,
            top_entities=top_entities,
        )

    @staticmethod
    def _emit_progress(
        callback: Callable[[PipelineProgress], None] | None,
        phase: str,
        processed: int,
        total: int,
        message: str,
        existing_articles: int = 0,
        new_articles: int = 0,
        analyzed_articles: int = 0,
        saved_articles: int = 0,
        loaded_articles: int = 0,
    ) -> None:
        if callback is None:
            return

        callback(
            PipelineProgress(
                phase=phase,
                processed=processed,
                total=max(total, 1),
                message=message,
                existing_articles=existing_articles,
                new_articles=new_articles,
                analyzed_articles=analyzed_articles,
                saved_articles=saved_articles,
                loaded_articles=loaded_articles,
            )
        )
