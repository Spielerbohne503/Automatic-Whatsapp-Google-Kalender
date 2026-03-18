import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from calendar_service import CalendarService, CalendarFetchError
from config import Config
from state_manager import StateManager
from whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(
        self,
        config: Config,
        calendar_service: CalendarService,
        whatsapp_service: WhatsAppService,
        state_manager: StateManager,
    ):
        self._config = config
        self._calendar = calendar_service
        self._whatsapp = whatsapp_service
        self._state = state_manager
        self._tz = pytz.timezone(config.timezone)
        self._scheduler = BackgroundScheduler(timezone=config.timezone)

    def start(self) -> None:
        # Sofort beim Start einmal ausführen
        self.poll_and_schedule()

        self._scheduler.add_job(
            self.poll_and_schedule,
            trigger=IntervalTrigger(minutes=self._config.poll_interval_minutes),
            id="poll_loop",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "Scheduler gestartet. Kalender-Abfrage alle %d Minuten.",
            self._config.poll_interval_minutes,
        )

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler gestoppt.")

    def poll_and_schedule(self) -> None:
        logger.info("Kalender wird abgefragt...")
        try:
            events = self._calendar.get_upcoming_events()
        except CalendarFetchError as e:
            logger.error("Kalender-Abfrage fehlgeschlagen: %s", e)
            return

        now = datetime.now(pytz.utc)
        self._state.purge_old_entries(now - timedelta(days=1))

        scheduled_count = 0

        for event in events:
            event_id = event.get("id", "unknown")
            try:
                start_dt = self._calendar.parse_event_start(event)
            except Exception as e:
                logger.warning("Start-Zeit für Event '%s' konnte nicht gelesen werden: %s", event_id, e)
                continue

            reminder_minutes = self._calendar.extract_reminder_minutes(event)

            # Erinnerungen N Minuten vor dem Termin
            for minutes_before in reminder_minutes:
                fire_dt = start_dt - timedelta(minutes=minutes_before)
                key = _make_key(event_id, f"reminder_{minutes_before}", start_dt)

                if self._try_schedule(
                    key=key,
                    fire_dt=fire_dt,
                    now=now,
                    callback=self._fire_reminder,
                    callback_kwargs={
                        "event": event,
                        "minutes_before": minutes_before,
                        "start_dt": start_dt,
                        "notification_key": key,
                    },
                ):
                    scheduled_count += 1

            # Benachrichtigung genau zum Terminstart
            start_key = _make_key(event_id, "start", start_dt)
            if self._try_schedule(
                key=start_key,
                fire_dt=start_dt,
                now=now,
                callback=self._fire_start,
                callback_kwargs={
                    "event": event,
                    "start_dt": start_dt,
                    "notification_key": start_key,
                },
            ):
                scheduled_count += 1

        if scheduled_count:
            logger.info("%d neue Job(s) eingeplant.", scheduled_count)
        else:
            logger.info("Keine neuen Jobs zum Einplanen.")

    def _try_schedule(
        self,
        key: str,
        fire_dt: datetime,
        now: datetime,
        callback,
        callback_kwargs: dict,
    ) -> bool:
        """Plant einen Job ein. Gibt True zurück, wenn ein neuer Job hinzugefügt wurde."""
        if fire_dt <= now:
            return False
        if self._state.is_sent(key):
            return False
        if self._scheduler.get_job(key):
            return False

        self._scheduler.add_job(
            callback,
            trigger=DateTrigger(run_date=fire_dt),
            id=key,
            kwargs=callback_kwargs,
            replace_existing=False,
            misfire_grace_time=120,
        )
        logger.debug("Job geplant: %s um %s", key, fire_dt.strftime("%d.%m.%Y %H:%M"))
        return True

    def _fire_reminder(
        self,
        event: dict,
        minutes_before: int,
        start_dt: datetime,
        notification_key: str,
    ) -> None:
        if self._state.is_sent(notification_key):
            return
        message = self._whatsapp.format_reminder_message(event, minutes_before, start_dt)
        success = self._whatsapp.send_message(message)
        if success:
            self._state.mark_sent(notification_key)

    def _fire_start(
        self,
        event: dict,
        start_dt: datetime,
        notification_key: str,
    ) -> None:
        if self._state.is_sent(notification_key):
            return
        message = self._whatsapp.format_start_message(event, start_dt)
        success = self._whatsapp.send_message(message)
        if success:
            self._state.mark_sent(notification_key)


def _make_key(event_id: str, ntype: str, start_dt: datetime) -> str:
    time_str = start_dt.strftime("%Y-%m-%dT%H:%M")
    # Sonderzeichen aus event_id entfernen damit der Key sauber bleibt
    safe_id = event_id.replace("_", "-")
    return f"{safe_id}_{ntype}_{time_str}"
