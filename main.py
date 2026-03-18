import logging
import signal
import sys
import time

from config import load_config
from calendar_service import CalendarService, CalendarAuthError
from whatsapp_service import WhatsAppService
from state_manager import StateManager
from scheduler import ReminderScheduler


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%d.%m.%Y %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger("main")

    logger.info("WhatsApp Kalender-Bot wird gestartet...")

    try:
        config = load_config()
    except ValueError as e:
        logger.error("Konfigurationsfehler:\n%s", e)
        sys.exit(1)

    calendar_service = CalendarService(config)
    try:
        calendar_service.authenticate()
    except CalendarAuthError as e:
        logger.error("Google Authentifizierung fehlgeschlagen:\n%s", e)
        sys.exit(1)

    whatsapp_service = WhatsAppService(config)
    state_manager = StateManager(config.state_file)
    scheduler = ReminderScheduler(config, calendar_service, whatsapp_service, state_manager)

    def handle_shutdown(sig, frame):
        logger.info("Beendigungssignal empfangen. Bot wird gestoppt...")
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info(
        "Bot läuft. Kalender '%s' wird alle %d Minuten abgefragt. (Strg+C zum Beenden)",
        config.google_calendar_id,
        config.poll_interval_minutes,
    )

    scheduler.start()

    # Hauptthread am Laufen halten
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        handle_shutdown(None, None)


if __name__ == "__main__":
    main()
