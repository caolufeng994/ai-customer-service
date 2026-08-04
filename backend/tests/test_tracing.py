"""
Tests for the full-chain tracing subsystem.

These exercise the *complete* tracing path without needing an external collector:
  - TraceId is minted + echoed on every HTTP response
  - spans are recorded per node and retrievable by TraceId
  - the trace API requires auth and returns the span tree with timing
"""
from __future__ import annotations

from app.core.trace_store import trace_store
from app.core.tracing import span, get_current_trace_id, set_current_trace_id, reset_current_trace_id


def _auth_headers(client):
    # Register + login a throwaway user to get a bearer token.
    phone = "13900001111"
    client.post("/api/auth/register", json={"phone": phone, "password": "abc123"})
    r = client.post("/api/auth/login", json={"phone_or_email": phone, "password": "abc123"})
    token = r.json().get("data", {}).get("token") or r.json().get("data", {}).get("access_token")
    return {"Authorization": f"Bearer {token}"}


def test_trace_id_echoed_on_response(client):
    # /health is public; middleware should still mint + echo a TraceId.
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-Trace-Id" in r.headers
    assert len(r.headers["X-Trace-Id"]) >= 16


def test_trace_id_reused_when_forwarded(client):
    r = client.get("/health", headers={"X-Trace-Id": "abcd1234abcd1234"})
    assert r.headers["X-Trace-Id"] == "abcd1234abcd1234"


def test_span_records_into_store():
    # Out-of-request span should still be recorded under a lazily-minted trace.
    with span("unit_span", attributes={"k": "v"}) as s:
        pass
    assert s.duration_ms >= 0
    stored = trace_store.get_trace(s.trace_id)
    assert stored is not None
    assert any(x.name == "unit_span" for x in stored)


def test_propagates_across_context(client):
    tok = set_current_trace_id("prop-test-123")
    try:
        with span("a") as a:
            with span("b") as b:
                # b is a child of a
                assert b.parent_span_id == a.span_id
                assert get_current_trace_id() == "prop-test-123"
    finally:
        reset_current_trace_id(tok)


def test_trace_api_requires_auth(client):
    r = client.get("/api/traces")
    assert r.status_code in (401, 403)


def test_authed_request_produces_retrievable_trace(client):
    headers = _auth_headers(client)
    # Hit an instrumented, lightweight authed endpoint (list_sessions span).
    r = client.get("/api/sessions", headers=headers)
    assert r.status_code == 200
    trace_id = r.headers.get("X-Trace-Id")
    assert trace_id

    # The trace should now be retrievable and contain the list_sessions span.
    tr = client.get(f"/api/traces/{trace_id}", headers=headers)
    assert tr.status_code == 200
    body = tr.json()["data"]
    assert body["trace_id"] == trace_id
    names = [s["name"] for s in body["spans"]]
    assert "list_sessions" in names
    # timing offsets must be present and non-negative
    for s in body["spans"]:
        assert s["duration_ms"] >= 0
        assert s["start_offset_ms"] >= 0


def test_trace_api_404_for_unknown(client):
    headers = _auth_headers(client)
    r = client.get("/api/traces/does-not-exist", headers=headers)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "TRACE_NOT_FOUND"
