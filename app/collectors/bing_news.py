"""Bing News RSS Collector - Fallback wenn Google News von Server-IPs blockiert wird."""

import re
import html as htmlmod
import random
import feedparser
import requests
from urllib.parse import quote
from dateutil import parser as dateparser

from .base import BaseCollector, CollectedArticle

_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
]

# Markt-Codes fuer Bing News
_MARKET_MAP = {
    'de': 'de-DE',
    'en': 'en-GB',
    'pl': 'pl-PL',
}


class BingNewsCollector(BaseCollector):
    """Bing News RSS - funktioniert zuverlaessig auch von Server-IPs."""

    @property
    def name(self):
        return "Bing News"

    def is_available(self):
        return True  # Kein API-Key noetig

    def collect(self, search_term, lang=None, country=None):
        """Sammle Artikel von Bing News RSS fuer einen Suchbegriff."""
        lang = lang or 'de'
        country = country or 'DE'
        max_articles = self.config.get('collection', {}).get('max_articles_per_source', 30)

        encoded_term = quote(search_term)
        mkt = _MARKET_MAP.get(lang, '{}-{}'.format(lang, country))

        url = "https://www.bing.com/news/search?q={}&format=rss&mkt={}&count={}".format(
            encoded_term, mkt, min(max_articles, 50))

        headers = {
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': '{},{};q=0.9'.format(lang, mkt),
        }

        try:
            resp = requests.get(url, timeout=15, headers=headers)
            if resp.status_code != 200:
                print("  [Bing News] HTTP {} fuer: {}".format(resp.status_code, search_term))
                return []

            feed = feedparser.parse(resp.text)
            if not feed.entries:
                return []

            articles = []
            for entry in feed.entries[:max_articles]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                published = entry.get('published', '')
                summary = entry.get('summary', '')

                if not title or not link:
                    continue

                # Quellennamen extrahieren (Bing haengt " - Quelle" an den Titel)
                source_name = self._extract_source(title, entry)
                clean_title = self._clean_title(title)

                # Datum parsen
                published_iso = None
                if published:
                    try:
                        published_iso = dateparser.parse(published).isoformat()
                    except (ValueError, TypeError):
                        pass

                # Snippet bereinigen
                snippet = None
                if summary:
                    snippet = re.sub(r'<[^>]+>', ' ', summary)
                    snippet = htmlmod.unescape(snippet).strip()
                    snippet = re.sub(r'\s+', ' ', snippet)
                    if len(snippet) > 500:
                        snippet = snippet[:497] + '...'

                # X/Twitter-Links ueberspringen (werden vom Twitter-Collector geholt)
                if link and ('x.com/' in link or 'twitter.com/' in link):
                    continue
                stype = 'google_news'

                articles.append(CollectedArticle(
                    url=link,
                    title=clean_title or title,
                    snippet=snippet,
                    source_name=source_name,
                    source_type=stype,
                    search_term=search_term,
                    published_at=published_iso,
                    image_url=None,
                    language=lang
                ))

            if articles:
                print("  [Bing News] {} Artikel fuer '{}' ({})".format(
                    len(articles), search_term, lang.upper()))
            return articles

        except requests.exceptions.Timeout:
            print("  [Bing News] Timeout fuer: {}".format(search_term))
            return []
        except Exception as e:
            print("  [Bing News] Fehler: {}".format(str(e)[:80]))
            return []

    def _extract_source(self, title, entry=None):
        """Extrahiere Quellennamen aus Titel oder Feed-Entry."""
        # Bing liefert manchmal source im Entry
        if entry:
            source = entry.get('source', {})
            if isinstance(source, dict):
                src_title = source.get('title', '')
                if src_title:
                    return src_title

        # Fallback: aus Titel extrahieren (Format "Titel - Quelle")
        if ' - ' in title:
            return title.rsplit(' - ', 1)[-1].strip()
        return None

    def _clean_title(self, title):
        """Entferne Quellennamen vom Titel."""
        if ' - ' in title:
            return title.rsplit(' - ', 1)[0].strip()
        return title
