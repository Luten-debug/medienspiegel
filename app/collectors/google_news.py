"""Google News RSS Collector - Hauptquelle, kein API-Key noetig."""

import re
import html
import random
import time
import feedparser
import requests
from urllib.parse import quote
from dateutil import parser as dateparser

from .base import BaseCollector, CollectedArticle

# Rotierende User-Agents um Blocks zu vermeiden
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
]


class GoogleNewsCollector(BaseCollector):

    @property
    def name(self):
        return "Google News"

    def is_available(self):
        return True  # Kein API-Key noetig

    def _get_headers(self, lang='de', country='DE'):
        """Erstelle realistische Browser-Headers."""
        ua = random.choice(_USER_AGENTS)
        accept_lang = '{},{}; q=0.9,en;q=0.8'.format(
            lang, '{}-{}'.format(lang, country))
        return {
            'User-Agent': ua,
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': accept_lang,
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }

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

        headers = self._get_headers(lang, country)

        # Bis zu 3 Versuche mit steigendem Timeout
        last_error = None
        for attempt in range(3):
            try:
                timeout = 15 + (attempt * 10)  # 15s, 25s, 35s
                resp = requests.get(url, timeout=timeout, headers=headers)

                if resp.status_code == 429:
                    # Rate limited — kurz warten und erneut versuchen
                    wait = 2 + (attempt * 3)
                    print("  [Google News] Rate limited (429), warte {}s...".format(wait))
                    time.sleep(wait)
                    headers = self._get_headers(lang, country)  # Neuer UA
                    continue

                if resp.status_code == 403:
                    print("  [Google News] Zugriff verweigert (403) fuer: {}".format(search_term))
                    # Neuer User-Agent beim naechsten Versuch
                    headers = self._get_headers(lang, country)
                    time.sleep(1)
                    continue

                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                break

            except requests.exceptions.Timeout:
                last_error = "Timeout nach {}s".format(timeout)
                print("  [Google News] Timeout (Versuch {}/3): {}".format(
                    attempt + 1, search_term))
                continue
            except requests.exceptions.RequestException as e:
                last_error = str(e)[:80]
                print("  [Google News] Fehler (Versuch {}/3): {}".format(
                    attempt + 1, str(e)[:80]))
                time.sleep(1)
                continue
        else:
            # Alle Versuche gescheitert
            print("  [Google News] Endgueltig fehlgeschlagen: {} ({})".format(
                search_term, last_error))
            return []

        articles = []
        for entry in feed.entries[:max_articles]:
            title = entry.get('title', '')
            # Google News haengt oft " - Quellenname" an den Titel
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

        if articles:
            print("  [Google News] {} Artikel fuer '{}' ({})".format(
                len(articles), search_term, lang.upper()))
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
                                 headers={'User-Agent': random.choice(_USER_AGENTS)})
            if resp.url and 'news.google.com' not in resp.url:
                return resp.url
        except requests.RequestException:
            pass

        return google_url
