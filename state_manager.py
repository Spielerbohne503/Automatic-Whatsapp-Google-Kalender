import json
import logging
import os
import tempfile
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, state_file: str):
        self._state_file = state_file
        self._sent: set = set()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._state_file):
            logger.debug("Keine bestehende State-Datei gefunden, starte mit leerem Zustand.")
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._sent = set(data)
            logger.info("State geladen: %d gesendete Benachrichtigungen.", len(self._sent))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("State-Datei konnte nicht gelesen werden: %s – starte neu.", e)
            self._sent = set()

    def _save(self) -> None:
        try:
            dir_name = os.path.dirname(self._state_file) or "."
            with tempfile.NamedTemporaryFile(
                "w", dir=dir_name, delete=False, suffix=".tmp", encoding="utf-8"
            ) as tmp:
                json.dump(sorted(self._sent), tmp, ensure_ascii=False, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, self._state_file)
        except OSError as e:
            logger.error("State-Datei konnte nicht gespeichert werden: %s", e)

    def is_sent(self, key: str) -> bool:
        return key in self._sent

    def mark_sent(self, key: str) -> None:
        self._sent.add(key)
        self._save()

    def purge_old_entries(self, cutoff_dt: datetime) -> None:
        """Entfernt Einträge, deren Datum vor cutoff_dt liegt."""
        cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M")
        before = len(self._sent)
        self._sent = {
            key for key in self._sent
            if not self._is_older_than(key, cutoff_str)
        }
        removed = before - len(self._sent)
        if removed:
            logger.debug("State bereinigt: %d alte Einträge entfernt.", removed)
            self._save()

    @staticmethod
    def _is_older_than(key: str, cutoff_str: str) -> bool:
        # Key-Format: "{event_id}_{type}_{YYYY-MM-DDTHH:MM}"
        # Letztes Segment enthält das Datum
        parts = key.rsplit("_", 1)
        if len(parts) < 2:
            return False
        date_part = parts[-1]
        return date_part < cutoff_str
