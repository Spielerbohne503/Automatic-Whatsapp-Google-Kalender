"""
WhatsApp Kalender-Bot
Alles in einer Datei. Läuft als bot.exe auf Windows.
Konfiguration: config.ini (liegt neben der exe)
"""

import configparser
import json
import logging
import os
import signal
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ─── Pfade relativ zur exe / zum Skript ────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
STATE_FILE = os.path.join(BASE_DIR, "gesendet.json")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


# ─── Logging ────────────────────────────────────────────────────────────────

def setup_logging():
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%d.%m.%Y %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fh = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)


log = logging.getLogger("bot")


# ─── Konfiguration ──────────────────────────────────────────────────────────

class Config:
    def __init__(self):
        if not os.path.exists(CONFIG_FILE):
            _create_default_config()
            log.error(
                "config.ini wurde neu erstellt in: %s\n"
                "Bitte ausfüllen und bot.exe neu starten.",
                CONFIG_FILE,
            )
            sys.exit(1)

        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_FILE, encoding="utf-8")

        s = cfg["Einstellungen"]
        self.phone = s.get("HandyNummer", "").strip()
        self.api_key = s.get("CallMeBot_ApiKey", "").strip()
        self.calendar_id = s.get("KalenderID", "primary").strip()
        self.timezone = s.get("Zeitzone", "Europe/Berlin").strip()
        self.poll_minutes = int(s.get("AbfrageIntervallMinuten", "5"))
        self.lookahead_hours = int(s.get("VorausschauStunden", "24"))
        self.allday_hour = int(s.get("GanztaegigErinnerungUhrzeit", "8"))

        missing = []
        if not self.phone:
            missing.append("HandyNummer")
        if not self.api_key:
            missing.append("CallMeBot_ApiKey")
        if missing:
            log.error(
                "Fehlende Felder in config.ini: %s\nBitte ausfüllen und neu starten.",
                ", ".join(missing),
            )
            sys.exit(1)


