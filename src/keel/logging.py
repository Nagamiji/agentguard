import json
import logging
import sys
from typing import Any

# Standard LogRecord attributes to ignore when extracting extra context
RESERVED_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Structured JSON logs. PII/secrets must never be passed to the logger (see standards)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in RESERVED_ATTRS and value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class ContextFilter(logging.Filter):
    """Filter that injects contextvars (request_id, org_id, run_id) into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        from keel.context import get_org_id, get_request_id, get_run_id

        if not getattr(record, "request_id", None):
            record.request_id = get_request_id()
        if not getattr(record, "org_id", None):
            record.org_id = get_org_id()
        if not getattr(record, "run_id", None):
            record.run_id = get_run_id()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
