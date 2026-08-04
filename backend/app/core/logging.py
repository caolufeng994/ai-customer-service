"""
Logging Configuration Module

Two responsibilities:
  1. Provide a resilient formatter that always renders ``%(trace_id)s`` on every
     log line (defaulting to ``-`` when no request context exists), so all log
     lines of one request can be correlated — and so a record that somehow
     bypasses the TraceIdFilter can never crash the handler with a KeyError.
  2. Build a uvicorn-compatible ``log_config`` dict that reuses the same
     formatter + filter, so that when uvicorn takes over the root logger it
     KEEPS the trace_id rendering instead of silently dropping it.
"""
import logging
from typing import Dict, Any

from app.config import settings


class TraceFormatter(logging.Formatter):
    """Formatter that always renders ``%(trace_id)s``.

    A plain ``logging.Formatter`` with ``%(trace_id)s`` in its format string
    raises ``ValueError: Formatting field not found in record`` whenever a log
    record reaches the handler *without* the ``trace_id`` attribute (e.g. a
    record emitted by a logger that does not propagate to the root filter, or a
    record created before/after a request context exists). This subclass makes
    the attribute always present, so formatting is guaranteed safe.
    """

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return super().format(record)


class TraceAccessFormatter(logging.Formatter):
    """Access-log formatter compatible with uvicorn's ``AccessLogger``.

    uvicorn emits access lines via ``access_logger.info('%s - "%s %s HTTP/%s"
    %d', client_addr, method, full_path, http_version, status)``, so
    ``record.args`` is a 5-tuple — NOT ``%(client_addr)s``-style attributes.
    uvicorn's own ``AccessFormatter`` unpacks that tuple to synthesize
    ``client_addr``/``request_line``/``status_code`` before formatting. We mirror
    that unpacking and additionally surface ``trace_id`` (defaulting to ``-``
    when no request context exists) for request correlation.
    """

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        args = record.args
        try:
            client_addr, method, full_path, http_version, status_code = args
        except (TypeError, ValueError):
            # Not a uvicorn access record — fall back to the standard trace line.
            return super().format(record)
        request_line = f"{method} {full_path} HTTP/{http_version}"
        return (
            f"{self.formatTime(record)} - {record.levelname} - {record.name} "
            f"- [trace={record.trace_id}] - "
            f'{client_addr} - "{request_line}" {status_code}'
        )


_DEFAULT_FMT = (
    "%(asctime)s - %(levelname)s - %(name)s - [trace=%(trace_id)s] - %(message)s"
)


def build_log_config(level: str = "INFO") -> Dict[str, Any]:
    """Return a dictConfig-style logging config used by both ``setup_logging``
    and uvicorn. Centralizes the trace_id formatter + filter so every handler
    (root, uvicorn, uvicorn.access) renders ``%(trace_id)s`` and is crash-safe.
    """
    lvl = level.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "trace": {
                "()": "app.core.logging.TraceFormatter",
                "fmt": _DEFAULT_FMT,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "access": {
                "()": "app.core.logging.TraceAccessFormatter",
                "fmt": _DEFAULT_FMT,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": {
            "trace": {"()": "app.core.tracing.TraceIdFilter"},
        },
        "handlers": {
            "default": {
                "formatter": "trace",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["trace"],
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["trace"],
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": lvl, "propagate": False},
            "uvicorn.error": {"level": lvl},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": lvl,
                "propagate": False,
            },
        },
        "root": {"handlers": ["default"], "level": lvl},
    }


def setup_logging() -> Dict[str, Any]:
    """Configure application logging.

    Applies our centralized log config (trace_id formatter + filter) directly,
    so it works for both standalone use and as the basis uvicorn inherits when
    ``main.py`` passes the same config to ``uvicorn.run(log_config=...)``.
    Returns the config dict (handy for passing straight to uvicorn).
    """
    import logging.config

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    config = build_log_config(logging.getLevelName(log_level))
    logging.config.dictConfig(config)
    return config
