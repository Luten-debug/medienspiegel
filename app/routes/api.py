"""API Routes - HTMX Endpoints für interaktive Aktionen."""

import threading
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, current_app, request, jsonify

from ..database import (
    get_articles, update_article_relevance, get_collection_run,
    get_articles_without_summary, get_article_stats, get_collection_runs,
    get_alerts, create_alert, delete_alert, toggle_alert, check_alerts
)
from ..collectors import run_collection

api_bp = Blueprint('api', __name__)

# Einfacher Lock um gleichzeitige Collections zu verhindern
_collection_lock = threading.Lock()
# Fortschritts-Tracking fuer die Sammlung
_collection_progress = {
    'phase': '',           # 'collecting', 'done', 'error'
    'detail': '',          # Detailtext
    'found': 0,            # Gefundene Artikel
    'new': 0,              # Neue Artikel
    'current_term': '',    # Aktueller Suchbegriff
    'terms_done': 0,       # Abgeschlossene Suchbegriffe
    'terms_total': 0,      # Gesamtanzahl Suchbegriffe
}


@api_bp.route('/collect', methods=['POST'])
def collect():
    """Starte eine neue Mediensammlung."""
    if not _collection_lock.acquire(blocking=False):
        return '<div class="notice" role="alert">Sammlung läuft bereits...</div>', 409

    config = current_app.config['MEDIENSPIEGEL']
    db_path = current_app.config['DB_PATH']

    # Anzahl Suchbegriffe berechnen
    languages = config.get('languages', [])
    total_terms = sum(len(lc.get('search_terms', [])) for lc in languages)
    # Twitter zaehlt als 1 (holt alle Accounts auf einmal)
    twitter_enabled = config.get('twitter', {}).get('enabled', False)
    all_terms = total_terms + (1 if twitter_enabled else 0)

    # Fortschritt zuruecksetzen
    _collection_progress.update({
        'phase': 'collecting', 'detail': '',
        'found': 0, 'new': 0, 'current_term': '',
        'terms_done': 0, 'terms_total': all_terms
    })

    app = current_app._get_current_object()

    def _progress_cb(term, terms_done, found_so_far):
        _collection_progress['current_term'] = term
        _collection_progress['terms_done'] = terms_done
        _collection_progress['found'] = found_so_far

    def _do_collection():
        try:
            with app.app_context():
                run_id, found, new, errors = run_collection(
                    config, db_path, progress_cb=_progress_cb)
                _collection_progress['found'] = found
                _collection_progress['new'] = new

                # Auto-Kategorisierung + Zitate generieren
                api_key = config.get('api_keys', {}).get('anthropic', '')
                if api_key and new > 0:
                    # Erst kaputte Meta-Kommentar-Zitate bereinigen + Themen remappen
                    try:
                        from ..summarizer import cleanup_meta_summaries, remap_all_topics
                        cleanup_meta_summaries(db_path)
                        remap_all_topics(db_path)
                    except Exception as e:
                        print("  [WARN] Cleanup: {}".format(str(e)[:80]))

                    _collection_progress['current_term'] = 'Kategorisierung...'
                    try:
                        from ..summarizer import categorize_uncategorized
                        categorize_uncategorized(db_path, api_key)
                    except Exception as e:
                        print("  [WARN] Auto-Kategorisierung: {}".format(str(e)[:80]))

                    # Automatisch Zitate fuer neue Artikel generieren
                    _collection_progress['current_term'] = 'Zitate generieren...'
                    try:
                        from ..summarizer import summarize_new_articles
                        summarize_new_articles(db_path, api_key)
                    except Exception as e:
                        print("  [WARN] Auto-Zitate: {}".format(str(e)[:80]))

                # Alerts pruefen fuer neue Artikel
                if new > 0:
                    try:
                        _collection_progress['current_term'] = 'Alerts prüfen...'
                        from ..database import get_db
                        conn = get_db(db_path)
                        # IDs der neuesten Artikel holen
                        new_rows = conn.execute(
                            "SELECT id FROM articles ORDER BY id DESC LIMIT ?",
                            (new,)).fetchall()
                        conn.close()
                        new_ids = [r['id'] for r in new_rows]
                        alert_hits = check_alerts(db_path, new_ids)

                        # Alert-Mails senden
                        if alert_hits and config.get('mail', {}).get('enabled'):
                            from ..mailer import send_alert_mail
                            # Gruppiere nach Alert
                            alert_groups = {}
                            for alert_d, art_d in alert_hits:
                                aid = alert_d['id']
                                if aid not in alert_groups:
                                    alert_groups[aid] = (alert_d, [])
                                alert_groups[aid][1].append(art_d)
                            for aid, (alert_d, arts) in alert_groups.items():
                                try:
                                    send_alert_mail(config, alert_d, arts)
                                except Exception as e:
                                    print("  [ALERT] Mail-Fehler: {}".format(str(e)[:80]))
                    except Exception as e:
                        print("  [WARN] Alert-Check: {}".format(str(e)[:80]))

                _collection_progress['phase'] = 'done'
                _collection_progress['detail'] = '{} gefunden, {} neu'.format(found, new)
        except Exception as e:
            _collection_progress['phase'] = 'error'
            _collection_progress['detail'] = str(e)[:100]
        finally:
            _collection_lock.release()

    thread = threading.Thread(target=_do_collection, daemon=True)
    thread.start()

    return render_template('partials/collection_status.html',
                           status='running',
                           message='Sammlung gestartet...',
                           progress=0, terms_total=all_terms)


