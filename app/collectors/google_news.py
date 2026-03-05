"""Google News RSS Collector - Hauptquelle, kein API-Key nötig."""

import re
import html
import feedparser
import requests
from urllib.parse import quote
from dateutil import parser as dateparser

from .base import BaseCollector, CollectedArticle


class GoogleNewsCollector(BaseCollector):

    @property
    def name(self):
        return "Google News"

    def is_available(self):
        return True  # Kein API-Key nötig

    def collect(self, search_term, lang=None, country=None):
        """Sammle Artikel von Google News RSS fuer einen Suchbegriff."""
        lang = lang or self.config.get('language', 'de')
        country = country or self.config.get('country', 'DE')
        max_articles = self.config.get('collection', {}).get('max_articles_per_source', 50)

        # Google News RSS URL bauen
        encoded_term = quote(search_term)
        url = (
            "https://news.google.com/rss/search"
            "?q={query}&hl={lang}&gl={country}&ceid={country}:{lang}"
        ).format(query=encoded_term, lang=lang, country=country)

        # feedparser direkt mit URL hat SSL-Probleme auf aelterem Python,
        # daher holen wir den Feed mit requests und parsen den Text
        resp = requests.get(url, timeout=15,
                            headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        articles = []

        for entry in feed.entries[:max_articles]:
            title = entry.get('title', '')
            # Google News hängt oft " - Quellenname" an den Titel
            source_name = self._extract_source_from_title(title)
            clean_title = self._clean_title(title)

            # URL aus dem Feed extrahieren
            link = entry.get('link', '')

            # Datum parsen
            published = entry.get('published', '')
            published_iso = None
            if published:
                try:
                    published_iso = dateparser.parse(published).isoformat()
                except (ValueError, TypeError):
                    pass

            # Snippet aus der Beschreibung extrahieren
            snippet = self._extract_snippet(entry.get('summary', ''))

            articles.append(CollectedArticle(
                url=link,
                title=clean_title or title,
                snippet=snippet,
                source_name=source_name,
                source_type='google_news',
                search_term=search_term,
                published_at=published_iso,
                image_url=None,
                language=lang
            ))

        return articles

    def _extract_source_from_title(self, title):
        """Extrahiere den Quellennamen aus dem Google News Titel.

        Google News formatiert Titel als: "Artikel-Titel - Quellenname"
        """
        if ' - ' in title:
            return title.rsplit(' - ', 1)[-1].strip()
        return None

    def _clean_title(self, title):
        """Entferne den Quellennamen vom Titel."""
        if ' - ' in title:
            return title.rsplit(' - ', 1)[0].strip()
        return title

    def _extract_snippet(self, summary_html):
        """Extrahiere lesbaren Text aus dem HTML-Summary."""
        if not summary_html:
            return None
        # HTML-Entities dekodieren und Tags entfernen
        text = html.unescape(summary_html)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Auf sinnvolle Laenge kuerzen
        if len(text) > 500:
            text = text[:497] + '...'
        return text if text else None

    def _resolve_google_news_url(self, google_url):
        """Versuche die echte Artikel-URL aus einer Google News Redirect-URL zu extrahieren."""
        if not google_url or 'news.google.com' not in google_url:
            return google_url

        try:
            resp = requests.head(google_url, allow_redirects=True, timeout=5,
                                 headers={'User-Agent': 'Mozilla/5.0'})
            if resp.url and 'news.google.com' not in resp.url:
                return resp.url
        except requests.RequestException:
            pass

        return google_url
