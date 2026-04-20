"""
WhatsApp Kalender-Bot mit KI-Assistent – 100% kostenlos
- Automatische Erinnerungen aus Google Kalender (iCal)
- Zwei-Wege WhatsApp via whatsapp-web.js Bridge (gratis)
- KI-Assistent via Groq API / Llama 3.1 (gratis)
- Termin-Erstellung per natürlicher Sprache
"""

import configparser
import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

import pytz
import recurring_ical_events
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from groq import Groq
from icalendar import Calendar

# ─── Pfade ───────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
STATE_FILE  = os.path.join(BASE_DIR, "gesendet.json")
LOG_FILE    = os.path.join(BASE_DIR, "bot.log")

BRIDGE_URL = "http://127.0.0.1:3000"


# ─── Logging ─────────────────────────────────────────────────────────────────

def setup_logging():
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%d.%m.%Y %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024,
                              backupCount=3, encoding="utf-8")
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
            log.error("config.ini erstellt in: %s\nBitte ausfüllen und neu starten.", CONFIG_FILE)
            sys.exit(1)

        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_FILE, encoding="utf-8")

        wa = cfg["WhatsApp"]
        self.meine_nummer = wa.get("MeineNummer", "").strip()

        ki = cfg["KI"]
        self.groq_key = ki.get("Groq_ApiKey", "").strip()

        s = cfg["Einstellungen"]
        self.timezone     = s.get("Zeitzone", "Europe/Berlin").strip()
        self.poll_minutes = int(s.get("AbfrageIntervallMinuten", "5"))
        self.lookahead_h  = int(s.get("VorausschauStunden", "24"))
        self.allday_hour  = int(s.get("GanztaegigErinnerungUhrzeit", "8"))

        self.calendars: dict[str, str] = {}
        if "Kalender" in cfg:
            for name, url in cfg["Kalender"].items():
                url = url.strip()
                if url and url != "ICAL_URL_HIER_EINFUEGEN":
                    self.calendars[name] = url

        missing = []
        if not self.meine_nummer:
            missing.append("WhatsApp → MeineNummer")
        if not self.groq_key or self.groq_key == "HIER_EINTRAGEN":
            missing.append("KI → Groq_ApiKey")
        if not self.calendars:
            missing.append("Kalender → mindestens eine iCal-URL eintragen")
        if missing:
            log.error("Fehlende Felder in config.ini:\n  %s\nDann neu starten.",
                      "\n  ".join(missing))
            sys.exit(1)


def _create_default_config():
    content = """\
[WhatsApp]
; Deine persönliche WhatsApp-Nummer (hierhin schickt der Bot Nachrichten)
MeineNummer = +4915226310258

[KI]
; Groq API Key – kostenlos auf console.groq.com registrieren
Groq_ApiKey = HIER_EINTRAGEN

[Kalender]
; Privaten iCal-Link aus Google Kalender Einstellungen einfügen
; (Einstellungen → Kalender-Name → "Privatadresse im iCalendar-Format")
;
Arbeit      = ICAL_URL_HIER_EINFUEGEN
Privat      = ICAL_URL_HIER_EINFUEGEN
Training    = ICAL_URL_HIER_EINFUEGEN
Haushalt    = ICAL_URL_HIER_EINFUEGEN
HSG         = ICAL_URL_HIER_EINFUEGEN
Mittelalter = ICAL_URL_HIER_EINFUEGEN
Special     = ICAL_URL_HIER_EINFUEGEN
Geburtstage = ICAL_URL_HIER_EINFUEGEN
Graue_Garde = ICAL_URL_HIER_EINFUEGEN
Formula_1   = ICAL_URL_HIER_EINFUEGEN

[Einstellungen]
Zeitzone                    = Europe/Berlin
AbfrageIntervallMinuten     = 5
VorausschauStunden          = 24
GanztaegigErinnerungUhrzeit = 8
"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


# ─── iCal / Kalender lesen ───────────────────────────────────────────────────

def fetch_events(config: Config, lookahead_hours: int = None) -> list[dict]:
    tz = pytz.timezone(config.timezone)
    now = datetime.now(pytz.utc)
    time_max = now + timedelta(hours=lookahead_hours or config.lookahead_h)

    events = []
    for cal_name, ical_url in config.calendars.items():
        try:
            resp = requests.get(ical_url, timeout=15)
            resp.raise_for_status()
            cal = Calendar.from_ical(resp.content)
            instances = recurring_ical_events.of(cal).between(now, time_max)
        except Exception as e:
            log.error("Fehler Kalender '%s': %s", cal_name, e)
            continue

        for vevent in instances:
            try:
                start_dt = _parse_start(vevent, tz, config.allday_hour)
                uid = str(vevent.get("uid", "")) + f"_{cal_name}"
                events.append({
                    "uid":              uid,
                    "summary":          str(vevent.get("summary", "(Kein Titel)")),
                    "location":         str(vevent.get("location", "") or ""),
                    "start_dt":         start_dt,
                    "reminder_minutes": _parse_reminders(vevent),
                    "calendar":         cal_name,
                })
            except Exception:
                pass

    events.sort(key=lambda e: e["start_dt"])
    return events


def _parse_start(vevent, tz, allday_hour: int) -> datetime:
    dtstart = vevent.get("dtstart")
    if dtstart is None:
        raise ValueError("Kein dtstart")
    val = dtstart.dt
    if isinstance(val, datetime):
        return val.astimezone(tz) if val.tzinfo else tz.localize(val)
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
            m = int(-val.total_seconds() / 60)
            if m > 0:
                mins.append(m)
    return sorted(set(mins)) if mins else [30]


# ─── WhatsApp Bridge (kommuniziert mit whatsapp-bridge/index.js) ─────────────

class WhatsApp:
    def __init__(self, my_phone: str):
        self._phone = my_phone
        # Chat-ID Format für whatsapp-web.js: "4915226310258@c.us"
        self._my_chat_id = my_phone.lstrip("+").replace(" ", "") + "@c.us"

    def send(self, message: str) -> bool:
        try:
            r = requests.post(f"{BRIDGE_URL}/send",
                              json={"phone": self._phone, "message": message},
                              timeout=10)
            if r.status_code == 200:
                log.info("WhatsApp gesendet: %s", message[:80])
                return True
            log.error("Bridge Fehler (HTTP %d): %s", r.status_code, r.text[:100])
            return False
        except requests.RequestException as e:
            log.error("Bridge nicht erreichbar: %s", e)
            return False

    def receive(self) -> str | None:
        """Gibt den Text der nächsten Nachricht zurück (nur von MeineNummer)."""
        try:
            r = requests.get(f"{BRIDGE_URL}/receive", timeout=5)
            if r.status_code == 200 and r.text and r.text != "null":
                data = r.json()
                if data and data.get("from") == self._my_chat_id:
                    return data.get("text")
        except requests.RequestException:
            pass
        return None

    def bridge_online(self) -> bool:
        try:
            r = requests.get(f"{BRIDGE_URL}/status", timeout=3)
            return r.status_code == 200 and r.json().get("connected", False)
        except Exception:
            return False


# ─── KI-Assistent (Groq / Llama 3.1 – kostenlos) ────────────────────────────

SYSTEM_PROMPT = """\
Du bist ein persönlicher KI-Kalender-Assistent der über WhatsApp antwortet.
Antworte auf Deutsch, kurz und freundlich (WhatsApp-Stil, kein Markdown).
Heute ist: {today}

