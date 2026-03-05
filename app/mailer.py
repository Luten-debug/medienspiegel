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
