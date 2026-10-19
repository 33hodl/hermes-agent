"""A non-interactive OAuth failure must be remembered across processes.

A cron/oneshot agent starts with an empty in-process auth-park table, so without a marker it
replayed the same rejected refresh token (a guaranteed 400), then entered the authorization-code
flow only to be refused by the non-interactive guard — once per OAuth server per process. Production
logged 883 such SDK tracebacks in two days from this loop. The marker is stamped with the
credentials it failed on, so a real `hermes mcp login` invalidates it.
"""

import asyncio
import json

import pytest


@pytest.mark.no_isolate
def test_marker_invalidates_when_credentials_are_rewritten(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from tools.mcp_oauth import HermesTokenStorage

    storage = HermesTokenStorage("cloud")
    tokens = storage._tokens_path()
    tokens.parent.mkdir(parents=True, exist_ok=True)
    tokens.write_text(json.dumps({"access_token": "a", "refresh_token": "dead"}))

    assert not storage.background_reauth_required()
    storage.record_background_reauth_required()
    assert storage.background_reauth_required()

    # A re-authorization rewrites the token file: the marker no longer describes reality.
    tokens.write_text(json.dumps({"access_token": "b", "refresh_token": "new"}))
    assert not storage.background_reauth_required()


@pytest.mark.no_isolate
def test_set_tokens_clears_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from tools.mcp_oauth import HermesTokenStorage

    storage = HermesTokenStorage("cloud")
    storage.record_background_reauth_required()
    assert storage.background_reauth_required()

    from mcp.shared.auth import OAuthToken
    asyncio.run(storage.set_tokens(OAuthToken(access_token="fresh", token_type="Bearer",
                                              expires_in=3600, refresh_token="new")))
    assert not storage.background_reauth_required()


@pytest.mark.no_isolate
def test_non_interactive_redirect_handler_records_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from tools import mcp_oauth

    storage = mcp_oauth.HermesTokenStorage("cloud")
    handler = mcp_oauth._make_redirect_handler(27890, storage=storage)
    monkeypatch.setattr(mcp_oauth, "_is_interactive", lambda: False)

    with pytest.raises(mcp_oauth.OAuthNonInteractiveError):
        asyncio.run(handler("https://auth.example.test/authorize?x=1"))
    assert storage.background_reauth_required()


@pytest.mark.no_isolate
def test_provider_build_parks_on_a_remembered_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from tools import mcp_oauth, mcp_oauth_manager

    storage = mcp_oauth.HermesTokenStorage("cloud")
    storage._tokens_path().parent.mkdir(parents=True, exist_ok=True)
    storage._tokens_path().write_text(json.dumps({"access_token": "a", "refresh_token": "dead"}))
    storage.record_background_reauth_required()

    monkeypatch.setattr(mcp_oauth, "_is_interactive", lambda: False)
    monkeypatch.setattr(mcp_oauth_manager, "_HERMES_PROVIDER_CLS", object())

    from tools.mcp_oauth_provider import prepare_oauth_config
    monkeypatch.setattr(mcp_oauth_manager, "prepare_oauth_config",
                        lambda name, url, cfg: prepare_oauth_config(name, url, cfg))
    monkeypatch.setattr("tools.mcp_dashboard_oauth.get_dashboard_oauth_flow", lambda: None)

    entry = mcp_oauth_manager._ProviderEntry(server_url="https://mcp.example.test/mcp", oauth_config=None)
    with pytest.raises(mcp_oauth.OAuthNonInteractiveError, match="already rejected"):
        mcp_oauth_manager.MCPOAuthManager()._build_provider("cloud", entry)