@api_bp.route('/collection-status')
def collection_status():
    """Prüfe den Status der laufenden Sammlung (für HTMX Polling)."""
    if _collection_lock.locked():
        terms_done = _collection_progress.get('terms_done', 0)
        terms_total = _collection_progress.get('terms_total', 1)
        current_term = _collection_progress.get('current_term', '')
        found = _collection_progress.get('found', 0)
        pct = int(terms_done / max(terms_total, 1) * 100)

        msg = '{}% – {} von {} Quellen durchsucht'.format(pct, terms_done, terms_total)
        if found > 0:
            msg += ' ({} gefunden)'.format(found)

        return render_template('partials/collection_status.html',
                               status='running', message=msg,
                               progress=pct, current_term=current_term,
                               terms_total=terms_total)

    # Sammlung abgeschlossen
    phase = _collection_progress.get('phase', '')
    if phase == 'error':
        return render_template('partials/collection_status.html',
                               status='error',
                               message='Fehler: {}'.format(_collection_progress.get('detail', '')))

    found = _collection_progress.get('found', 0)
    new = _collection_progress.get('new', 0)

    if found > 0:
        msg = '{} Artikel gefunden, {} neu'.format(found, new)
    else:
        msg = 'Keine neuen Artikel gefunden'

    return render_template('partials/collection_status.html',
                           status='done', message=msg)


# Lock und Fehlerspeicher fuer KI-Zusammenfassungen
_summary_lock = threading.Lock()
_summary_error = [None]
_summary_count = [0]
_summary_progress = {'done': 0, 'total': 0}


@api_bp.route('/reset-summaries', methods=['POST'])
def reset_summaries():
    """Setze alle KI-Zusammenfassungen zurueck (damit neue Zitate generiert werden)."""
    db_path = current_app.config['DB_PATH']
    from ..database import get_db
    conn = get_db(db_path)
    result = conn.execute("UPDATE articles SET ai_summary = NULL")
    count = result.rowcount
    conn.commit()
    conn.close()
    return '<div class="notice success">{} Zusammenfassungen zurückgesetzt. Klicke jetzt "Jetzt sammeln" für neue Zitate.</div>'.format(count)


@api_bp.route('/cleanup-meta', methods=['POST'])
def cleanup_meta():
    """Bereinige kaputte Meta-Kommentar-Zitate und generiere sie neu."""
    db_path = current_app.config['DB_PATH']
    config = current_app.config['MEDIENSPIEGEL']
    api_key = config.get('api_keys', {}).get('anthropic', '')

    from ..summarizer import cleanup_meta_summaries
    cleaned = cleanup_meta_summaries(db_path)

    if cleaned > 0 and api_key:
        # Sofort neue Zitate generieren
        try:
            from ..summarizer import summarize_new_articles
            summarize_new_articles(db_path, api_key)
        except Exception as e:
            return '<div class="notice success">{} kaputte Zitate bereinigt, aber Neugenerierung fehlgeschlagen: {}</div>'.format(cleaned, str(e)[:80])
        return '<div class="notice success">{} kaputte Zitate bereinigt und neu generiert!<script>setTimeout(function(){{ window.location.reload(); }}, 1500);</script></div>'.format(cleaned)

    return '<div class="notice success">Keine kaputten Zitate gefunden.</div>'


