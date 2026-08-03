"""
In-process trace store.

Keeps the most recent N traces (span lists) in memory so a single request's full
call chain can be retrieved and visualized without an external collector. For a
multi-worker / horizontally-scaled deployment this would be swapped for Redis or a
real tracing backend (OTel + Jaeger); the public API (add_span / get_trace /
list_traces) would stay the same.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional

from app.core.tracing import Span


class TraceStore:
    def __init__(self, max_traces: int = 500):
        self._traces: Dict[str, List[Span]] = {}
        self._order: deque = deque()
        self._max = max_traces

    def add_span(self, span: Span) -> None:
        tid = span.trace_id
        if tid not in self._traces:
            self._traces[tid] = []
            self._order.append(tid)
            if len(self._order) > self._max:
                old = self._order.popleft()
                self._traces.pop(old, None)
        self._traces[tid].append(span)

    def get_trace(self, trace_id: str) -> Optional[List[Span]]:
        return self._traces.get(trace_id)

    def list_traces(self, limit: int = 50) -> List[dict]:
        out: List[dict] = []
        for tid in list(self._order)[-limit:][::-1]:
            spans = self._traces.get(tid)
            if not spans:
                continue
            starts = [s.start_ms for s in spans]
            ends = [s.end_effective for s in spans]
            out.append(
                {
                    "trace_id": tid,
                    "root_name": spans[0].name,
                    "span_count": len(spans),
                    "total_ms": round(max(ends) - min(starts), 1),
                    "status": "error" if any(s.status == "error" for s in spans) else "ok",
                    "start_ms": min(starts),
                }
            )
        return out


# Module-level singleton (single process). Tests share this instance by design.
trace_store = TraceStore()
