"""
Trading Engine entry point — LIVE by default.
"""

from __future__ import annotations
import asyncio
import logging

from app.live.runner import LiveRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("trading-engine")


async def run() -> None:
    logger.info("Starting Molido Trading Engine — LIVE")
    runner = LiveRunner()
    await runner.start()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted")
