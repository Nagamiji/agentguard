from __future__ import annotations

import logging
import signal
import sys
import time
from types import FrameType

import redis

from keel.config import settings
from keel.logging import configure_logging

logger = logging.getLogger("worker")

STREAM = "keel:runs"
GROUP = "keel-workers"
CONSUMER = "worker-1"

_running = True


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _running
    _running = False


def ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def process(message_id: str) -> None:
    # Idempotent stub. Real eval-run dispatch lands in BE-04 / EVAL-01.
    logger.info("processing run", extra={"message_id": message_id})


def main() -> int:
    configure_logging(settings.log_level)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    ensure_group(client)
    logger.info("worker started", extra={"message_id": STREAM})
    while _running:
        try:
            resp = client.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=10, block=2000)
        except redis.RedisError:
            logger.exception("redis read failed; backing off")
            time.sleep(1)
            continue
        if not resp:
            continue
        for _stream, messages in resp:
            for message_id, _data in messages:
                process(message_id)
                client.xack(STREAM, GROUP, message_id)
    logger.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