def _create_default_config():
    content = """\
[Einstellungen]
; Deine Handynummer im internationalen Format
HandyNummer = +491701234567

; API-Key von https://www.callmebot.com/blog/free-api-whatsapp-messages/
CallMeBot_ApiKey = HIER_API_KEY_EINTRAGEN

; "primary" für Hauptkalender, sonst die Kalender-ID aus Google Kalender
KalenderID = primary

; Deine Zeitzone
Zeitzone = Europe/Berlin

; Wie oft der Kalender abgefragt wird (Minuten)
AbfrageIntervallMinuten = 5

; Wie weit in die Zukunft nach Terminen gesucht wird (Stunden)
VorausschauStunden = 24

; Uhrzeit für ganztägige Termine (Stunde, z.B. 8 = 08:00 Uhr)
GanztaegigErinnerungUhrzeit = 8
"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


# ─── Google Calendar ─────────────────────────────────────────────────────────

def authenticate(config: Config):
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                log.error(
                    "credentials.json nicht gefunden in: %s\n"
                    "Bitte von der Google Cloud Console herunterladen\n"
                    "(APIs & Dienste → Anmeldedaten → OAuth 2.0 Client-IDs → Desktop-App).",
                    BASE_DIR,
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    log.info("Google Calendar verbunden.")
    return service


def get_events(service, config: Config) -> list:
    now = datetime.now(pytz.utc)
    time_max = now + timedelta(hours=config.lookahead_hours)
    try:
        result = (
            service.events()
            .list(
                calendarId=config.calendar_id,
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = result.get("items", [])
        log.info("%d Termin(e) gefunden.", len(events))
        return events
    except HttpError as e:
        log.error("Kalender-Fehler: %s", e)
        return []


def parse_start(event: dict, config: Config) -> datetime:
    tz = pytz.timezone(config.timezone)
    start = event.get("start", {})
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt.astimezone(tz)
    date_str = start["date"]
    naive = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=config.allday_hour, minute=0, second=0
    )
    return tz.localize(naive)


def get_reminder_minutes(event: dict) -> list:
    reminders = event.get("reminders", {})
    if reminders.get("useDefault", True):
        return [30]
    overrides = reminders.get("overrides", [])
    if not overrides:
        return []
    return sorted({o["minutes"] for o in overrides if "minutes" in o})


# ─── WhatsApp ────────────────────────────────────────────────────────────────

def send_whatsapp(message: str, config: Config) -> bool:
    try:
        r = requests.get(
            CALLMEBOT_URL,
            params={"phone": config.phone, "text": message, "apikey": config.api_key},
            timeout=15,
        )
        if r.status_code == 200:
            log.info("WhatsApp gesendet: %s", message[:80])
            return True
        log.error("WhatsApp Fehler (HTTP %d): %s", r.status_code, r.text[:200])
        return False
    except requests.RequestException as e:
        log.error("WhatsApp Netzwerkfehler: %s", e)
        return False


def msg_erinnerung(event: dict, minutes_before: int, start_dt: datetime) -> str:
    title = event.get("summary", "(Kein Titel)")
    zeit = start_dt.strftime("%H:%M")
    ort = event.get("location", "")
    if minutes_before >= 60 and minutes_before % 60 == 0:
        h = minutes_before // 60
        label = f"{h} Stunde{'n' if h > 1 else ''}"
    elif minutes_before >= 60:
        label = f"{minutes_before // 60}h {minutes_before % 60}min"
    else:
        label = f"{minutes_before} Minuten"
    m = f"Erinnerung: {title} startet in {label} ({zeit} Uhr)"
    return m + f" – {ort}" if ort else m


def msg_start(event: dict, start_dt: datetime) -> str:
    title = event.get("summary", "(Kein Titel)")
    zeit = start_dt.strftime("%H:%M")
    ort = event.get("location", "")
    m = f"Jetzt gestartet: {title} ({zeit} Uhr)"
    return m + f" – {ort}" if ort else m


# ─── State (Duplikat-Schutz) ─────────────────────────────────────────────────

def load_state() -> set:
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_state(state: set):
    try:
        dir_name = os.path.dirname(STATE_FILE) or "."
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp", encoding="utf-8") as tmp:
            json.dump(sorted(state), tmp, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, STATE_FILE)
    except OSError as e:
        log.error("State konnte nicht gespeichert werden: %s", e)


def make_key(event_id: str, ntype: str, start_dt: datetime) -> str:
    return f"{event_id.replace('_', '-')}_{ntype}_{start_dt.strftime('%Y-%m-%dT%H:%M')}"


def purge_old(state: set) -> set:
    cutoff = (datetime.now(pytz.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    return {k for k in state if k.rsplit("_", 1)[-1] >= cutoff}


# ─── Scheduler ───────────────────────────────────────────────────────────────

def poll_and_schedule(service, config: Config, scheduler: BackgroundScheduler, state: set):
    events = get_events(service, config)
    now = datetime.now(pytz.utc)

    for event in events:
        eid = event.get("id", "unknown")
        try:
            start_dt = parse_start(event, config)
        except Exception as e:
            log.warning("Start-Zeit unlesbar für '%s': %s", eid, e)
            continue

        for mins in get_reminder_minutes(event):
            fire_dt = start_dt - timedelta(minutes=mins)
            key = make_key(eid, f"r{mins}", start_dt)
            _schedule(scheduler, key, fire_dt, now, state, config,
                      lambda e=event, m=mins, s=start_dt, k=key: _send(
                          msg_erinnerung(e, m, s), k, config, state))

        start_key = make_key(eid, "start", start_dt)
        _schedule(scheduler, start_key, start_dt, now, state, config,
                  lambda e=event, s=start_dt, k=start_key: _send(
                      msg_start(e, s), k, config, state))


def _schedule(scheduler, key, fire_dt, now, state, config, fn):
    if fire_dt <= now or key in state or scheduler.get_job(key):
        return
    scheduler.add_job(fn, trigger=DateTrigger(run_date=fire_dt),
                      id=key, replace_existing=False, misfire_grace_time=120)
    log.debug("Geplant: %s um %s", key, fire_dt.strftime("%d.%m. %H:%M"))


def _send(message: str, key: str, config: Config, state: set):
    if key in state:
        return
    if send_whatsapp(message, config):
        state.add(key)
        save_state(state)


# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def main():
    setup_logging()
    log.info("WhatsApp Kalender-Bot startet...")

    config = Config()
    service = authenticate(config)

    state = load_state()
    scheduler = BackgroundScheduler(timezone=config.timezone)

    def poll():
        nonlocal state
        state = purge_old(state)
        poll_and_schedule(service, config, scheduler, state)

    poll()  # Sofort beim Start
    scheduler.add_job(poll, trigger=IntervalTrigger(minutes=config.poll_minutes),
                      id="poll", replace_existing=True)
    scheduler.start()

    log.info("Bot läuft. Abfrage alle %d Minuten. (Strg+C zum Beenden)", config.poll_minutes)

    def shutdown(sig=None, frame=None):
        log.info("Bot wird beendet...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        shutdown()


if __name__ == "__main__":
    main()
