"""Tests for sshq server /ask and /analyze endpoints."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app():
    from sshq.server import app
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def mock_backend():
    """Mock the AI backend so we never call real APIs."""
    mock = MagicMock()
    with patch("sshq.server.backend", mock):
        yield mock


# --- /ask ---


def test_ask_without_prompt_returns_400(client):
    r = client.post("/ask", json={})
    assert r.status_code == 400
    assert r.json == {"error": "No prompt provided"}

    r = client.post("/ask", json={"other": "key"}, content_type="application/json")
    assert r.status_code == 400


def test_ask_with_prompt_returns_command(client, mock_backend):
    mock_backend.return_value = "ls -la"

    r = client.post("/ask", json={"prompt": "list files"})
    assert r.status_code == 200
    assert r.json == {"command": "ls -la"}
    mock_backend.assert_called_once()


def test_ask_on_api_error_returns_500(client, mock_backend):
    mock_backend.side_effect = RuntimeError("API error")

    r = client.post("/ask", json={"prompt": "do something"})
    assert r.status_code == 500
    assert "error" in r.json
    assert "API error" in r.json["error"]


# --- /analyze ---


def test_analyze_without_prompt_or_content_returns_400(client):
    r = client.post("/analyze", json={})
    assert r.status_code == 400
    assert "prompt" in r.json["error"] and "content" in r.json["error"]

    r = client.post("/analyze", json={"prompt": "explain"})
    assert r.status_code == 400

    r = client.post("/analyze", json={"content": "some log"})
    assert r.status_code == 400


def test_analyze_with_prompt_and_content_returns_analysis(client, mock_backend):
    mock_backend.return_value = "I see 2 failures in the log."

    r = client.post(
        "/analyze",
        json={"prompt": "any failures?", "content": "ERROR: disk full\nERROR: timeout"},
    )
    assert r.status_code == 200
    assert r.json == {"analysis": "I see 2 failures in the log."}
    mock_backend.assert_called_once()


def test_analyze_on_api_error_returns_500(client, mock_backend):
    mock_backend.side_effect = RuntimeError("API error")

    r = client.post(
        "/analyze",
        json={"prompt": "explain", "content": "log line"},
    )
    assert r.status_code == 500
    assert "error" in r.json
    assert "API error" in r.json["error"]