@api_bp.route('/summarize', methods=['POST'])
def summarize():
    """Generiere KI-Zusammenfassungen fuer alle Artikel ohne Summary."""
    if not _summary_lock.acquire(blocking=False):
        return '<div class="notice running">KI-Zusammenfassungen laufen bereits...</div>', 409

    config = current_app.config['MEDIENSPIEGEL']
    db_path = current_app.config['DB_PATH']
    api_key = config.get('api_keys', {}).get('anthropic', '')

    if not api_key:
        _summary_lock.release()
        return '<div class="notice" style="background:#fff3cd;color:#856404;">Kein Anthropic API Key konfiguriert.</div>'

    unsummarized = len(get_articles_without_summary(db_path))
    if unsummarized == 0:
        _summary_lock.release()
        return '<div class="notice success">Alle Artikel sind bereits zusammengefasst.</div>'

    _summary_error[0] = None
    _summary_count[0] = 0
    _summary_progress['done'] = 0
    _summary_progress['total'] = unsummarized
    app = current_app._get_current_object()

    def _progress_cb(done, total):
        _summary_progress['done'] = done
        _summary_progress['total'] = total

    def _do_summarize():
        try:
            with app.app_context():
                from ..summarizer import summarize_new_articles
                total = 0
                while True:
                    count = summarize_new_articles(db_path, api_key, progress_cb=_progress_cb)
                    total += count
                    _summary_count[0] = total
                    if count == 0:
                        break
        except Exception as e:
            _summary_error[0] = str(e)
        finally:
            _summary_lock.release()

    thread = threading.Thread(target=_do_summarize, daemon=True)
    thread.start()

    return '<div class="notice running" hx-get="/api/summary-status" hx-trigger="every 3s" hx-swap="outerHTML"><div style="width:100%"><span>KI-Zusammenfassungen: 0 von {} Artikeln...</span><div class="progress-bar"><div class="progress-fill" style="width:0%"></div></div></div></div>'.format(unsummarized)


@api_bp.route('/summary-status')
def summary_status():
    """Pruefe ob KI-Zusammenfassungen noch laufen."""
    if _summary_lock.locked():
        done = _summary_progress.get('done', 0)
        total = _summary_progress.get('total', 1)
        pct = int(done / max(total, 1) * 100)
        return '<div class="notice running" hx-get="/api/summary-status" hx-trigger="every 3s" hx-swap="outerHTML"><div style="width:100%"><span>KI-Zusammenfassungen: {} von {} Artikeln ({}%)</span><div class="progress-bar"><div class="progress-fill" style="width:{}%"></div></div></div></div>'.format(done, total, pct, pct)

    if _summary_error[0]:
        err = _summary_error[0]
        if 'credit balance' in err.lower() or 'too low' in err.lower():
            return '<div class="notice" style="background:#fff3cd;color:#856404;">Anthropic API: Kein Guthaben. Bitte unter <a href="https://console.anthropic.com/settings/billing" target="_blank">console.anthropic.com</a> Credits aufladen.</div>'
        return '<div class="notice" role="alert">KI-Fehler: {}</div>'.format(err[:100])

    return '<div class="notice success">KI-Zusammenfassungen fertig! ({} Artikel)<script>setTimeout(function(){{ window.location.reload(); }}, 1500);</script></div>'.format(_summary_count[0])


@api_bp.route('/articles')
def articles():
    """Hole gefilterte Artikel-Liste (HTMX Partial)."""
    db_path = current_app.config['DB_PATH']

    time_range = request.args.get('range', '3d')
    source_type = request.args.get('source', '')
    topic = request.args.get('topic', '')
    search = request.args.get('search', '')
    sort_by = request.args.get('sort', 'published_at')

    from .dashboard import _calculate_since
    since = _calculate_since(time_range)

    articles = get_articles(
        db_path,
        since=since,
        source_type=source_type or None,
        topic=topic or None,
        search=search or None,
        sort_by=sort_by
    )

    from .dashboard import group_articles_by_topic
    topic_groups = group_articles_by_topic(articles)

    return render_template('partials/article_list.html',
                           articles=articles, topic_groups=topic_groups)


@api_bp.route('/articles/<int:article_id>/summarize', methods=['POST'])
def summarize_single(article_id):
    """Generiere Zusammenfassung fuer einen einzelnen Artikel."""
    config = current_app.config['MEDIENSPIEGEL']
    db_path = current_app.config['DB_PATH']
    api_key = config.get('api_keys', {}).get('anthropic', '')

    if not api_key:
        return '<span class="snippet">Kein API Key konfiguriert.</span>'

    from ..database import get_db
    conn = get_db(db_path)
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    conn.close()

    if not row:
        return '<span class="snippet">Artikel nicht gefunden.</span>'

    try:
        from ..summarizer import _summarize_article
        from ..database import update_article_summary
        article = dict(row)
        article['_db_path'] = db_path
        summary, reach, topic = _summarize_article(article, api_key)
        update_article_summary(db_path, article_id, summary, reach, topic)
        return '<div class="ai-summary">{}</div>'.format(summary)
    except Exception as e:
        return '<span class="snippet">Fehler: {}</span>'.format(str(e)[:100])


