"""``terminal.ssh_sync_files`` gates the ssh backend's host<->remote .hermes mirror.

The sync-back tars the remote's ENTIRE ``$HOME/.hermes`` on every sync, before the size cap is
even consulted. A backend pointed at a host that already holds the files (a self-hosted VPS, or
this very machine) therefore pays a multi-GB copy per terminal session inside the gateway event
loop. The toggle lets that topology opt out without touching any other backend.
"""

import pytest

from tools import terminal_tool_backends as backends


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    class _Stub:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(backends, "_SSHEnvironment", _Stub)
    return seen


SSH_CONFIG = {"host": "127.0.0.1", "user": "root", "key": "/tmp/key", "port": 22}


def _build(monkeypatch, terminal_config):
    monkeypatch.setattr(backends, "_terminal_config", lambda: terminal_config)
    return backends._build_ssh_env(cwd="~", timeout=30, ssh_config=dict(SSH_CONFIG))


def test_sync_files_disabled_by_config(monkeypatch, captured):
    _build(monkeypatch, {"ssh_sync_files": False})
    assert captured["sync_files"] is False
    assert captured["host"] == "127.0.0.1"


def test_sync_files_defaults_on_when_unset(monkeypatch, captured):
    _build(monkeypatch, {})
    assert captured["sync_files"] is True


def test_sync_files_can_be_explicitly_on(monkeypatch, captured):
    _build(monkeypatch, {"ssh_sync_files": True})
    assert captured["sync_files"] is True


def test_terminal_config_never_raises(monkeypatch):
    def _boom():
        raise RuntimeError("unreadable config")

    import hermes_cli.config as config

    monkeypatch.setattr(config, "load_config", _boom)
    assert backends._terminal_config() == {}
