"""Worker that writes data and decides nothing. Skips closed markets."""

from __future__ import annotations
import logging
import time
from molido_guards import SessionCalendar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("molido-collector")


def sweep() -> None:
    cal = SessionCalendar()
    ok, why = cal.allow_new_entries()
    sessions = cal.active_sessions()
    if not ok:
        logger.info("collector skip: %s", why)
        return
    logger.info("collector sweep | sessions=%s | (ingest/quality land with broker history)", sessions)


def main() -> None:
    logger.info("Molido collector started — writes data, never places orders")
    while True:
        try:
            sweep()
        except Exception:
            logger.exception("collector sweep failed")
        time.sleep(15 * 60)


if __name__ == "__main__":
    main()
