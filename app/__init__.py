"""Flask App Factory fuer den Medienspiegel."""

import os
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
from flask import Flask

# Deutsche Zeitzone (CET/CEST)
CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))


def _to_german_time(dt):
    """Konvertiere naive UTC-Datetime in deutsche Zeit (CET/CEST)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Einfache DST-Regel: Letzte Sonntage Maerz-Oktober = CEST
    year = dt.year
    # Letzter Sonntag im Maerz
    mar31 = datetime(year, 3, 31, tzinfo=timezone.utc)
    dst_start = mar31 - timedelta(days=(mar31.weekday() + 1) % 7)
    dst_start = dst_start.replace(hour=1)
    # Letzter Sonntag im Oktober
    oct31 = datetime(year, 10, 31, tzinfo=timezone.utc)
    dst_end = oct31 - timedelta(days=(oct31.weekday() + 1) % 7)
    dst_end = dst_end.replace(hour=1)
    if dst_start <= dt.replace(tzinfo=timezone.utc) < dst_end:
        return dt.astimezone(CEST)
    return dt.astimezone(CET)

from .config import load_config
from .database import init_db

# Bekannte Medien -> Domain-Mapping fuer Favicons
KNOWN_SOURCES = {
    'spiegel': 'spiegel.de', 'der spiegel': 'spiegel.de',
    'tagesschau': 'tagesschau.de', 'tagesschau.de': 'tagesschau.de',
    'tagesspiegel': 'tagesspiegel.de',
    'berliner morgenpost': 'morgenpost.de', 'morgenpost': 'morgenpost.de',
    'berliner zeitung': 'berliner-zeitung.de',
    'rbb24': 'rbb24.de', 'rbb': 'rbb24.de',
    'bild': 'bild.de', 'bild.de': 'bild.de',
    'welt': 'welt.de', 'die welt': 'welt.de',
    'zeit': 'zeit.de', 'die zeit': 'zeit.de', 'zeit online': 'zeit.de',
    'faz': 'faz.net', 'frankfurter allgemeine': 'faz.net',
    'handelsblatt': 'handelsblatt.com',
    'focus': 'focus.de', 'focus online': 'focus.de',
    'stern': 'stern.de',
    'n-tv': 'n-tv.de', 'ntv': 'n-tv.de',
    'zdf': 'zdf.de',
    'ard': 'ard.de',
    'sueddeutsche': 'sueddeutsche.de', 'sz': 'sueddeutsche.de',
    't-online': 't-online.de',
    'reuters': 'reuters.com',
    'business insider': 'businessinsider.de',
    'teslamag': 'teslamag.de', 'teslamag.de': 'teslamag.de',
    'electrive': 'electrive.net', 'electrive.net': 'electrive.net',
    'ecomento': 'ecomento.de', 'ecomento.de': 'ecomento.de',
    'golem': 'golem.de', 'golem.de': 'golem.de',
    'heise': 'heise.de', 'heise online': 'heise.de',
    'manager magazin': 'manager-magazin.de',
    'wirtschaftswoche': 'wiwo.de', 'wiwo': 'wiwo.de',
    'maz': 'maz-online.de', 'maerkische allgemeine': 'maz-online.de',
    'moz': 'moz.de', 'maerkische oderzeitung': 'moz.de',
    'pnn': 'pnn.de', 'potsdamer neueste nachrichten': 'pnn.de',
    'kfz-betrieb': 'kfz-betrieb.vogel.de',
    'automotive world': 'automotiveworld.com',
    'tradingview': 'tradingview.com',
    'electrek': 'electrek.co',
    'upday news': 'upday.com', 'upday': 'upday.com',
    'benzinga': 'benzinga.com',
    'automobilwoche': 'automobilwoche.de',
    'finviz': 'finviz.com',
    'rnd': 'rnd.de', 'rnd.de': 'rnd.de',
    'market screener': 'marketscreener.com',
    'der standard': 'derstandard.at',
    'auto josh': 'autojosh.com',
    'yahoo finance': 'finance.yahoo.com', 'yahoo': 'yahoo.com',
    'cnbc': 'cnbc.com',
    'bloomberg': 'bloomberg.com',
    'the guardian': 'theguardian.com',
    'bbc': 'bbc.com',
    'auto motor und sport': 'auto-motor-und-sport.de',
    'autobild': 'autobild.de', 'auto bild': 'autobild.de',
}

GERMAN_MONTHS = [
    '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]


def create_app():
    app = Flask(__name__)

    # Jinja2 Filter registrieren
    @app.template_filter('format_datetime')
    def format_datetime_filter(value):
        """ISO-Datum (UTC) in lesbares deutsches Format mit Zeitzone umwandeln."""
        if not value:
            return ''
        try:
            if isinstance(value, str):
                dt = dateparser.parse(value)
            else:
                dt = value
            dt = _to_german_time(dt)
            return '{}. {} {}, {:02d}:{:02d}'.format(
                dt.day, GERMAN_MONTHS[dt.month], dt.year, dt.hour, dt.minute)
        except (ValueError, TypeError):
            return str(value)[:16] if value else ''

    @app.template_filter('format_date_short')
    def format_date_short_filter(value):
        """ISO-Datum in kurzes deutsches Format: '5. März 2026'."""
        if not value:
            return ''
        try:
            if isinstance(value, str):
                dt = dateparser.parse(value)
            else:
                dt = value
            dt = _to_german_time(dt)
            return '{}. {} {}'.format(dt.day, GERMAN_MONTHS[dt.month], dt.year)
        except (ValueError, TypeError):
            return str(value)[:10] if value else ''

    GERMAN_MONTHS_SHORT = [
        '', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
        'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'
    ]

    @app.template_filter('format_datetime_short')
    def format_datetime_short_filter(value):
        """ISO-Datum in kompaktes Format mit Uhrzeit: '5. Mär, 14:30'."""
        if not value:
            return ''
        try:
            if isinstance(value, str):
                dt = dateparser.parse(value)
            else:
                dt = value
            dt = _to_german_time(dt)
            return '{}. {}, {:02d}:{:02d}'.format(
                dt.day, GERMAN_MONTHS_SHORT[dt.month], dt.hour, dt.minute)
        except (ValueError, TypeError):
            return str(value)[:16] if value else ''

    @app.template_filter('tweet_handle')
    def tweet_handle_filter(source_name):
        """Extrahiere @handle aus source_name (Format: @handle|Name|avatar)."""
        if not source_name:
            return '@x'
        if '|' in source_name:
            return source_name.split('|')[0]
        if source_name.startswith('@'):
            return source_name
        return '@' + source_name.replace('x.com', '').replace('@', '').strip() or 'x'

    @app.template_filter('tweet_name')
    def tweet_name_filter(source_name):
        """Extrahiere Anzeigename aus source_name."""
        if not source_name:
            return 'X'
        if '|' in source_name:
            parts = source_name.split('|')
            return parts[1] if len(parts) > 1 and parts[1] else parts[0].lstrip('@')
        return source_name.replace('x.com', '').replace('@', '').strip() or 'X'

    @app.template_filter('tweet_avatar')
    def tweet_avatar_filter(source_name):
        """Extrahiere Avatar-URL aus source_name."""
        if not source_name or '|' not in source_name:
            return ''
        parts = source_name.split('|')
        return parts[2] if len(parts) > 2 else ''

    @app.template_filter('tweet_id')
    def tweet_id_filter(url):
        """Extrahiere Tweet-ID aus x.com/twitter.com URL."""
        if not url:
            return ''
        import re
        match = re.search(r'(?:x\.com|twitter\.com)/\w+/status/(\d+)', url)
        return match.group(1) if match else ''

    @app.template_filter('domain_from_name')
    def domain_from_name_filter(source_name):
        """Medienname -> Domain fuer Favicon-Lookup."""
        if not source_name:
            return 'google.com'
        name_lower = source_name.lower().strip()
        # Exakter Match
        if name_lower in KNOWN_SOURCES:
            return KNOWN_SOURCES[name_lower]
        # Teilmatch
        for key, domain in KNOWN_SOURCES.items():
            if key in name_lower or name_lower in key:
                return domain
        # Fallback: versuche direkt als Domain
        if '.' in source_name:
            return source_name.lower()
        return source_name.lower().replace(' ', '') + '.de'

    # Config laden
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yaml')
    example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.example.yaml')

    # Immer config.example.yaml als config.yaml verwenden
    # (API-Keys kommen aus Umgebungsvariablen, nicht aus der Datei)
    import shutil
    if os.path.exists(example_path):
        shutil.copy(example_path, config_path)
    elif not os.path.exists(config_path):
        print("\n  [FEHLER] Weder config.yaml noch config.example.yaml gefunden!\n")

    medienspiegel_config = load_config(config_path)
    app.config['MEDIENSPIEGEL'] = medienspiegel_config

    # Datenbank initialisieren (Render: /data/, lokal: ./data/)
    db_dir = os.environ.get('DATA_DIR',
                            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'))
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, 'medienspiegel.db')
    app.config['DB_PATH'] = db_path
    init_db(db_path)

    # Blueprints registrieren
    from .routes import register_blueprints
    register_blueprints(app)

    # Scheduler starten (nur im Hauptprozess, nicht im Reloader)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from .scheduler import init_scheduler
        init_scheduler(app)

    return app
