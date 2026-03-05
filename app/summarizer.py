"""KI-Zusammenfassungen und Kategorisierung via Claude API."""

import json
import re
import time
import requests
from .database import (
    get_articles_without_summary, update_article_summary, get_articles,
    get_db, get_existing_topics, get_uncategorized_articles, update_article_topic
)

# Feste Themenkategorien (breit gefasst)
TOPIC_CATEGORIES = [
    "Produktion & Ausbau",
    "Betriebsrat & Gewerkschaft",
    "Arbeitsmarkt & Personal",
    "Umwelt & Genehmigungen",
    "Proteste & Sicherheit",
    "Politik & Standort",
    "Elon Musk & Image",
    "Markt & Wettbewerb",
    "Technologie & Batterie",
    "Sonstiges",
]


def categorize_uncategorized(db_path, api_key, model="claude-haiku-4-5-20251001"):
    """Kategorisiere alle Artikel ohne Thema in Batches (schnell, ohne Zusammenfassung)."""
    articles = get_uncategorized_articles(db_path, limit=100)
    if not articles:
        return 0

    categories_str = ', '.join(TOPIC_CATEGORIES)
    categorized = 0

    # Batches von 15 Artikeln
    for i in range(0, len(articles), 15):
        batch = articles[i:i+15]
        items = []
        for a in batch:
            items.append('{}: {}'.format(a['id'], a['title'][:120]))
        articles_list = '\n'.join(items)

        prompt = """Kategorisiere diese Artikel zur Tesla Giga Factory Berlin-Brandenburg.

Kategorien: {categories}

Artikel:
{articles}

Antworte NUR mit JSON-Array (kein Markdown): [{{"id":123,"thema":"..."}}, ...]""".format(
            categories=categories_str, articles=articles_list)

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": model,
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            resp.raise_for_status()
            text = resp.json().get('content', [{}])[0].get('text', '[]')
            results = _parse_json_response(text)

            # Kann ein Array oder ein Dict sein
            if isinstance(results, dict):
                results = [results]
            elif not isinstance(results, list):
                # Versuche Array zu parsen
                cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip())
                cleaned = re.sub(r'\s*```\s*$', '', cleaned)
                try:
                    results = json.loads(cleaned)
                except Exception:
                    results = []

            for item in results:
                if isinstance(item, dict) and 'id' in item and 'thema' in item:
                    update_article_topic(db_path, item['id'], item['thema'])
                    categorized += 1

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                time.sleep(int(e.response.headers.get('retry-after', 15)))
            else:
                print("  [FEHLER] Kategorisierung: {}".format(str(e)[:80]))
        except Exception as e:
            print("  [FEHLER] Kategorisierung: {}".format(str(e)[:80]))

    return categorized


def summarize_new_articles(db_path, api_key, model="claude-haiku-4-5-20251001", progress_cb=None):
    """Generiere KI-Zusammenfassungen fuer alle Artikel ohne Summary.

    Args:
        progress_cb: Optional callback(summarized, total) fuer Fortschrittsanzeige.
    """
    articles = get_articles_without_summary(db_path)
    if not articles:
        return 0

    total = len(articles)
    summarized = 0
    for article in articles:
        try:
            article['_db_path'] = db_path
            summary, reach, topic = _summarize_article(article, api_key, model)
            update_article_summary(db_path, article['id'], summary, reach, topic)
            summarized += 1
            if progress_cb:
                progress_cb(summarized, total)
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            if e.response is not None and e.response.status_code in (400, 401, 403):
                try:
                    err_detail = e.response.json().get('error', {}).get('message', error_msg)
                except Exception:
                    err_detail = error_msg
                raise RuntimeError(err_detail)
            if e.response is not None and e.response.status_code == 429:
                retry_after = int(e.response.headers.get('retry-after', 30))
                print("  [RATE-LIMIT] Warte {} Sek...".format(retry_after))
                time.sleep(retry_after)
            else:
                print("  [FEHLER] Zusammenfassung: {}".format(error_msg[:80]))
        except Exception as e:
            if 'credit' in str(e).lower() or 'billing' in str(e).lower():
                raise
            print("  [FEHLER] Zusammenfassung: {}".format(str(e)[:80]))

    # News-Ueberblick generieren
    if summarized > 0:
        try:
            generate_news_overview(db_path, api_key, model)
        except Exception as e:
            print("  [FEHLER] News-Ueberblick: {}".format(e))

    return summarized