Anstehende Termine (nächste 7 Tage):
{events}

Was du kannst:
1. Termine abfragen: "Was hab ich morgen?", "Nächster Termin?", "Diese Woche?"
2. Neuen Termin erstellen: Wenn der Nutzer einen Termin nennt, gib einen Google-Kalender-Link zurück.
   Format: Schreib genau diese Zeile: LINK: https://calendar.google.com/calendar/r/eventedit?text=TITEL&dates=YYYYMMDDTHHMMSS/YYYYMMDDTHHMMSS
   Der Endtermin ist 1 Stunde nach dem Start wenn nicht anders angegeben.
   Erkläre danach kurz: "Tippe auf den Link um den Termin zu speichern."
3. Allgemeine Fragen zur Terminplanung beantworten.

Zeitzone: Europe/Berlin. Alle Zeiten in UTC+2 (Sommerzeit) oder UTC+1 (Winterzeit) umrechnen.
"""


class KI:
    def __init__(self, api_key: str, config: Config):
        self._client = Groq(api_key=api_key)
        self._config = config

    def antworten(self, nachricht: str, events: list[dict]) -> str:
        tz = pytz.timezone(self._config.timezone)
        today = datetime.now(tz).strftime("%A, %d.%m.%Y %H:%M Uhr")
        events_text = self._events_zu_text(events, tz)
        system = SYSTEM_PROMPT.format(today=today, events=events_text)
        try:
            resp = self._client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=600,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": nachricht},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.error("Groq API Fehler: %s", e)
            return "Entschuldigung, ich konnte deine Anfrage gerade nicht verarbeiten."

    @staticmethod
    def _events_zu_text(events: list[dict], tz) -> str:
        if not events:
            return "Keine Termine in den nächsten 7 Tagen."
        lines = []
        for e in events:
            dt = e["start_dt"].astimezone(tz).strftime("%a %d.%m. %H:%M")
            ort = f" ({e['location']})" if e.get("location") else ""
            cal = f" [{e['calendar']}]" if e.get("calendar") else ""
            lines.append(f"- {dt}: {e['summary']}{ort}{cal}")
        return "\n".join(lines)


# ─── State (Duplikat-Schutz für Erinnerungen) ────────────────────────────────

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
        with tempfile.NamedTemporaryFile("w", dir=dn, delete=False,
                                         suffix=".tmp", encoding="utf-8") as tmp:
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


# ─── Automatische Erinnerungen ───────────────────────────────────────────────

def poll_and_schedule(config: Config, whatsapp: WhatsApp,
                      scheduler: BackgroundScheduler, state: set):
    events = fetch_events(config)
    now = datetime.now(pytz.utc)
    for event in events:
        uid, start_dt = event["uid"], event["start_dt"]
        for mins in event["reminder_minutes"]:
            fire_dt = start_dt - timedelta(minutes=mins)
            key = make_key(uid, f"r{mins}", start_dt)
            _schedule(scheduler, key, fire_dt, now, state,
                      lambda e=event, m=mins, k=key:
                      _send_reminder(whatsapp, e, m, k, state))
        start_key = make_key(uid, "start", start_dt)
        _schedule(scheduler, start_key, start_dt, now, state,
                  lambda e=event, k=start_key:
                  _send_start(whatsapp, e, k, state))


def _schedule(scheduler, key, fire_dt, now, state, fn):
    if fire_dt <= now or key in state or scheduler.get_job(key):
        return
    scheduler.add_job(fn, trigger=DateTrigger(run_date=fire_dt),
                      id=key, replace_existing=False, misfire_grace_time=120)


def _send_reminder(whatsapp: WhatsApp, event: dict, mins: int, key: str, state: set):
    if key in state:
        return
    zeit = event["start_dt"].strftime("%H:%M")
    if mins >= 60 and mins % 60 == 0:
        h = mins // 60
        label = f"{h} Stunde{'n' if h > 1 else ''}"
    elif mins >= 60:
        label = f"{mins // 60}h {mins % 60}min"
    else:
        label = f"{mins} Minuten"
    msg = f"Erinnerung: {event['summary']} startet in {label} ({zeit} Uhr)"
    if event.get("location"):
        msg += f" – {event['location']}"
    if whatsapp.send(msg):
        state.add(key)
        save_state(state)


def _send_start(whatsapp: WhatsApp, event: dict, key: str, state: set):
    if key in state:
        return
    zeit = event["start_dt"].strftime("%H:%M")
    msg = f"Jetzt gestartet: {event['summary']} ({zeit} Uhr)"
    if event.get("location"):
        msg += f" – {event['location']}"
    if whatsapp.send(msg):
        state.add(key)
        save_state(state)


# ─── Nachrichten-Loop ────────────────────────────────────────────────────────

_events_cache:      list[dict]       = []
_events_cache_zeit: datetime | None  = None
_cache_lock = threading.Lock()


def get_events_cached(config: Config) -> list[dict]:
    global _events_cache, _events_cache_zeit
    with _cache_lock:
        now = datetime.now(pytz.utc)
        if (_events_cache_zeit is None or
                (now - _events_cache_zeit).total_seconds() > 300):
            _events_cache = fetch_events(config, lookahead_hours=7 * 24)
            _events_cache_zeit = now
        return _events_cache


def message_loop(config: Config, whatsapp: WhatsApp, ki: KI,
                 stop_event: threading.Event):
    log.info("Nachrichten-Loop gestartet. Warte auf eingehende Nachrichten...")
    while not stop_event.is_set():
        try:
            text = whatsapp.receive()
            if text:
                log.info("Eingehende Nachricht: %s", text[:60])
                events = get_events_cached(config)
                antwort = ki.antworten(text, events)
                whatsapp.send(antwort)
        except Exception as e:
            log.error("Fehler im Nachrichten-Loop: %s", e)
        time.sleep(3)


# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def main():
    setup_logging()
    log.info("WhatsApp Kalender-Bot mit KI startet...")

    config    = Config()
    whatsapp  = WhatsApp(config.meine_nummer)
    ki        = KI(config.groq_key, config)
    state     = load_state()
    scheduler = BackgroundScheduler(timezone=config.timezone)
    stop_event = threading.Event()

    # Auf Bridge warten
    log.info("Warte auf WhatsApp-Bridge (whatsapp-bridge muss laufen)...")
    for i in range(30):
        if whatsapp.bridge_online():
            log.info("WhatsApp-Bridge verbunden.")
            break
        if i == 0:
            log.info("Bridge noch nicht bereit – warte bis zu 60 Sekunden...")
        time.sleep(2)
    else:
        log.error(
            "WhatsApp-Bridge nicht erreichbar!\n"
            "Bitte zuerst start.bat ausführen (startet Bridge + Bot zusammen)."
        )
        sys.exit(1)

    def poll():
        nonlocal state
        state = purge_old(state)
        poll_and_schedule(config, whatsapp, scheduler, state)
        with _cache_lock:
            global _events_cache, _events_cache_zeit
            _events_cache = []
            _events_cache_zeit = None

    poll()
    scheduler.add_job(poll, trigger=IntervalTrigger(minutes=config.poll_minutes),
                      id="poll", replace_existing=True)
    scheduler.start()

    msg_thread = threading.Thread(
        target=message_loop,
        args=(config, whatsapp, ki, stop_event),
        daemon=True,
    )
    msg_thread.start()

    log.info("Bot läuft! %d Kalender überwacht. Schreib mir auf WhatsApp!", len(config.calendars))

    def shutdown(sig=None, frame=None):
        log.info("Bot wird beendet...")
        stop_event.set()
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
