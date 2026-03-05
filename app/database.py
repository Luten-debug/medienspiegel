"""SQLite Datenbank: Schema-Setup und Query-Helper."""

import sqlite3
import json
from datetime import datetime


def get_db(db_path):
    """Erstelle eine neue DB-Verbindung."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path):
    """Erstelle Tabellen falls sie nicht existieren."""
    conn = get_db(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            url             TEXT NOT NULL UNIQUE,
            title           TEXT NOT NULL,
            snippet         TEXT,
            ai_summary      TEXT,
            source_name     TEXT,
            source_type     TEXT NOT NULL,
            search_term     TEXT,
            estimated_reach TEXT,
            published_at    TEXT,
            collected_at    TEXT NOT NULL,
            is_relevant     INTEGER DEFAULT 0,
            image_url       TEXT,
            collection_run_id INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_articles_collected_at ON articles(collected_at);
        CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
        CREATE INDEX IF NOT EXISTS idx_articles_is_relevant ON articles(is_relevant);

        CREATE TABLE IF NOT EXISTS kv_store (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS collection_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            status          TEXT DEFAULT 'running',
            articles_found  INTEGER DEFAULT 0,
            articles_new    INTEGER DEFAULT 0,
            mail_sent       INTEGER DEFAULT 0,
            errors          TEXT
        );
    """)
    # Migrationen: Neue Spalten hinzufuegen
    for migration in [
        "ALTER TABLE articles ADD COLUMN language TEXT DEFAULT 'de'",
        "ALTER TABLE articles ADD COLUMN topic_cluster TEXT",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits

    conn.commit()
    conn.close()


def create_collection_run(db_path):
    """Starte einen neuen Collection-Run und gib die ID zurück."""
    conn = get_db(db_path)
    cursor = conn.execute(
        "INSERT INTO collection_runs (started_at, status) VALUES (?, 'running')",
        (datetime.utcnow().isoformat(),)
    )
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def finish_collection_run(db_path, run_id, articles_found, articles_new, errors=None):
    """Schließe einen Collection-Run ab."""
    conn = get_db(db_path)
    conn.execute(
        """UPDATE collection_runs
           SET finished_at = ?, status = 'completed',
               articles_found = ?, articles_new = ?, errors = ?
           WHERE id = ?""",
        (datetime.utcnow().isoformat(), articles_found, articles_new,
         json.dumps(errors or []), run_id)
    )
    conn.commit()
    conn.close()


def fail_collection_run(db_path, run_id, errors):
    """Markiere einen Collection-Run als fehlgeschlagen."""
    conn = get_db(db_path)
    conn.execute(
        """UPDATE collection_runs
           SET finished_at = ?, status = 'failed', errors = ?
           WHERE id = ?""",
        (datetime.utcnow().isoformat(), json.dumps(errors), run_id)
    )
    conn.commit()
    conn.close()


def insert_articles(db_path, articles, run_id):
    """Füge Artikel ein. Gibt Anzahl neuer (nicht-doppelter) Artikel zurück."""
    conn = get_db(db_path)
    new_count = 0
    for a in articles:
        try:
            changes_before = conn.total_changes
            conn.execute(
                """INSERT OR IGNORE INTO articles
                   (url, title, snippet, source_name, source_type, search_term,
                    published_at, collected_at, image_url, collection_run_id, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (a.url, a.title, a.snippet, a.source_name, a.source_type,
                 a.search_term, a.published_at, datetime.utcnow().isoformat(),
                 a.image_url, run_id, getattr(a, 'language', 'de'))
            )
            if conn.total_changes > changes_before:
                new_count += 1
        except sqlite3.Error:
            pass
    conn.commit()
    conn.close()
    return new_count


def get_articles(db_path, date=None, since=None, source_type=None, relevance=None,
                 search=None, topic=None, sort_by='published_at', sort_dir='DESC', limit=200):
    """Hole Artikel mit optionalen Filtern."""
    conn = get_db(db_path)
    query = "SELECT * FROM articles WHERE 1=1"
    params = []

    if since:
        query += " AND COALESCE(published_at, collected_at) >= ?"
        params.append(since)
    elif date:
        query += " AND DATE(COALESCE(published_at, collected_at)) = DATE(?)"
        params.append(date)

    if source_type:
        query += " AND source_type = ?"
        params.append(source_type)

    if relevance is not None:
        query += " AND is_relevant = ?"
        params.append(relevance)

    if topic:
        query += " AND topic_cluster = ?"
        params.append(topic)

    if search:
        query += " AND (title LIKE ? OR snippet LIKE ? OR ai_summary LIKE ?)"
        like = '%{}%'.format(search)
        params.extend([like, like, like])

    allowed_sorts = {'collected_at', 'published_at', 'source_name', 'is_relevant'}
    if sort_by not in allowed_sorts:
        sort_by = 'published_at'
    sort_dir = 'ASC' if sort_dir.upper() == 'ASC' else 'DESC'
    if sort_by == 'published_at':
        query += " ORDER BY COALESCE(published_at, collected_at) {}".format(sort_dir)
    else:
        query += " ORDER BY {} {}".format(sort_by, sort_dir)
    query += " LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_articles_without_summary(db_path, limit=50):
    """Hole Artikel die noch keine KI-Zusammenfassung haben."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT * FROM articles WHERE ai_summary IS NULL ORDER BY COALESCE(published_at, collected_at) DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_article_summary(db_path, article_id, summary, reach, topic=None):
    """Aktualisiere KI-Zusammenfassung, Reichweite und Themencluster."""
    conn = get_db(db_path)
    conn.execute(
        "UPDATE articles SET ai_summary = ?, estimated_reach = ?, topic_cluster = ? WHERE id = ?",
        (summary, reach, topic, article_id)
    )
    conn.commit()
    conn.close()


def update_article_relevance(db_path, article_id, relevance):
    """Setze Relevanz-Status: 1=relevant, -1=irrelevant, 0=unbewertet."""
    conn = get_db(db_path)
    conn.execute(
        "UPDATE articles SET is_relevant = ? WHERE id = ?",
        (relevance, article_id)
    )
    conn.commit()
    conn.close()


def get_existing_topics(db_path, limit=20):
    """Hole die haeufigsten existierenden Themencluster-Namen."""
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT topic_cluster, COUNT(*) as cnt FROM articles
           WHERE topic_cluster IS NOT NULL
           GROUP BY topic_cluster ORDER BY cnt DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [r['topic_cluster'] for r in rows if r['topic_cluster']]


def get_uncategorized_articles(db_path, limit=50):
    """Hole Artikel ohne Themenkategorie."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT id, title, source_name, snippet, language FROM articles WHERE topic_cluster IS NULL ORDER BY COALESCE(published_at, collected_at) DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_article_topic(db_path, article_id, topic):
    """Setze nur die Themenkategorie eines Artikels."""
    conn = get_db(db_path)
    conn.execute(
        "UPDATE articles SET topic_cluster = ? WHERE id = ?",
        (topic, article_id)
    )
    conn.commit()
    conn.close()


def get_collection_runs(db_path, limit=10):
    """Hole die letzten Collection-Runs."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_collection_run(db_path, run_id):
    """Hole einen einzelnen Collection-Run."""
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT * FROM collection_runs WHERE id = ?", (run_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_article_stats(db_path, date=None, since=None, until=None):
    """Hole Statistiken ueber gesammelte Artikel."""
    conn = get_db(db_path)
    where = ""
    params = []
    if since and until:
        where = "WHERE COALESCE(published_at, collected_at) >= ? AND COALESCE(published_at, collected_at) < ?"
        params = [since, until]
    elif since:
        where = "WHERE COALESCE(published_at, collected_at) >= ?"
        params = [since]
    elif date:
        where = "WHERE DATE(COALESCE(published_at, collected_at)) = DATE(?)"
        params = [date]

    stats = {}
    row = conn.execute(
        "SELECT COUNT(*) as total FROM articles " + where, params
    ).fetchone()
    stats['total'] = row['total']

    row = conn.execute(
        "SELECT COUNT(*) as relevant FROM articles {} {}".format(
            where,
            "AND is_relevant = 1" if where else "WHERE is_relevant = 1"
        ), params
    ).fetchone()
    stats['relevant'] = row['relevant']

    rows = conn.execute(
        "SELECT source_type, COUNT(*) as count FROM articles {} GROUP BY source_type".format(where),
        params
    ).fetchall()
    stats['by_source'] = {r['source_type']: r['count'] for r in rows}

    # Unique Medien-Quellen zaehlen
    row = conn.execute(
        "SELECT COUNT(DISTINCT source_name) as sources FROM articles " + where, params
    ).fetchone()
    stats['unique_sources'] = row['sources']

    # Artikel mit KI-Zusammenfassung
    row = conn.execute(
        "SELECT COUNT(*) as summarized FROM articles {} {}".format(
            where,
            "AND ai_summary IS NOT NULL" if where else "WHERE ai_summary IS NOT NULL"
        ), params
    ).fetchone()
    stats['summarized'] = row['summarized']

    # Themencluster zaehlen
    rows = conn.execute(
        "SELECT topic_cluster, COUNT(*) as cnt FROM articles {} {} GROUP BY topic_cluster ORDER BY cnt DESC".format(
            where,
            "AND topic_cluster IS NOT NULL" if where else "WHERE topic_cluster IS NOT NULL"
        ), params
    ).fetchall()
    stats['topics'] = {r['topic_cluster']: r['cnt'] for r in rows if r['topic_cluster']}

    conn.close()
    return stats
