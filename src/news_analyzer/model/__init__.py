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
    "SentimentAnalyzer",
    "SentimentResult",
    "VALID_PERIODS",
    "VALID_TOPICS",
]
