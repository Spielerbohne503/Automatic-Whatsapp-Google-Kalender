import logging
import os
from datetime import datetime, timedelta

import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_REMINDER_MINUTES = 30


class CalendarAuthError(Exception):
    pass


class CalendarFetchError(Exception):
    pass


class CalendarService:
    def __init__(self, config: Config):
        self._config = config
        self._service = None

    def authenticate(self) -> None:
        creds = None

        if os.path.exists(self._config.token_file):
            try:
                creds = Credentials.from_authorized_user_file(
                    self._config.token_file, SCOPES
                )
            except Exception as e:
                logger.warning("Token-Datei konnte nicht geladen werden: %s", e)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Google OAuth Token aktualisiert.")
                except Exception as e:
                    logger.warning("Token-Aktualisierung fehlgeschlagen: %s", e)
                    creds = None

            if not creds:
                if not os.path.exists(self._config.credentials_file):
                    raise CalendarAuthError(
                        f"'{self._config.credentials_file}' nicht gefunden.\n"
                        "Bitte lade credentials.json von der Google Cloud Console herunter\n"
                        "(APIs & Dienste > Anmeldedaten > OAuth 2.0 Client-IDs > Desktop-App)."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._config.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("Google OAuth erfolgreich abgeschlossen.")

            with open(self._config.token_file, "w") as f:
                f.write(creds.to_json())
            logger.info("Token gespeichert in '%s'.", self._config.token_file)

        self._service = build("calendar", "v3", credentials=creds)
        logger.info("Google Calendar API verbunden.")

    def get_upcoming_events(self) -> list:
        if self._service is None:
            raise CalendarAuthError("Nicht authentifiziert. Bitte zuerst authenticate() aufrufen.")

        tz = pytz.timezone(self._config.timezone)
        now = datetime.now(pytz.utc)
        time_max = now + timedelta(hours=self._config.lookahead_hours)

        try:
            result = (
                self._service.events()
                .list(
                    calendarId=self._config.google_calendar_id,
                    timeMin=now.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as e:
            raise CalendarFetchError(f"Google Calendar API Fehler: {e}") from e

        events = result.get("items", [])
        logger.info("%d Termin(e) in den nächsten %dh gefunden.", len(events), self._config.lookahead_hours)
        return events

    def extract_reminder_minutes(self, event: dict) -> list:
        reminders = event.get("reminders", {})

        if reminders.get("useDefault", True):
            return [DEFAULT_REMINDER_MINUTES]

        overrides = reminders.get("overrides", [])
        if not overrides:
            return []

        minutes = list({o["minutes"] for o in overrides if "minutes" in o})
        return sorted(minutes)

    def parse_event_start(self, event: dict) -> datetime:
        tz = pytz.timezone(self._config.timezone)
        start = event.get("start", {})

        if "dateTime" in start:
            dt = datetime.fromisoformat(start["dateTime"])
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            return dt.astimezone(tz)

        # Ganztägiger Termin: Datum parsen und Uhrzeit aus Konfiguration verwenden
        date_str = start["date"]
        naive = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=self._config.all_day_reminder_hour, minute=0, second=0
        )
        return tz.localize(naive)
