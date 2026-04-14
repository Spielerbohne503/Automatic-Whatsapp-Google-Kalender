"""
WhatsApp Kalender-Bot
Konfiguration: config.ini (liegt neben der exe)
Keine credentials.json, kein OAuth – nur iCal-Links aus Google Kalender.
"""

import configparser
import json
import logging
import os
import signal
import sys
import tempfile
import time
from datetime import datetime, timedelta, date
from logging.handlers import RotatingFileHandler

import pytz
import recurring_ical_events
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from icalendar import Calendar

# ─── Pfade relativ zur exe / zum Skript ─────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
STATE_FILE  = os.path.join(BASE_DIR, "gesendet.json")
LOG_FILE    = os.path.join(BASE_DIR, "bot.log")

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


# ─── Logging ─────────────────────────────────────────────────────────────────

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


# ─── Konfiguration ───────────────────────────────────────────────────────────

class Config:
    def __init__(self):
        if not os.path.exists(CONFIG_FILE):
            _create_default_config()
            log.error(
                "config.ini wurde erstellt in: %s\n"
                "Bitte iCal-Links und CallMeBot-API-Key eintragen, dann neu starten.",
                CONFIG_FILE,
            )
            sys.exit(1)

        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_FILE, encoding="utf-8")

        wa = cfg["WhatsApp"]
        self.phone   = wa.get("HandyNummer", "").strip()
        self.api_key = wa.get("CallMeBot_ApiKey", "").strip()

        s = cfg["Einstellungen"]
        self.timezone      = s.get("Zeitzone", "Europe/Berlin").strip()
        self.poll_minutes  = int(s.get("AbfrageIntervallMinuten", "5"))
        self.lookahead_h   = int(s.get("VorausschauStunden", "24"))
        self.allday_hour   = int(s.get("GanztaegigErinnerungUhrzeit", "8"))

        # Alle Kalender-URLs aus Sektion [Kalender]
        if "Kalender" not in cfg:
            log.error("Sektion [Kalender] fehlt in config.ini.")
            sys.exit(1)

        self.calendars: dict[str, str] = {}  # Name → URL
        placeholder = "ICAL_URL_HIER_EINFUEGEN"
        for name, url in cfg["Kalender"].items():
            url = url.strip()
            if url and url != placeholder:
                self.calendars[name] = url

        # Pflichtfeld-Checks
        missing = []
        if not self.phone:
            missing.append("WhatsApp → HandyNummer")
        if not self.api_key or self.api_key == "HIER_EINTRAGEN":
            missing.append("WhatsApp → CallMeBot_ApiKey")
        if not self.calendars:
            missing.append("Kalender → mindestens eine iCal-URL eintragen")
        if missing:
            log.error(
                "Bitte folgende Felder in config.ini ausfüllen:\n  %s\nDann neu starten.",
                "\n  ".join(missing),
            )
            sys.exit(1)


