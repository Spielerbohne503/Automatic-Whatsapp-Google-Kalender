import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    whatsapp_phone: str
    callmebot_api_key: str
    google_calendar_id: str
    timezone: str
    poll_interval_minutes: int
    lookahead_hours: int
    all_day_reminder_hour: int
    token_file: str
    credentials_file: str
    state_file: str


def load_config() -> Config:
    required = {
        "WHATSAPP_PHONE": os.getenv("WHATSAPP_PHONE"),
        "CALLMEBOT_API_KEY": os.getenv("CALLMEBOT_API_KEY"),
        "GOOGLE_CALENDAR_ID": os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        "TIMEZONE": os.getenv("TIMEZONE", "Europe/Berlin"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(
            f"Fehlende Pflichtfelder in .env: {', '.join(missing)}\n"
            "Bitte kopiere .env.example nach .env und fülle alle Felder aus."
        )

    def parse_int(key: str, default: int) -> int:
        raw = os.getenv(key, str(default))
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"Ungültiger Wert für {key}: '{raw}' (muss eine ganze Zahl sein)")

    return Config(
        whatsapp_phone=required["WHATSAPP_PHONE"],
        callmebot_api_key=required["CALLMEBOT_API_KEY"],
        google_calendar_id=required["GOOGLE_CALENDAR_ID"],
        timezone=required["TIMEZONE"],
        poll_interval_minutes=parse_int("POLL_INTERVAL_MINUTES", 5),
        lookahead_hours=parse_int("LOOKAHEAD_HOURS", 24),
        all_day_reminder_hour=parse_int("ALL_DAY_REMINDER_HOUR", 8),
        token_file=os.getenv("TOKEN_FILE", "token.json"),
        credentials_file=os.getenv("CREDENTIALS_FILE", "credentials.json"),
        state_file=os.getenv("STATE_FILE", "sent_notifications.json"),
    )