def generate_news_overview(db_path, api_key, model="claude-haiku-4-5-20251001"):
    """Generiere einen KI-Gesamtueberblick ueber die aktuellen Nachrichten."""
    articles = get_articles(db_path, limit=30)
    if not articles:
        return

    summaries = []
    for a in articles[:30]:
        title = a.get('title', '')
        source = a.get('source_name', '')
        summary = a.get('ai_summary', '')
        if summary:
            summaries.append('- {} ({}): {}'.format(title, source, summary[:150]))
        else:
            summaries.append('- {} ({})'.format(title, source))

    articles_text = '\n'.join(summaries[:20])

    prompt = """Du bist Medienanalyst fuer Tesla und die Giga Factory Berlin-Brandenburg in Gruenheide.
Du stehst Tesla grundsaetzlich positiv gegenueber – die Fabrik ist ein wichtiger Arbeitgeber und Innovationsstandort.

Hier sind die aktuellen Nachrichten:

{articles}

Schreibe einen kurzen Ueberblick (3-4 Saetze, max. 80 Worte) der die aktuelle Nachrichtenlage zusammenfasst.
Betone positive Entwicklungen (Produktion, Jobs, Innovation) und ordne kritische Stimmen sachlich ein.
Schreibe auf Deutsch, als reinen Fliesstext. KEIN Markdown, keine Ueberschriften, keine Aufzaehlungen.""".format(
        articles=articles_text
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": model,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    overview = data.get('content', [{}])[0].get('text', '').strip()

    if overview:
        conn = get_db(db_path)
        conn.execute(
            "INSERT OR REPLACE INTO kv_store (key, value) VALUES ('news_overview', ?)",
            (overview,)
        )
        conn.commit()
        conn.close()
        print("  [INFO] News-Ueberblick generiert")


def _summarize_article(article, api_key, model="claude-haiku-4-5-20251001"):
    """Generiere Zusammenfassung, Reichweite und Themencluster fuer einen Artikel."""
    lang = article.get('language', 'de') or 'de'

    prompt = """{lang_hint}Artikel: "{title}" ({source})
Text: {snippet}

Schreibe 2-3 kurze, praegnante Kernaussagen basierend auf den verfuegbaren Informationen.

WICHTIG:
- Nutze NUR die oben gegebenen Informationen (Titel + Text). Arbeite mit dem was da ist.
- NIEMALS schreiben "Ich kann nicht...", "benoetige...", "Der Artikel...", "Es wird berichtet..." oder aehnliche Meta-Saetze.
- NIEMALS nach mehr Text fragen oder sagen dass Informationen fehlen.
- Wenn wenig Text vorhanden: formuliere 1-2 Kernaussagen basierend auf dem Titel.
- Wenn Zitate im Text stehen: gib sie in Anfuehrungszeichen wieder.
- Trenne mehrere Aussagen mit Zeilenumbruch.
- Schreibe direkt und faktisch. Max 80 Worte.{topic_hint}

JSON: {{"zusammenfassung":"...","reichweite":"Ueberregional|Regional|Fachpresse","thema":"..."}}""".format(
        lang_hint="Auf Deutsch. " if lang != 'de' else "",
        title=article.get('title', ''),
        source=article.get('source_name', 'Unbekannt'),
        snippet=article.get('snippet', '')[:400],
        topic_hint="\nThema: {}".format(', '.join(TOPIC_CATEGORIES)) if not article.get('topic_cluster') else "\nThema: {}".format(article.get('topic_cluster'))
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": model,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    text = data.get('content', [{}])[0].get('text', '{}')

    result = _parse_json_response(text)

    summary = result.get('zusammenfassung', text.strip())
    reach = result.get('reichweite', 'Unbekannt')
    topic = result.get('thema', article.get('topic_cluster') or 'Sonstiges')

    # Schutz: Meta-Kommentare erkennen und durch Fallback ersetzen
    meta_phrases = ['ich kann', 'benoetige', 'benötige', 'artikeltext', 'bereitstellen',
                    'nicht verfügbar', 'nicht verfuegbar', 'leider nicht', 'sobald du']
    summary_lower = summary.lower()
    if any(phrase in summary_lower for phrase in meta_phrases):
        # Fallback: Einfache Kernaussage aus dem Titel
        summary = article.get('title', '')

    return summary, reach, topic


def _parse_json_response(text):
    """Parse JSON aus der Claude-Antwort, auch wenn es in Markdown-Codeblocks steckt."""
    # Markdown-Codeblocks entfernen (```json ... ``` oder ``` ... ```)
    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip())
    cleaned = re.sub(r'\s*```\s*$', '', cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: JSON-Objekt aus dem Text extrahieren
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Letzter Fallback: Felder per Regex extrahieren (fuer kaputtes JSON mit Sonderzeichen)
    result = {}
    for field in ('zusammenfassung', 'reichweite', 'thema'):
        m = re.search(r'"' + field + r'"\s*:\s*"(.+?)"\s*[,}]', cleaned)
        if m:
            result[field] = m.group(1)
    if result:
        return result

    return {}


def fix_broken_summaries(db_path):
    """Repariere Zusammenfassungen die noch rohes JSON oder Markdown enthalten."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT id, ai_summary, topic_cluster, estimated_reach FROM articles WHERE ai_summary IS NOT NULL"
    ).fetchall()

    fixed = 0
    for row in rows:
        summary = row['ai_summary']
        if not summary:
            continue

        # Pruefen ob die Summary JSON oder Markdown-Codeblocks enthaelt
        needs_fix = False
        if '```' in summary or '"zusammenfassung"' in summary or '"reichweite"' in summary:
            needs_fix = True

        if not needs_fix:
            continue

        result = _parse_json_response(summary)
        if result and 'zusammenfassung' in result:
            new_summary = result['zusammenfassung']
            new_reach = result.get('reichweite', row['estimated_reach'] or 'Unbekannt')
            new_topic = result.get('thema', row['topic_cluster'] or 'Sonstiges')
            conn.execute(
                "UPDATE articles SET ai_summary = ?, estimated_reach = ?, topic_cluster = ? WHERE id = ?",
                (new_summary, new_reach, new_topic, row['id'])
            )
            fixed += 1

    conn.commit()
    conn.close()
    return fixed
