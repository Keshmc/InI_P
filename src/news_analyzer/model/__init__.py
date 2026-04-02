"""Model layer package."""

from .analysis import EntityAnalyzer, EntityItem, EntityResult, SentimentAnalyzer, SentimentResult
from .datastore import (
    DatastoreConfig,
    DatastoreQuery,
    DatastoreRepository,
    FirestoreConfig,
    FirestoreQuery,
    FirestoreRepository,
)
from .insights import (
    CountMetric,
    DatastoreInsights,
    SentimentOverview,
    TrendPoint,
    build_datastore_insights,
    build_sentiment_overview,
    entities_to_display,
    sentiment_label,
)
from .model import NewsAnalysisPipeline, PipelineProgress, SearchRequest, SearchResult, SearchSummary
from .rss_feed import (
    ExtractedArticle,
    NewsArticle,
    RssArticleExtractor,
    RssFeedLoader,
    VALID_PERIODS,
    VALID_TOPICS,
)

__all__ = [
    "DatastoreConfig",
    "DatastoreQuery",
    "DatastoreRepository",
    "FirestoreConfig",
    "FirestoreQuery",
    "FirestoreRepository",
    "CountMetric",
    "DatastoreInsights",
    "EntityAnalyzer",
    "EntityItem",
    "EntityResult",
    "ExtractedArticle",
    "NewsAnalysisPipeline",
    "PipelineProgress",
    "NewsArticle",
    "RssArticleExtractor",
    "RssFeedLoader",
    "SearchRequest",
    "SearchResult",
    "SearchSummary",
    "SentimentOverview",
    "TrendPoint",
    "SentimentAnalyzer",
    "SentimentResult",
    "build_datastore_insights",
    "build_sentiment_overview",
    "entities_to_display",
    "sentiment_label",
    "VALID_PERIODS",
    "VALID_TOPICS",
]
