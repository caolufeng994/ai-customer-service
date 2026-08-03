"""
Trace retrieval API.

Exposes the in-process trace store so a single request's full call chain
(spans with per-node timing, status and attributes) can be fetched and rendered
by the frontend viewer — no external collector required.
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.core.trace_store import trace_store
from app.core.tracing import Span
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.core.response import ApiResponse

router = APIRouter(prefix="/api/traces", tags=["traces"])


def _serialize(trace_id: str) -> Dict:
    spans: List[Span] = trace_store.get_trace(trace_id)
    if not spans:
        return None

    by_id = {s.span_id: {"span": s, "children": []} for s in spans}
    roots = []
    for s in spans:
        node = by_id[s.span_id]
        if s.parent_span_id and s.parent_span_id in by_id:
            by_id[s.parent_span_id]["children"].append(node)
        else:
            roots.append(node)

    starts = [s.start_ms for s in spans]
    base = min(starts)

    def conv(node: Dict) -> Dict:
        s: Span = node["span"]
        return {
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "start_offset_ms": round(s.start_ms - base, 2),
            "duration_ms": s.duration_ms,
            "end_offset_ms": round(s.end_effective - base, 2),
            "status": s.status,
            "error": s.error,
            "attributes": s.attributes,
            "children": [conv(c) for c in node["children"]],
        }

    return {
        "trace_id": trace_id,
        "base_ms": base,
        "total_ms": round(max(s.end_effective for s in spans) - base, 2),
        "status": "error" if any(s.status == "error" for s in spans) else "ok",
        "spans": [conv(r) for r in roots],
    }


@router.get("")
def list_traces(limit: int = 50, current_user: User = Depends(get_current_user)):
    """List the most recent traces (newest first)."""
    return ApiResponse.ok(data=trace_store.list_traces(limit=min(limit, 200)))


@router.get("/{trace_id}")
def get_trace(trace_id: str, current_user: User = Depends(get_current_user)):
    """Return one trace as a span tree with timing offsets and attributes."""
    data = _serialize(trace_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail={"code": "TRACE_NOT_FOUND", "message": "trace not found"},
        )
    return ApiResponse.ok(data=data)
