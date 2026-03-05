"""Basis-Interface für alle Collector."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CollectedArticle:
    """Einheitliche Artikel-Darstellung aus jeder Quelle."""
    url: str
    title: str
    snippet: Optional[str]
    source_name: Optional[str]
    source_type: str  # 'google_news', 'newsapi', 'rss', 'twitter'
    search_term: str
    published_at: Optional[str]  # ISO 8601
    image_url: Optional[str] = None
    language: Optional[str] = None


class BaseCollector(ABC):
    """Alle Collector implementieren dieses Interface."""

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def collect(self, search_term, lang=None, country=None):
        # type: (str, Optional[str], Optional[str]) -> List[CollectedArticle]
        """Sammle Artikel die zum Suchbegriff passen."""
        pass

    @abstractmethod
    def is_available(self):
        # type: () -> bool
        """Prüfe ob dieser Collector korrekt konfiguriert ist."""
        pass

    @property
    @abstractmethod
    def name(self):
        # type: () -> str
        """Menschenlesbarer Name des Collectors."""
        pass
