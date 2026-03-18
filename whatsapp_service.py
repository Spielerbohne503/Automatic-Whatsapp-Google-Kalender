import logging
import urllib.parse
from datetime import datetime

import requests

from config import Config

logger = logging.getLogger(__name__)

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


class WhatsAppService:
    def __init__(self, config: Config):
        self._config = config

    def send_message(self, message: str) -> bool:
        params = {
            "phone": self._config.whatsapp_phone,
            "text": message,
            "apikey": self._config.callmebot_api_key,
        }
        try:
            response = requests.get(CALLMEBOT_URL, params=params, timeout=15)
            if response.status_code == 200:
                logger.info("WhatsApp-Nachricht gesendet: %s", message[:60])
                return True
            else:
                logger.error(
                    "WhatsApp-Versand fehlgeschlagen (HTTP %d): %s",
                    response.status_code,
                    response.text[:200],
                )
                return False
        except requests.RequestException as e:
            logger.error("WhatsApp-Netzwerkfehler: %s", e)
            return False

    def format_reminder_message(
        self, event: dict, minutes_before: int, start_dt: datetime
    ) -> str:
        title = event.get("summary", "(Kein Titel)")
        time_str = start_dt.strftime("%H:%M")
        location = event.get("location", "")

        if minutes_before >= 60 and minutes_before % 60 == 0:
            hours = minutes_before // 60
            time_label = f"{hours} Stunde{'n' if hours > 1 else ''}"
        elif minutes_before >= 60:
            hours = minutes_before // 60
            mins = minutes_before % 60
            time_label = f"{hours}h {mins}min"
        else:
            time_label = f"{minutes_before} Minuten"

        msg = f"Erinnerung: {title} startet in {time_label} ({time_str} Uhr)"
        if location:
            msg += f" – {location}"
        return msg

    def format_start_message(self, event: dict, start_dt: datetime) -> str:
        title = event.get("summary", "(Kein Titel)")
        time_str = start_dt.strftime("%H:%M")
        location = event.get("location", "")

        msg = f"Jetzt gestartet: {title} ({time_str} Uhr)"
        if location:
            msg += f" – {location}"
        return msg
