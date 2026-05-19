import os

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("META_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("MCP_SERVER_URL", "http://test-mcp/mcp")
    import main
    return TestClient(main.app), main


def test_malformed_body_returns_422(client):
    test_client, _ = client
    resp = test_client.post("/api/query", json={})
    assert resp.status_code == 422


def test_mcp_unavailable_returns_friendly_message(client, monkeypatch):
    test_client, main = client

    async def _raise(*_args, **_kwargs):
        raise main.orchestrator.MCPUnavailableError("connection refused")

    monkeypatch.setattr(main.orchestrator, "run_query", _raise)
    resp = test_client.post("/api/query", json={"query": "list campaigns"})
    assert resp.status_code == 200
    body = resp.json()
    assert "ad data service" in body["response"].lower()
    assert "connection refused" not in body["response"]
    assert "traceback" not in body["response"].lower()


def test_mcp_timeout_returns_friendly_message(client, monkeypatch):
    test_client, main = client

    async def _raise(*_args, **_kwargs):
        raise main.orchestrator.MCPTimeoutError("read timeout")

    monkeypatch.setattr(main.orchestrator, "run_query", _raise)
    resp = test_client.post("/api/query", json={"query": "list campaigns"})
    assert resp.status_code == 200
    assert "timed out" in resp.json()["response"].lower()


def test_httpx_connect_error_returns_friendly_message(client, monkeypatch):
    test_client, main = client

    async def _raise(*_args, **_kwargs):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(main.orchestrator, "run_query", _raise)
    resp = test_client.post("/api/query", json={"query": "list campaigns"})
    assert resp.status_code == 200
    assert "ad data service" in resp.json()["response"].lower()


def test_generic_exception_returns_friendly_message(client, monkeypatch):
    test_client, main = client

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("boom internal detail")

    monkeypatch.setattr(main.orchestrator, "run_query", _raise)
    resp = test_client.post("/api/query", json={"query": "list campaigns"})
    assert resp.status_code == 200
    body = resp.json()
    assert "unexpected error" in body["response"].lower()
    assert "boom internal detail" not in body["response"]