@api_bp.route('/articles/<int:article_id>/relevant', methods=['POST'])
def mark_relevant(article_id):
    """Markiere Artikel als relevant."""
    db_path = current_app.config['DB_PATH']
    update_article_relevance(db_path, article_id, 1)
    return '''<button class="action-btn relevant active"
            hx-post="/api/articles/{0}/reset"
            hx-target="#relevance-{0}"
            hx-swap="innerHTML">Relevant</button>'''.format(article_id)


@api_bp.route('/articles/<int:article_id>/irrelevant', methods=['POST'])
def mark_irrelevant(article_id):
    """Markiere Artikel als irrelevant."""
    db_path = current_app.config['DB_PATH']
    update_article_relevance(db_path, article_id, -1)
    return '''<button class="action-btn irrelevant active"
            hx-post="/api/articles/{0}/reset"
            hx-target="#relevance-{0}"
            hx-swap="innerHTML">Irrelevant</button>'''.format(article_id)


@api_bp.route('/articles/<int:article_id>/reset', methods=['POST'])
def reset_relevance(article_id):
    """Setze Relevanz zurueck."""
    db_path = current_app.config['DB_PATH']
    update_article_relevance(db_path, article_id, 0)
    return '''<button class="action-btn relevant"
            hx-post="/api/articles/{0}/relevant"
            hx-target="#relevance-{0}"
            hx-swap="innerHTML">Relevant</button>
    <button class="action-btn irrelevant"
            hx-post="/api/articles/{0}/irrelevant"
            hx-target="#relevance-{0}"
            hx-swap="innerHTML">Irrelevant</button>'''.format(article_id)


# === Alert API Routes ===

@api_bp.route('/alerts')
def alerts_list():
    """Liste aller Alerts (HTMX Partial)."""
    db_path = current_app.config['DB_PATH']
    alerts = get_alerts(db_path)
    return render_template('partials/alerts_list.html', alerts=alerts)


@api_bp.route('/alerts', methods=['POST'])
def alerts_create():
    """Erstelle einen neuen Alert."""
    db_path = current_app.config['DB_PATH']
    name = request.form.get('name', '').strip()
    if not name:
        return '<div class="notice" role="alert">Bitte einen Namen eingeben.</div>', 400

    source_pattern = request.form.get('source_pattern', '').strip() or None
    topic_pattern = request.form.get('topic_pattern', '').strip() or None
    keyword_pattern = request.form.get('keyword_pattern', '').strip() or None
    email_to = request.form.get('email_to', '').strip() or None

    create_alert(db_path, name, source_pattern, topic_pattern, keyword_pattern, email_to)

    alerts = get_alerts(db_path)
    return render_template('partials/alerts_list.html', alerts=alerts)


@api_bp.route('/alerts/<int:alert_id>', methods=['DELETE'])
def alerts_delete(alert_id):
    """Loesche einen Alert."""
    db_path = current_app.config['DB_PATH']
    delete_alert(db_path, alert_id)
    alerts = get_alerts(db_path)
    return render_template('partials/alerts_list.html', alerts=alerts)


@api_bp.route('/alerts/<int:alert_id>/toggle', methods=['POST'])
def alerts_toggle(alert_id):
    """Schalte einen Alert an/aus."""
    db_path = current_app.config['DB_PATH']
    toggle_alert(db_path, alert_id)
    alerts = get_alerts(db_path)
    return render_template('partials/alerts_list.html', alerts=alerts)


