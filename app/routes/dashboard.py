"""Dashboard Routes - Hauptseite des Medienspiegels."""

from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, current_app, request

from ..database import get_articles, get_article_stats, get_collection_runs, get_db

dashboard_bp = Blueprint('dashboard', __name__)


def group_articles_by_topic(articles):
    """Gruppiere Artikel nach Thema, sortiert nach Gruppengroesse (Sonstiges am Ende)."""
    groups = {}
    for article in articles:
        topic = article.get('topic_cluster') or 'Sonstiges'
        if topic not in groups:
            groups[topic] = []
        groups[topic].append(article)

    sorted_topics = sorted(
        groups.keys(),
        key=lambda t: (t == 'Sonstiges', -len(groups[t]))
    )
    return [{'topic': t, 'articles': groups[t]} for t in sorted_topics]


# Verfuegbare Zeitraeume
TIME_RANGES = [
    ('24h', 'Letzte 24 Stunden'),
    ('3d', 'Letzte 3 Tage'),
    ('7d', 'Letzte 7 Tage'),
    ('14d', 'Letzte 14 Tage'),
    ('all', 'Alle Artikel'),
]


def _calculate_since(time_range):
    """Zeitraum-String in ISO-Datetime umrechnen."""
    now = datetime.utcnow()
    mapping = {
        '24h': timedelta(hours=24),
        '3d': timedelta(days=3),
        '7d': timedelta(days=7),
        '14d': timedelta(days=14),
    }
    if time_range in mapping:
        return (now - mapping[time_range]).isoformat()
    return None  # 'all' -> kein Filter


def _get_news_overview(db_path):
    """Hole eine gespeicherte KI-Gesamtzusammenfassung."""
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT value FROM kv_store WHERE key = 'news_overview'"
    ).fetchone()
    conn.close()
    return row['value'] if row else None


@dashboard_bp.route('/')
def index():
    """Haupt-Dashboard mit den gesammelten Artikeln."""
    db_path = current_app.config['DB_PATH']

    # Filter
    time_range = request.args.get('range', '3d')
    search = request.args.get('search', '')
    source = request.args.get('source', '')
    topic = request.args.get('topic', '')
    sort_by = request.args.get('sort', 'published_at')

    since = _calculate_since(time_range)

    articles = get_articles(
        db_path,
        since=since,
        source_type=source or None,
        topic=topic or None,
        search=search or None,
        sort_by=sort_by
    )

    stats = get_article_stats(db_path, since=since)

    # 24h-Stats fuer die Headline-Karten (immer 24h, unabhaengig vom Filter)
    now = datetime.utcnow()
    since_24h = (now - timedelta(hours=24)).isoformat()
    stats_24h = get_article_stats(db_path, since=since_24h)

    # Vorherige 24h fuer Trend-Vergleich (24h-48h)
    since_48h = (now - timedelta(hours=48)).isoformat()
    until_24h = since_24h
    stats_prev_24h = get_article_stats(db_path, since=since_48h, until=until_24h)

    runs = get_collection_runs(db_path, limit=1)
    last_run = runs[0] if runs else None

    # KI News-Ueberblick
    try:
        news_overview = _get_news_overview(db_path)
    except Exception:
        news_overview = None

    # Trend berechnen
    trend_mentions = stats_24h['total'] - stats_prev_24h['total']
    trend_sources = stats_24h['unique_sources'] - stats_prev_24h['unique_sources']

    topic_groups = group_articles_by_topic(articles)

    return render_template('dashboard.html',
                           articles=articles,
                           topic_groups=topic_groups,
                           stats=stats,
                           stats_24h=stats_24h,
                           trend_mentions=trend_mentions,
                           trend_sources=trend_sources,
                           last_run=last_run,
                           time_range=time_range,
                           time_ranges=TIME_RANGES,
                           filter_search=search,
                           filter_source=source,
                           filter_topic=topic,
                           sort_by=sort_by,
                           news_overview=news_overview)
