"""Tests for sshq backends and get_backend selection."""
import pytest


def test_get_backend_prefers_local(monkeypatch):
    from sshq.backends import get_backend, _local_generate

    monkeypatch.setenv("SSHQ_USE_LOCAL", "1")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert get_backend() is _local_generate


def test_get_backend_prefers_groq_over_gemini(monkeypatch):
    from sshq.backends import get_backend, _groq_generate

    monkeypatch.delenv("SSHQ_USE_LOCAL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    assert get_backend() is _groq_generate


def test_get_backend_falls_back_to_gemini(monkeypatch):
    from sshq.backends import get_backend, _gemini_generate

    monkeypatch.delenv("SSHQ_USE_LOCAL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    assert get_backend() is _gemini_generate


def test_get_backend_raises_without_any_key(monkeypatch):
    from sshq.backends import get_backend

    monkeypatch.delenv("SSHQ_USE_LOCAL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SSHQ_USE_LOCAL|GROQ_API_KEY|GEMINI_API_KEY"):
        get_backend()
