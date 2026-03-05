"""HTML-Mail Erstellung und Gmail-Versand."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from flask import render_template


def send_medienspiegel_mail(config, articles, stats, range_label="Heute"):
    """Sende den Medienspiegel als formatierte HTML-Mail."""
    mail_config = config.get('mail', {})

    sender = mail_config.get('sender', '')
    password = mail_config.get('password', '')
    recipients = mail_config.get('recipients', [])
    subject_prefix = mail_config.get('subject_prefix', 'Medienspiegel')

    if not sender or not password or not recipients:
        raise ValueError("Mail nicht vollstaendig konfiguriert (sender/password/recipients)")

    # Betreff mit Datum und Zeitraum
    today = date.today().strftime('%d.%m.%Y')
    subject = "{} - {} ({})".format(subject_prefix, today, range_label)

    # HTML-Body aus Template rendern
    html_body = render_template('mail.html',
                                articles=articles,
                                stats=stats,
                                date_str=today,
                                range_label=range_label)

    # Mail zusammenbauen
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    # Plain-Text Fallback
    plain = "Medienspiegel vom {}\n\n{} Artikel gesammelt.\n\nBitte HTML-Ansicht aktivieren.".format(
        today, stats.get('total', 0))
    msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    # Gmail SMTP Versand
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())


def send_alert_mail(config, alert, articles):
    """Sende eine Alert-Benachrichtigung per E-Mail.

    Args:
        config: App-Konfiguration
        alert: Alert-Dict mit name, source_pattern, topic_pattern, etc.
        articles: Liste der gematchten Artikel-Dicts
    """
    mail_config = config.get('mail', {})
    sender = mail_config.get('sender', '')
    password = mail_config.get('password', '')

    # Empfaenger: Alert-spezifisch oder globale Empfaenger
    recipients = []
    if alert.get('email_to'):
        recipients = [r.strip() for r in alert['email_to'].split(',')]
    else:
        recipients = mail_config.get('recipients', [])

    if not sender or not password or not recipients:
        print("  [ALERT-MAIL] Nicht konfiguriert: sender={}, recipients={}".format(
            bool(sender), len(recipients)))
        return

    today = date.today().strftime('%d.%m.%Y')
    subject = "Alert: {} ({} Treffer)".format(alert['name'], len(articles))

    # Einfaches HTML fuer Alert-Mail
    lines = []
    lines.append('<h2 style="font-family:DM Sans,sans-serif;color:#171a20;">Alert: {}</h2>'.format(
        alert['name']))
    lines.append('<p style="font-family:DM Sans,sans-serif;color:#5c5e62;font-size:14px;">')
    lines.append('{} neue Artikel gefunden am {}</p>'.format(len(articles), today))

    if alert.get('source_pattern'):
        lines.append('<p style="font-size:13px;color:#878b90;">Quelle: {}</p>'.format(
            alert['source_pattern']))
    if alert.get('topic_pattern'):
        lines.append('<p style="font-size:13px;color:#878b90;">Thema: {}</p>'.format(
            alert['topic_pattern']))
    if alert.get('keyword_pattern'):
        lines.append('<p style="font-size:13px;color:#878b90;">Keyword: {}</p>'.format(
            alert['keyword_pattern']))

    lines.append('<hr style="border:none;border-top:1px solid #e0e2e6;margin:16px 0;">')

    for art in articles[:20]:  # Max 20 Artikel in der Mail
        lines.append('<div style="margin-bottom:16px;">')
        lines.append('<a href="{}" style="font-family:DM Sans,sans-serif;font-size:15px;'
                     'font-weight:600;color:#171a20;text-decoration:none;">{}</a>'.format(
                         art.get('url', '#'), art.get('title', '')))
        if art.get('source_name'):
            lines.append('<br><span style="font-size:12px;color:#878b90;">{}</span>'.format(
                art['source_name']))
        if art.get('ai_summary'):
            lines.append('<p style="font-size:13px;color:#5c5e62;margin:4px 0 0;">{}</p>'.format(
                art['ai_summary'][:200]))
        lines.append('</div>')

    html_body = '\n'.join(lines)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    plain = "Alert: {} - {} Treffer\n\n".format(alert['name'], len(articles))
    for art in articles[:20]:
        plain += "- {}\n  {}\n\n".format(art.get('title', ''), art.get('url', ''))

    msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print("  [ALERT-MAIL] '{}' gesendet an {}".format(alert['name'], recipients))
    except Exception as e:
        print("  [ALERT-MAIL] Fehler: {}".format(str(e)[:80]))
