"""Page classes for view routing."""

from .datastore.datastore_page import DataStorePage
from .publishers.publisher_page import PublisherPage
from .search.search_page import NewsSearchPage

__all__ = ["DataStorePage", "NewsSearchPage", "PublisherPage"]
