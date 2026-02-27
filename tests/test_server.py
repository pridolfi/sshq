"""Tests for sshq server /ask endpoint."""
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
