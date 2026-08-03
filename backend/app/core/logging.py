"""
Logging Configuration Module
"""
import logging
import sys
from app.config import settings
from app.core.tracing import TraceIdFilter


def setup_logging():
    """Configure application logging"""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Structured-ish format that carries the request trace_id on every line so
    # all log records of one request can be correlated by grep / log UI.
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - [trace=%(trace_id)s] - %(message)s'
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger. The TraceIdFilter on the root logger (below) guarantees
    # every record — including uvicorn access logs that bypass this handler — carries
    # `trace_id`, so the formatter never hits a missing attribute.
    logging.basicConfig(level=log_level, handlers=[handler])

    # Ensure every record (including ones from loggers that bypass our handler,
    # e.g. uvicorn access logs) still has `trace_id` set, so the format string
    # never hits a missing attribute.
    logging.getLogger().addFilter(TraceIdFilter())

    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("fastapi").setLevel(log_level)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
