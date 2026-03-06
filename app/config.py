"""Konfiguration aus config.yaml laden und validieren."""

import os
import yaml


def load_config(path):
    """Lade config.yaml und gib ein Dictionary zurück.

    Umgebungsvariablen ueberschreiben config.yaml-Werte (fuer Render/Cloud):
        ANTHROPIC_API_KEY  -> api_keys.anthropic
        MAIL_SENDER        -> mail.sender
        MAIL_PASSWORD      -> mail.password
        MAIL_RECIPIENTS    -> mail.recipients (kommagetrennt)
    """
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Defaults setzen falls nicht vorhanden
    config.setdefault('api_keys', {})
    config.setdefault('mail', {'enabled': False})
    config.setdefault('schedule', {'enabled': False, 'time': '08:00'})
    config.setdefault('rss_feeds', [])
    config.setdefault('twitter', {'enabled': False})
    config.setdefault('collection', {
        'max_articles_per_source': 50,
        'request_delay': 1.0
    })

    # Backward-Kompatibilitaet: alte flat-Config in languages umwandeln
    if 'languages' not in config:
        config['languages'] = [{
            'lang': config.get('language', 'de'),
            'country': config.get('country', 'DE'),
            'search_terms': config.get('search_terms', [])
        }]

    # Validierung
    for lang_config in config.get('languages', []):
        lang_config.setdefault('lang', 'de')
        lang_config.setdefault('country', 'DE')
        lang_config.setdefault('search_terms', [])

    total_terms = sum(len(lc.get('search_terms', [])) for lc in config.get('languages', []))
    if total_terms == 0:
        print("  [WARNUNG] Keine Suchbegriffe in config.yaml definiert!")

    # Umgebungsvariablen ueberschreiben config.yaml (fuer Cloud/Render)
    env_api_key = os.environ.get('ANTHROPIC_API_KEY')
    if env_api_key:
        config['api_keys']['anthropic'] = env_api_key

    # Groq API-Key (kostenlos: console.groq.com)
    env_groq_key = os.environ.get('GROQ_API_KEY')
    if env_groq_key:
        config['api_keys']['groq'] = env_groq_key

    env_mail_sender = os.environ.get('MAIL_SENDER')
    if env_mail_sender:
        config.setdefault('mail', {})
        config['mail']['sender'] = env_mail_sender
        config['mail']['enabled'] = True

    env_mail_pw = os.environ.get('MAIL_PASSWORD')
    if env_mail_pw:
        config.setdefault('mail', {})
        config['mail']['password'] = env_mail_pw

    env_recipients = os.environ.get('MAIL_RECIPIENTS')
    if env_recipients:
        config.setdefault('mail', {})
        config['mail']['recipients'] = [r.strip() for r in env_recipients.split(',')]

    return config


def save_config(path, config):
    """Speichere config Dictionary zurück in YAML-Datei."""
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
