"""NewsAPI.org Collector - benötigt kostenlosen API-Key."""

import requests
from dateutil import parser as dateparser

from .base import BaseCollector, CollectedArticle


class NewsApiCollector(BaseCollector):

    API_URL = "https://newsapi.org/v2/everything"

    @property
    def name(self):
        return "NewsAPI"

    def is_available(self):
        key = self.config.get('api_keys', {}).get('newsapi', '')
        return bool(key)

    def collect(self, search_term, lang=None, country=None):
        """Sammle Artikel von NewsAPI fuer einen Suchbegriff."""
        api_key = self.config.get('api_keys', {}).get('newsapi', '')
        lang = lang or self.config.get('language', 'de')
        max_articles = self.config.get('collection', {}).get('max_articles_per_source', 50)

        params = {
            'q': search_term,
            'language': lang,
            'sortBy': 'publishedAt',
            'pageSize': min(max_articles, 100),
            'apiKey': api_key
        }

        resp = requests.get(self.API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get('status') != 'ok':
            raise ValueError("NewsAPI Fehler: {}".format(data.get('message', 'Unbekannt')))

        articles = []
        for item in data.get('articles', []):
            published_iso = None
            if item.get('publishedAt'):
                try:
                    published_iso = dateparser.parse(item['publishedAt']).isoformat()
                except (ValueError, TypeError):
                    pass

            articles.append(CollectedArticle(
                url=item.get('url', ''),
                title=item.get('title', ''),
                snippet=item.get('description', ''),
                source_name=item.get('source', {}).get('name', ''),
                source_type='newsapi',
                search_term=search_term,
                published_at=published_iso,
                image_url=item.get('urlToImage'),
                language=lang
            ))

        return articles
