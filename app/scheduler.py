"""APScheduler fuer taegliche automatische Mediensammlung."""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


_scheduler = None


def init_scheduler(app):
    """Initialisiere den Scheduler falls in config aktiviert."""
    global _scheduler

    config = app.config['MEDIENSPIEGEL']
    schedule_config = config.get('schedule', {})

    if not schedule_config.get('enabled'):
        return

    time_str = schedule_config.get('time', '08:00')
    try:
        hour, minute = time_str.split(':')
        hour, minute = int(hour), int(minute)
    except (ValueError, AttributeError):
        print("  [FEHLER] Ungueltige Uhrzeit in config: {}".format(time_str))
        return

    _scheduler = BackgroundScheduler()

    def scheduled_collection():
        """Fuehre geplante Sammlung + optionalen Mail-Versand durch."""
        with app.app_context():
            try:
                from .collectors import run_collection
                db_path = app.config['DB_PATH']
                run_id, found, new, errors = run_collection(config, db_path)
                print("  [SCHEDULER] Sammlung abgeschlossen: {} gefunden, {} neu".format(found, new))

                # KI-Zusammenfassungen
                api_key = config.get('api_keys', {}).get('anthropic', '')
                if api_key:
                    try:
                        from .summarizer import summarize_new_articles
                        count = summarize_new_articles(db_path, api_key)
                        print("  [SCHEDULER] {} Artikel zusammengefasst".format(count))
                    except Exception as e:
                        print("  [SCHEDULER] KI-Fehler: {}".format(e))

                # Auto-Mail senden
                mail_config = config.get('mail', {})
                if mail_config.get('enabled'):
                    try:
                        from .mailer import send_medienspiegel_mail
                        from .database import get_articles, get_article_stats
                        from datetime import date
                        today = date.today().isoformat()
                        articles = get_articles(db_path, date=today)
                        stats = get_article_stats(db_path, date=today)
                        send_medienspiegel_mail(config, articles, stats,
                                                range_label="Automatisch 08:00")
                        print("  [SCHEDULER] Mail gesendet an {} Empfaenger".format(
                            len(mail_config.get('recipients', []))))
                    except Exception as e:
                        print("  [SCHEDULER] Mail-Fehler: {}".format(e))

                if errors:
                    for err in errors:
                        print("  [SCHEDULER] Warnung: {}".format(err))

            except Exception as e:
                print("  [SCHEDULER] Kritischer Fehler: {}".format(e))

    _scheduler.add_job(
        scheduled_collection,
        trigger=CronTrigger(hour=hour, minute=minute),
        id='daily_collection',
        name='Taegliche Mediensammlung',
        replace_existing=True
    )
    _scheduler.start()
    print("  [SCHEDULER] Taegliche Sammlung geplant fuer {}:{:02d}".format(hour, minute))


def shutdown_scheduler():
    """Stoppe den Scheduler sauber."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