def _create_default_config():
    content = """\
[WhatsApp]
; Deine Handynummer im internationalen Format
HandyNummer = +4915226310258
; API-Key von https://www.callmebot.com/blog/free-api-whatsapp-messages/
CallMeBot_ApiKey = HIER_EINTRAGEN

[Kalender]
; Für jeden Kalender den privaten iCal-Link eintragen.
; So findest du die Links:
;   1. Öffne calendar.google.com im Browser
;   2. Klicke oben rechts auf das Zahnrad → "Einstellungen"
;   3. Links in der Seitenleiste auf den Kalender-Namen klicken
;   4. Runterscrollen zu "Privatadresse im iCalendar-Format"
;   5. Den Link kopieren und hier einfügen
;
; Nicht benötigte Kalender einfach auskommentieren (Semikolon davor setzen).
;
Arbeit          = ICAL_URL_HIER_EINFUEGEN
Privat          = ICAL_URL_HIER_EINFUEGEN
Training        = ICAL_URL_HIER_EINFUEGEN
Haushalt        = ICAL_URL_HIER_EINFUEGEN
HSG             = ICAL_URL_HIER_EINFUEGEN
Mittelalter     = ICAL_URL_HIER_EINFUEGEN
Special         = ICAL_URL_HIER_EINFUEGEN
Geburtstage     = ICAL_URL_HIER_EINFUEGEN
Graue_Garde     = ICAL_URL_HIER_EINFUEGEN
Formula_1       = ICAL_URL_HIER_EINFUEGEN

[Einstellungen]
; Zeitzone
Zeitzone = Europe/Berlin
; Wie oft der Kalender abgefragt wird (Minuten)
AbfrageIntervallMinuten = 5
; Wie weit in die Zukunft gesucht wird (Stunden)
VorausschauStunden = 24
; Uhrzeit für ganztägige Termine (Stunde, z.B. 8 = 08:00 Uhr)
GanztaegigErinnerungUhrzeit = 8
"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


# ─── Kalender (iCal) ─────────────────────────────────────────────────────────

def fetch_events(config: Config) -> list[dict]:
    tz       = pytz.timezone(config.timezone)
    now      = datetime.now(pytz.utc)
    time_max = now + timedelta(hours=config.lookahead_h)

    events = []
    for cal_name, ical_url in config.calendars.items():
        try:
            resp = requests.get(ical_url, timeout=15)
            resp.raise_for_status()
            cal = Calendar.from_ical(resp.content)
        except Exception as e:
            log.error("Fehler beim Laden von Kalender '%s': %s", cal_name, e)
            continue

        try:
            instances = recurring_ical_events.of(cal).between(now, time_max)
        except Exception as e:
            log.error("Fehler beim Auslesen von Kalender '%s': %s", cal_name, e)
            continue

        for vevent in instances:
            try:
                start_dt = _parse_start(vevent, tz, config.allday_hour)
                reminder_mins = _parse_reminders(vevent)
                uid = str(vevent.get("uid", "")) + f"_{cal_name}"
                events.append({
                    "uid":             uid,
                    "summary":         str(vevent.get("summary", "(Kein Titel)")),
                    "location":        str(vevent.get("location", "") or ""),
                    "start_dt":        start_dt,
                    "reminder_minutes": reminder_mins,
                })
            except Exception as e:
                log.warning("Termin übersprungen (%s): %s", cal_name, e)

    log.info("%d Termin(e) in den nächsten %dh gefunden.", len(events), config.lookahead_h)
    return events


def _parse_start(vevent, tz, allday_hour: int) -> datetime:
    dtstart = vevent.get("dtstart")
    if dtstart is None:
        raise ValueError("Kein dtstart")

    val = dtstart.dt
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return tz.localize(val)
        return val.astimezone(tz)
    else:
        # Ganztägiger Termin (date-Objekt) → Uhrzeit aus Einstellung
        naive = datetime(val.year, val.month, val.day, allday_hour, 0, 0)
        return tz.localize(naive)


def _parse_reminders(vevent) -> list[int]:
    mins = []
    for alarm in vevent.walk("VALARM"):
        trigger = alarm.get("trigger")
        if trigger is None:
            continue
        val = trigger.dt
        if isinstance(val, timedelta):
            # Negative timedelta = Erinnerung VOR dem Termin
            m = int(-val.total_seconds() / 60)
            if m > 0:
                mins.append(m)
    return sorted(set(mins)) if mins else [30]  # Standard: 30 Minuten


# ─── WhatsApp ─────────────────────────────────────────────────────────────────

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


def msg_erinnerung(event: dict, minutes_before: int) -> str:
    start_dt = event["start_dt"]
    title    = event["summary"]
    zeit     = start_dt.strftime("%H:%M")
    ort      = event["location"]

    if minutes_before >= 60 and minutes_before % 60 == 0:
        h = minutes_before // 60
        label = f"{h} Stunde{'n' if h > 1 else ''}"
    elif minutes_before >= 60:
        label = f"{minutes_before // 60}h {minutes_before % 60}min"
    else:
        label = f"{minutes_before} Minuten"

    msg = f"Erinnerung: {title} startet in {label} ({zeit} Uhr)"
    return msg + f" – {ort}" if ort else msg


def msg_start(event: dict) -> str:
    start_dt = event["start_dt"]
    title    = event["summary"]
    zeit     = start_dt.strftime("%H:%M")
    ort      = event["location"]

    msg = f"Jetzt gestartet: {title} ({zeit} Uhr)"
    return msg + f" – {ort}" if ort else msg


# ─── State (Duplikat-Schutz) ──────────────────────────────────────────────────

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
        dn = os.path.dirname(STATE_FILE) or "."
        with tempfile.NamedTemporaryFile("w", dir=dn, delete=False, suffix=".tmp", encoding="utf-8") as tmp:
            json.dump(sorted(state), tmp, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, STATE_FILE)
    except OSError as e:
        log.error("State konnte nicht gespeichert werden: %s", e)


def make_key(uid: str, ntype: str, start_dt: datetime) -> str:
    safe = uid.replace("/", "-").replace("@", "_")[:60]
    return f"{safe}_{ntype}_{start_dt.strftime('%Y-%m-%dT%H:%M')}"


def purge_old(state: set) -> set:
    cutoff = (datetime.now(pytz.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    return {k for k in state if k.rsplit("_", 1)[-1] >= cutoff}


# ─── Scheduler ───────────────────────────────────────────────────────────────

def poll_and_schedule(config: Config, scheduler: BackgroundScheduler, state: set):
    events = fetch_events(config)
    now    = datetime.now(pytz.utc)

    for event in events:
        uid      = event["uid"]
        start_dt = event["start_dt"]

        for mins in event["reminder_minutes"]:
            fire_dt = start_dt - timedelta(minutes=mins)
            key     = make_key(uid, f"r{mins}", start_dt)
            _schedule(scheduler, key, fire_dt, now, state,
                      lambda e=event, m=mins, k=key: _send(msg_erinnerung(e, m), k, config, state))

        start_key = make_key(uid, "start", start_dt)
        _schedule(scheduler, start_key, start_dt, now, state,
                  lambda e=event, k=start_key: _send(msg_start(e), k, config, state))


def _schedule(scheduler, key, fire_dt, now, state, fn):
    if fire_dt <= now or key in state or scheduler.get_job(key):
        return
    scheduler.add_job(fn, trigger=DateTrigger(run_date=fire_dt),
                      id=key, replace_existing=False, misfire_grace_time=120)
    log.debug("Geplant: %s um %s", key[:50], fire_dt.strftime("%d.%m. %H:%M"))


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

    config    = Config()
    state     = load_state()
    scheduler = BackgroundScheduler(timezone=config.timezone)

    def poll():
        nonlocal state
        state = purge_old(state)
        poll_and_schedule(config, scheduler, state)

    poll()  # Sofort beim Start
    scheduler.add_job(poll, trigger=IntervalTrigger(minutes=config.poll_minutes),
                      id="poll", replace_existing=True)
    scheduler.start()

    log.info(
        "Bot läuft. %d Kalender überwacht. Abfrage alle %d Minuten. (Strg+C zum Beenden)",
        len(config.calendars),
        config.poll_minutes,
    )

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
