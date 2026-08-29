"""Collector worker: refresh news calendar, skip closed markets, never places orders."""

from __future__ import annotations

import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for pkg in ("packages/guards", "packages/shared"):
    sys.path.insert(0, str(ROOT / pkg))

from molido_guards import SessionCalendar, refresh_calendar, default_calendar_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("molido-collector")


def ping_health() -> None:
    url = os.getenv("MOLIDO_HEALTH_URL", "http://api:8000/api/v1/health")
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            logger.info("health ping status=%s", resp.status)
    except Exception as exc:
        logger.warning("health ping failed: %s", exc)


def sweep() -> None:
    cal = SessionCalendar()
    ok, why = cal.allow_new_entries()
    sessions = cal.active_sessions()
    if not ok:
        logger.info("collector skip: %s", why)
        return
    path = default_calendar_path()
    payload = refresh_calendar(path=path)
    n = len(payload.get("events") or [])
    logger.info(
        "collector calendar refresh source=%s events=%s path=%s sessions=%s (never places orders)",
        payload.get("source"),
        n,
        path,
        sessions,
    )
    ping_health()


def main() -> None:
    logger.info("Molido collector started — writes calendar, never places orders")
    while True:
        try:
            sweep()
        except Exception:
            logger.exception("collector sweep failed")
        time.sleep(15 * 60)


if __name__ == "__main__":
    main()
