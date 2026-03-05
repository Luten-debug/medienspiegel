"""Generischer RSS Feed Collector - für konfigurierbare Feeds."""

import re
import feedparser
from dateutil import parser as dateparser

from .base import BaseCollector, CollectedArticle


class RssFeedCollector(BaseCollector):

    @property
    def name(self):
        return "RSS Feeds"

    def is_available(self):
        feeds = self.config.get('rss_feeds', [])
        return len(feeds) > 0

    def collect(self, search_term, lang=None, country=None):
        """Sammle Artikel aus konfigurierten RSS-Feeds die zum Suchbegriff passen."""
        feeds = self.config.get('rss_feeds', [])
        max_articles = self.config.get('collection', {}).get('max_articles_per_source', 50)
        articles = []

        # Suchbegriff vorbereiten (Anführungszeichen entfernen für Textsuche)
        clean_term = search_term.replace('"', '').lower()
        search_words = clean_term.split()

        for feed_config in feeds:
            feed_name = feed_config.get('name', 'RSS')
            feed_url = feed_config.get('url', '')
            if not feed_url:
                continue

            try:
                feed = feedparser.parse(feed_url)
            except Exception:
                continue

            for entry in feed.entries[:max_articles]:
                title = entry.get('title', '')
                summary = entry.get('summary', '')
                content = (title + ' ' + summary).lower()

                # Prüfe ob der Suchbegriff im Inhalt vorkommt
                if not self._matches(content, search_words):
                    continue

                published_iso = None
                if entry.get('published'):
                    try:
                        published_iso = dateparser.parse(entry['published']).isoformat()
                    except (ValueError, TypeError):
                        pass

                snippet = self._clean_html(summary)
                if len(snippet) > 500:
                    snippet = snippet[:497] + '...'

                articles.append(CollectedArticle(
                    url=entry.get('link', ''),
                    title=title,
                    snippet=snippet,
                    source_name=feed_name,
                    source_type='rss',
                    search_term=search_term,
                    published_at=published_iso,
                    image_url=None,
                    language=lang
                ))

        return articles

    def _matches(self, content, search_words):
        """Prüfe ob alle Suchworte im Content vorkommen."""
        return all(word in content for word in search_words)

    def _clean_html(self, html):
        """Entferne HTML-Tags aus Text."""
        if not html:
            return ''
        text = re.sub(r'<[^>]+>', ' ', html)
        return re.sub(r'\s+', ' ', text).strip()
