"""Artikel-Volltext Scraper — laedt Artikelseiten und extrahiert den Textinhalt."""

import re
import random
import time
import requests
from bs4 import BeautifulSoup

_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
]

# Tags die keinen Artikeltext enthalten
_REMOVE_TAGS = ['script', 'style', 'nav', 'footer', 'header', 'aside',
                'noscript', 'iframe', 'form', 'button', 'svg', 'figure',
                'figcaption', 'img', 'video', 'audio']


def scrape_article_text(url, timeout=10, max_chars=3000):
    """Lade eine Artikel-URL und extrahiere den Textinhalt.

    Args:
        url: Artikel-URL (auch Google News Redirect-URLs)
        timeout: Request-Timeout in Sekunden
        max_chars: Maximale Textlaenge

    Returns:
        str: Extrahierter Text oder None bei Fehler
    """
    if not url:
        return None

    # Twitter/X URLs nicht scrapen
    if 'x.com/' in url or 'twitter.com/' in url:
        return None

    try:
        # Google News Redirect-URLs aufloesen
        actual_url = _resolve_redirect(url, timeout)

        resp = requests.get(actual_url, timeout=timeout, headers={
            'User-Agent': random.choice(_USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
        })

        if resp.status_code != 200:
            return None

        # Nur HTML-Seiten parsen
        content_type = resp.headers.get('content-type', '')
        if 'text/html' not in content_type and 'application/xhtml' not in content_type:
            return None

        text = _extract_text(resp.text)
        if text and len(text) > 50:
            return text[:max_chars]

        return None

    except (requests.RequestException, Exception):
        return None


def _resolve_redirect(url, timeout=5):
    """Loese Redirect-URLs auf (Google News, Bing, etc.)."""
    redirect_domains = ['news.google.com', 'google.com/url', 'bing.com/news']

    if any(domain in url for domain in redirect_domains):
        try:
            resp = requests.head(url, allow_redirects=True, timeout=timeout, headers={
                'User-Agent': random.choice(_USER_AGENTS),
            })
            if resp.url and resp.url != url:
                return resp.url
        except requests.RequestException:
            pass

    return url


def _extract_text(html):
    """Extrahiere lesbaren Text aus HTML."""
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return None

    # Unerwuenschte Tags entfernen
    for tag in soup.find_all(_REMOVE_TAGS):
        tag.decompose()

    # Versuche den Artikeltext zu finden (priorisiert)
    content = None

    # 1. <article> Tag (beste Quelle)
    article = soup.find('article')
    if article:
        content = article

    # 2. Haupt-Content-Bereiche (class/id patterns)
    if not content:
        for selector in [
            '[class*="article-body"]', '[class*="article-content"]',
            '[class*="story-body"]', '[class*="post-content"]',
            '[class*="entry-content"]', '[class*="content-body"]',
            '[itemprop="articleBody"]', '[role="main"]',
            'main', '#content', '.content',
        ]:
            found = soup.select_one(selector)
            if found:
                content = found
                break

    # 3. Fallback: <body>
    if not content:
        content = soup.find('body')

    if not content:
        return None

    # Text extrahieren
    text = content.get_text(separator=' ', strip=True)

    # Bereinigen
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\b(Cookie|Datenschutz|Newsletter|Anmelden|Registrieren)\b.*?\.', '', text)
    text = text.strip()

    return text if len(text) > 50 else None


def scrape_batch(db_path, limit=30, delay=1.0):
    """Scrape Volltext fuer Artikel ohne full_text.

    Args:
        db_path: Pfad zur SQLite-Datenbank
        limit: Max Artikel pro Batch
        delay: Pause zwischen Requests (Sekunden)

    Returns:
        int: Anzahl erfolgreich gescrapte Artikel
    """
    from .database import get_articles_without_fulltext, update_article_fulltext

    articles = get_articles_without_fulltext(db_path, limit=limit)
    if not articles:
        return 0

    scraped = 0
    for article in articles:
        text = scrape_article_text(article['url'])
        if text:
            update_article_fulltext(db_path, article['id'], text)
            scraped += 1

        # Rate-Limiting
        if delay > 0:
            time.sleep(delay)

    if scraped > 0:
        print("  [SCRAPER] {} von {} Artikeln gescrapt".format(scraped, len(articles)))

    return scraped
