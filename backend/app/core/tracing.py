"""
Self-contained distributed-tracing core (no external collector required).

Provides the three capabilities the project was missing:
  1. Request-scoped TraceId (contextvar) + X-Trace-Id header propagation.
  2. Per-node Span timing & status (intent -> route -> retrieve -> context -> LLM).
  3. TraceId correlation: every log line and every span carries the same trace_id,
     and a built-in in-process TraceStore makes a single request's full chain
     retrievable/visualizable without ELK/Jaeger.

Design notes:
  * contextvars are used so the trace_id / span stack survive across async hops
    within one request but stay isolated between concurrent requests.
  * A Span created outside any request (e.g. a background task) lazily mints its
    own trace_id, so it is still recorded rather than dropped.
  * This is intentionally framework-light; an OpenTelemetry export hook can be
    added later without touching call sites (the Span shape is OTel-compatible).
"""
from __future__ import annotations

import contextvars
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import Request, Depends

# --- request-scoped context ---
_trace_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_span_stack_ctx: contextvars.ContextVar[Optional["Span"]] = contextvars.ContextVar(
    "span_stack", default=None
)


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def get_current_trace_id() -> Optional[str]:
    return _trace_id_ctx.get()


def set_current_trace_id(tid: str) -> contextvars.Token:
    return _trace_id_ctx.set(tid)


def reset_current_trace_id(token: contextvars.Token) -> None:
    _trace_id_ctx.reset(token)


@dataclass
class Span:
    """One node in a trace. OTel-compatible shape (trace_id/span_id/parent/status)."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_ms: float
    end_ms: Optional[float] = None
    duration_ms: float = 0.0
    status: str = "ok"  # "ok" | "error"
    error: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status_error(self, msg: str) -> None:
        self.status = "error"
        self.error = msg

    def finish(self) -> None:
        self.end_ms = time.time() * 1000
        self.duration_ms = round(self.end_ms - self.start_ms, 3)

    @property
    def end_effective(self) -> float:
        """Effective end time; falls back to start_ms while the span is still open."""
        return self.end_ms if self.end_ms is not None else self.start_ms


def _ensure_trace_id() -> str:
    tid = _trace_id_ctx.get()
    if not tid:
        tid = generate_trace_id()
        _trace_id_ctx.set(tid)
    return tid


class _SpanCtx:
    """Context-manager that records one span and pushes it onto the span stack."""

    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.name = name
        self.attributes = attributes or {}
        self.span: Optional[Span] = None
        self._token = None

    def __enter__(self) -> Span:
        tid = _ensure_trace_id()
        parent = _span_stack_ctx.get()
        self.span = Span(
            trace_id=tid,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=parent.span_id if parent else None,
            name=self.name,
            start_ms=time.time() * 1000,
            attributes=dict(self.attributes),
        )
        self._token = _span_stack_ctx.set(self.span)
        return self.span

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.span is not None:
                if exc_type is not None:
                    self.span.set_status_error(f"{exc_type.__name__}: {exc}")
                self.span.finish()
                # local import avoids a circular import at module load
                from app.core.trace_store import trace_store

                trace_store.add_span(self.span)
        finally:
            if self._token is not None:
                _span_stack_ctx.reset(self._token)
        return False  # do not suppress exceptions


def span(name: str, attributes: Optional[Dict[str, Any]] = None) -> _SpanCtx:
    """Context manager: with span("retrieve") as s: ..."""
    return _SpanCtx(name, attributes)


class TraceIdFilter(logging.Filter):
    """Injects the current trace_id into every log record so all lines of one
    request share the same `record.trace_id` (rendered by the formatter)."""

    def filter(self, record: logging.LogRecord) -> bool:
        tid = get_current_trace_id()
        record.trace_id = tid if tid else "-"
        return True


async def trace_context(request: Request):
    """FastAPI dependency that re-asserts the request TraceId contextvar INSIDE
    the endpoint's own task.

    The raw ASGI middleware sets the contextvar, but under some ASGI servers the
    endpoint runs in a different task and loses it. `request.state.trace_id` was
    stashed by the middleware, so this dependency restores it for the duration of
    the request — guaranteeing every downstream span shares the same TraceId that
    is echoed on the response.
    """
    tid = getattr(request.state, "trace_id", None) or generate_trace_id()
    token = set_current_trace_id(tid)
    try:
        yield
    finally:
        reset_current_trace_id(token)
