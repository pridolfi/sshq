"""Tests for sshq CLI."""
import os
import sys
from unittest.mock import patch

import pytest


def run_main(argv, env=None, prog="sshq", clear_env=False):
    """Run cli.main with given argv and env; return (exit_code, stdout, stderr)."""
    env = dict(env or os.environ)
    with patch.object(sys, "argv", [prog] + argv), patch.dict(
        os.environ, env, clear=clear_env
    ):
        from io import StringIO

        out = StringIO()
        err = StringIO()
        with patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
            try:
                from sshq.cli import main

                main()
                return 0, out.getvalue(), err.getvalue()
            except SystemExit as e:
                return (e.code if e.code is not None else 0), out.getvalue(), err.getvalue()


def test_no_args_shows_usage_and_exits_nonzero():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
        code, out, err = run_main([])
    assert code != 0
    assert "Usage:" in out
    assert "user@host" in out
    assert err == ""


def test_usage_shows_invoked_prog_name():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
        code, out, err = run_main([], prog="/some/path/my-sshq")
    assert code != 0
    assert "my-sshq" in out


@pytest.mark.parametrize("argv", [["--version"], ["-V"]])
def test_version_exits_zero_and_prints_version(argv):
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
        code, out, err = run_main(argv)
    assert code == 0
    assert out.strip() == "0.1.0"
    assert err == ""


def test_missing_gemini_api_key_exits_nonzero_and_prints_to_stderr():
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    code, out, err = run_main(["user@host"], env=env, clear_env=True)
    assert code != 0
    assert "GEMINI_API_KEY" in err
    assert "not set" in err
