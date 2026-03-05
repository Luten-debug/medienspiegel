"""APScheduler fuer automatische Mediensammlung."""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


_scheduler = None


def init_scheduler(app):
    """Initialisiere den Scheduler falls in config aktiviert."""
    global _scheduler

    config = app.config['MEDIENSPIEGEL']
    schedule_config = config.get('schedule', {})

    if not schedule_config.get('enabled'):
        return

    _scheduler = BackgroundScheduler()

    # === 1) Taegliche Sammlung + KI + Mail ===
    time_str = schedule_config.get('time', '08:00')
    try:
        hour, minute = time_str.split(':')
        hour, minute = int(hour), int(minute)
    except (ValueError, AttributeError):
        print("  [FEHLER] Ungueltige Uhrzeit in config: {}".format(time_str))
        hour, minute = 8, 0

    def scheduled_collection():
        """Fuehre geplante Sammlung + optionalen Mail-Versand durch."""
        with app.app_context():
            try:
                from .collectors import run_collection
                db_path = app.config['DB_PATH']
                # run_collection hat internen Lock — gibt (None, 0, 0, [...]) zurueck
                # wenn bereits eine Sammlung laeuft
                run_id, found, new, errors = run_collection(config, db_path)

                if run_id is None:
                    print("  [SCHEDULER] Sammlung uebersprungen (laeuft bereits)")
                    return

                print("  [SCHEDULER] Sammlung abgeschlossen: {} gefunden, {} neu".format(found, new))

                # KI-Zusammenfassungen (nur bei taeglich)
                api_key = config.get('api_keys', {}).get('anthropic', '')
                if api_key and new > 0:
                    try:
                        from .summarizer import categorize_uncategorized
                        categorize_uncategorized(db_path, api_key)
                    except Exception as e:
                        print("  [SCHEDULER] Kategorisierung: {}".format(str(e)[:80]))

                    try:
                        from .summarizer import summarize_new_articles
                        count = summarize_new_articles(db_path, api_key)
                        print("  [SCHEDULER] {} Artikel zusammengefasst".format(count))
                    except Exception as e:
                        print("  [SCHEDULER] KI-Fehler: {}".format(e))

                # Alerts pruefen
                if new > 0:
                    try:
                        from .database import check_alerts, get_db
                        conn = get_db(db_path)
                        new_rows = conn.execute(
                            "SELECT id FROM articles ORDER BY id DESC LIMIT ?",
                            (new,)).fetchall()
                        conn.close()
                        new_ids = [r['id'] for r in new_rows]
                        alert_hits = check_alerts(db_path, new_ids)

                        if alert_hits and config.get('mail', {}).get('enabled'):
                            from .mailer import send_alert_mail
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
                                    print("  [SCHEDULER] Alert-Mail: {}".format(str(e)[:80]))
                    except Exception as e:
                        print("  [SCHEDULER] Alert-Check: {}".format(str(e)[:80]))

                # Auto-Mail senden
                mail_config = config.get('mail', {})
                if mail_config.get('enabled') and mail_config.get('auto_send', True):
                    try:
                        from .mailer import send_medienspiegel_mail
                        from .database import get_articles, get_article_stats
                        from datetime import date
                        today = date.today().isoformat()
                        articles = get_articles(db_path, date=today)
                        stats = get_article_stats(db_path, date=today)
                        send_medienspiegel_mail(config, articles, stats,
                                                range_label="Automatisch {:02d}:{:02d}".format(hour, minute))
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
    print("  [SCHEDULER] Taegliche Sammlung geplant fuer {:02d}:{:02d}".format(hour, minute))

    # === 2) Auto-Refresh ===
    refresh_minutes = schedule_config.get('refresh_interval', 15)
    if refresh_minutes and refresh_minutes > 0:

        def auto_refresh():
            """Schnelle Artikelsammlung mit KI-Kategorisierung."""
            with app.app_context():
                try:
                    from .collectors import run_collection
                    db_path = app.config['DB_PATH']
                    run_id, found, new, errors = run_collection(config, db_path)

                    if run_id is None:
                        return  # Laeuft schon

                    if new > 0:
                        print("  [AUTO-REFRESH] {} neue Artikel gesammelt".format(new))

                        # Kategorisierung + Zitate
                        api_key = config.get('api_keys', {}).get('anthropic', '')
                        if api_key:
                            try:
                                from .summarizer import categorize_uncategorized, summarize_new_articles
                                categorize_uncategorized(db_path, api_key)
                                summarize_new_articles(db_path, api_key)
                            except Exception:
                                pass

                        # Alerts pruefen
                        try:
                            from .database import check_alerts, get_db
                            conn = get_db(db_path)
                            new_rows = conn.execute(
                                "SELECT id FROM articles ORDER BY id DESC LIMIT ?",
                                (new,)).fetchall()
                            conn.close()
                            new_ids = [r['id'] for r in new_rows]
                            alert_hits = check_alerts(db_path, new_ids)

                            if alert_hits and config.get('mail', {}).get('enabled'):
                                from .mailer import send_alert_mail
                                alert_groups = {}
                                for alert_d, art_d in alert_hits:
                                    aid = alert_d['id']
                                    if aid not in alert_groups:
                                        alert_groups[aid] = (alert_d, [])
                                    alert_groups[aid][1].append(art_d)
                                for aid, (alert_d, arts) in alert_groups.items():
                                    try:
                                        send_alert_mail(config, alert_d, arts)
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                except Exception as e:
                    print("  [AUTO-REFRESH] Fehler: {}".format(str(e)[:100]))

        _scheduler.add_job(
            auto_refresh,
            trigger=IntervalTrigger(minutes=refresh_minutes),
            id='auto_refresh',
            name='Auto-Refresh (alle {} Min)'.format(refresh_minutes),
            replace_existing=True
        )
        print("  [SCHEDULER] Auto-Refresh alle {} Minuten aktiviert".format(refresh_minutes))

    _scheduler.start()


def shutdown_scheduler():
    """Stoppe den Scheduler sauber."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