@api_bp.route('/send-mail', methods=['POST'])
def send_mail():
    """Sende den Medienspiegel per Mail mit waehlbarem Zeitraum."""
    config = current_app.config['MEDIENSPIEGEL']
    db_path = current_app.config['DB_PATH']

    if not config.get('mail', {}).get('enabled'):
        return '<div class="notice" style="background:#fff3cd;color:#856404;">Mail nicht konfiguriert. Bitte in <code>config.yaml</code> die Mail-Einstellungen eintragen und <code>enabled: true</code> setzen.</div>'

    time_range = request.args.get('range', 'today')

    try:
        from ..mailer import send_medienspiegel_mail

        # Zeitraum bestimmen
        filter_date = None
        range_label = "Heute"

        if time_range == 'today':
            filter_date = date.today().isoformat()
            range_label = "Heute"
        elif time_range == '24h':
            filter_date = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            range_label = "Letzte 24h"
        elif time_range == 'since_last':
            # Finde letzten Mail-Versand
            runs = get_collection_runs(db_path, limit=50)
            last_mail = None
            for run in runs:
                if run.get('mail_sent'):
                    last_mail = run.get('finished_at')
                    break
            if last_mail:
                filter_date = last_mail
                range_label = "Seit letztem Versand"
            else:
                filter_date = date.today().isoformat()
                range_label = "Heute (kein vorheriger Versand)"
        elif time_range == 'since_collect':
            runs = get_collection_runs(db_path, limit=2)
            if len(runs) > 1:
                filter_date = runs[1].get('finished_at', date.today().isoformat())
                range_label = "Seit vorletzter Sammlung"
            else:
                filter_date = date.today().isoformat()
                range_label = "Heute"
        elif time_range == 'all':
            filter_date = None
            range_label = "Alle Artikel"

        # Artikel holen (fuer 24h und since_* nach collected_at filtern)
        if time_range in ('24h', 'since_last', 'since_collect') and filter_date:
            articles = get_articles(db_path, since=filter_date)
        elif time_range == 'all':
            articles = get_articles(db_path)
        else:
            articles = get_articles(db_path, date=filter_date)

        stats = get_article_stats(db_path,
                                  date=filter_date if time_range == 'today' else None)
        send_medienspiegel_mail(config, articles, stats, range_label=range_label)

        # Mail-Versand in der DB markieren
        latest_runs = get_collection_runs(db_path, limit=1)
        if latest_runs:
            from ..database import get_db
            conn = get_db(db_path)
            conn.execute("UPDATE collection_runs SET mail_sent = 1 WHERE id = ?",
                         (latest_runs[0]['id'],))
            conn.commit()
            conn.close()

        return '<div class="notice success">Mail gesendet ({}, {} Artikel)</div>'.format(
            range_label, len(articles))
    except Exception as e:
        return '<div class="notice" role="alert">Mail-Fehler: {}</div>'.format(str(e)), 500


@api_bp.route('/debug-config')
def debug_config():
    """Temporaerer Debug-Endpoint: Zeige Konfiguration auf Render."""
    import os
    import traceback
    try:
        config = current_app.config['MEDIENSPIEGEL']
        languages = config.get('languages', [])
        total_terms = sum(len(lc.get('search_terms', [])) for lc in languages)
        twitter = config.get('twitter', {})
        api_key = config.get('api_keys', {}).get('anthropic', '')
        schedule = config.get('schedule', {})
        db_path = current_app.config['DB_PATH']

        # DB-Info (sicher)
        total_articles = 0
        twitter_articles = 0
        run_info = []
        try:
            from ..database import get_db
            conn = get_db(db_path)
            total_articles = conn.execute("SELECT COUNT(*) as c FROM articles").fetchone()['c']
            twitter_articles = conn.execute("SELECT COUNT(*) as c FROM articles WHERE source_type='twitter'").fetchone()['c']
            conn.close()
        except Exception as e:
            run_info.append('DB error: {}'.format(str(e)[:200]))

        try:
            runs = get_collection_runs(db_path, limit=3)
            for r in runs:
                run_info.append('{}: {} found, {} new, status={}'.format(
                    r.get('started_at', '?')[:19], r.get('articles_found', 0),
                    r.get('articles_new', 0), r.get('status', '?')))
        except Exception as e:
            run_info.append('Runs error: {}'.format(str(e)[:100]))

        # Erste 3 Suchbegriffe pro Sprache
        terms_preview = []
        for lc in languages:
            terms = lc.get('search_terms', [])
            terms_preview.append({
                'lang': lc.get('lang'),
                'count': len(terms),
                'first_3': terms[:3]
            })

        info = {
            'languages': len(languages),
            'total_search_terms': total_terms,
            'terms_preview': terms_preview,
            'twitter_enabled': twitter.get('enabled', False),
            'twitter_accounts': twitter.get('accounts', []),
            'has_api_key': bool(api_key),
            'key_prefix': api_key[:10] + '...' if api_key else 'EMPTY',
            'schedule_on': schedule.get('enabled', False),
            'refresh_min': schedule.get('refresh_interval', 'N/A'),
            'db_path': db_path,
            'db_exists': os.path.exists(db_path),
            'articles': total_articles,
            'tweets': twitter_articles,
            'runs': run_info,
            'env_key': bool(os.environ.get('ANTHROPIC_API_KEY')),
            'data_dir': os.environ.get('DATA_DIR', 'not set'),
        }
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()[-500:]}), 500
