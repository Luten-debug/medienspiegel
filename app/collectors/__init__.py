"""Collector-Orchestrator: Fuehrt alle aktiven Collector fuer alle Suchbegriffe aus."""

import time
import threading
from ..database import create_collection_run, finish_collection_run, fail_collection_run, insert_articles
from .google_news import GoogleNewsCollector
from .bing_news import BingNewsCollector
from .newsapi import NewsApiCollector
from .rss_feed import RssFeedCollector

# Globaler Lock: verhindert parallele Sammlungen (Scheduler + manuell)
_global_collection_lock = threading.Lock()


def get_enabled_collectors(config):
    """Gib eine Liste aller aktivierten Collector zurueck."""
    collectors = []

    # Bing News RSS - primaere Quelle (funktioniert zuverlaessig von Servern)
    collectors.append(BingNewsCollector(config))

    # Google News RSS - sekundaere Quelle (wird von manchen Server-IPs blockiert)
    collectors.append(GoogleNewsCollector(config))

    # NewsAPI - nur wenn API-Key vorhanden
    newsapi_key = config.get('api_keys', {}).get('newsapi', '')
    if newsapi_key:
        collectors.append(NewsApiCollector(config))

    # RSS Feeds - nur wenn Feeds konfiguriert
    rss_feeds = config.get('rss_feeds', [])
    if rss_feeds:
        collectors.append(RssFeedCollector(config))

    # Twitter/X - nur wenn aktiviert
    twitter_config = config.get('twitter', {})
    if twitter_config.get('enabled'):
        try:
            from .twitter import TwitterCollector
            collectors.append(TwitterCollector(config))
        except ImportError:
            pass

    return collectors


def run_collection(config, db_path, progress_cb=None):
    """Fuehre eine komplette Mediensammlung durch.

    Args:
        progress_cb: Optional callback(term, terms_done, found_so_far)

    Returns:
        tuple: (run_id, articles_found, articles_new, errors)
    """
    # Verhindere parallele Sammlungen
    if not _global_collection_lock.acquire(blocking=False):
        print("  [COLLECTION] Uebersprungen - andere Sammlung laeuft noch")
        return None, 0, 0, ["Sammlung uebersprungen (bereits aktiv)"]

    run_id = create_collection_run(db_path)
    all_articles = []
    errors = []
    delay = config.get('collection', {}).get('request_delay', 0.3)
    terms_done = 0

    try:
        collectors = get_enabled_collectors(config)
        languages = config.get('languages', [])

        if not collectors:
            errors.append("Keine Collector verfuegbar")
            fail_collection_run(db_path, run_id, errors)
            return run_id, 0, 0, errors

        if not languages:
            errors.append("Keine Sprachen/Suchbegriffe konfiguriert")
            fail_collection_run(db_path, run_id, errors)
            return run_id, 0, 0, errors

        # Set fuer bereits gefundene URLs (Deduplizierung zwischen Bing + Google)
        seen_urls = set()

        for collector in collectors:
            if not collector.is_available():
                continue

            # Twitter: einmal alle Accounts abfragen
            if hasattr(collector, '_is_twitter') and collector._is_twitter:
                if progress_cb:
                    progress_cb('X/Twitter Accounts', terms_done, len(all_articles))
                try:
                    articles = collector.collect(search_term=None)
                    for a in articles:
                        if a.url not in seen_urls:
                            seen_urls.add(a.url)
                            all_articles.append(a)
                except Exception as e:
                    errors.append("{}: {}".format(collector.name, str(e)[:80]))
                terms_done += 1
                continue

            # Alle anderen Collector iterieren ueber Sprachen
            for lang_config in languages:
                lang = lang_config.get('lang', 'de')
                country = lang_config.get('country', 'DE')
                search_terms = lang_config.get('search_terms', [])

                for term in search_terms:
                    if progress_cb:
                        progress_cb(term, terms_done, len(all_articles))
                    try:
                        articles = collector.collect(term, lang=lang, country=country)
                        for a in articles:
                            if a.url not in seen_urls:
                                seen_urls.add(a.url)
                                all_articles.append(a)
                    except Exception as e:
                        errors.append("{} [{}]: '{}': {}".format(
                            collector.name, lang.upper(), term, str(e)[:80]))

                    terms_done += 1
                    time.sleep(delay)

        if progress_cb:
            progress_cb('', terms_done, len(all_articles))

        articles_new = insert_articles(db_path, all_articles, run_id)
        finish_collection_run(db_path, run_id, len(all_articles), articles_new, errors)

        return run_id, len(all_articles), articles_new, errors

    except Exception as e:
        # Sicherstellen dass der Run IMMER abgeschlossen wird
        try:
            fail_collection_run(db_path, run_id, errors + [str(e)])
        except Exception:
            pass
        return run_id, len(all_articles), 0, errors + [str(e)]

    finally:
        _global_collection_lock.release()
