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
def mock_genai_client():
    """Mock the genai client so we never call the real API."""
    mock = MagicMock()
    with patch("sshq.server.client", mock):
        yield mock


# --- /ask ---


def test_ask_without_prompt_returns_400(client):
    r = client.post("/ask", json={})
    assert r.status_code == 400
    assert r.json == {"error": "No prompt provided"}

    r = client.post("/ask", json={"other": "key"}, content_type="application/json")
    assert r.status_code == 400


def test_ask_with_prompt_returns_command(client, mock_genai_client):
    mock_response = MagicMock()
    mock_response.text = "  ls -la\n"
    mock_genai_client.models.generate_content.return_value = mock_response

    r = client.post("/ask", json={"prompt": "list files"})
    assert r.status_code == 200
    assert r.json == {"command": "ls -la"}
    mock_genai_client.models.generate_content.assert_called_once()


def test_ask_on_api_error_returns_500(client, mock_genai_client):
    mock_genai_client.models.generate_content.side_effect = RuntimeError("API error")

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


def test_analyze_with_prompt_and_content_returns_analysis(client, mock_genai_client):
    mock_response = MagicMock()
    mock_response.text = "I see 2 failures in the log."
    mock_genai_client.models.generate_content.return_value = mock_response

    r = client.post(
        "/analyze",
        json={"prompt": "any failures?", "content": "ERROR: disk full\nERROR: timeout"},
    )
    assert r.status_code == 200
    assert r.json == {"analysis": "I see 2 failures in the log."}
    mock_genai_client.models.generate_content.assert_called_once()


def test_analyze_on_api_error_returns_500(client, mock_genai_client):
    mock_genai_client.models.generate_content.side_effect = RuntimeError("API error")

    r = client.post(
        "/analyze",
        json={"prompt": "explain", "content": "log line"},
    )
    assert r.status_code == 500
    assert "error" in r.json
    assert "API error" in r.json["error"]
