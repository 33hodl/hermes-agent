from gateway.response_filters import (
    is_autonomous_silence_response,
    is_intentional_silence_agent_result,
    is_intentional_silence_response,
)


def test_exact_silence_tokens_are_intentional_silence():
    for token in ("[SILENT]", " SILENT ", "NO_REPLY", "no reply"):
        assert is_intentional_silence_response(token)


def test_autonomous_silence_accepts_marker_with_own_line_note():
    """The loose rule for cron/webhook lanes: marker + explanation suppresses."""
    assert is_autonomous_silence_response("[SILENT]")
    assert is_autonomous_silence_response("[SILENT]\n\nNothing new this tick.")
    assert is_autonomous_silence_response("2 deals filtered\n\n[SILENT]")
    assert is_autonomous_silence_response("no_reply\nduplicate inbound, already handled")
    assert is_autonomous_silence_response("[SILENT] No changes detected")


def test_autonomous_silence_accepts_emphasis_wrapped_marker():
    """Emphasis-wrapped markers still suppress; prose mentioning a marker still delivers.

    A model that bolds its sentinel (``**[SILENT]**``) means the same thing as the bare
    token; delivering it verbatim sends a marker-only message to the user's chat.
    """
    assert is_autonomous_silence_response("**[SILENT]**")
    assert is_autonomous_silence_response("**[SILENT]**\n")
    assert is_autonomous_silence_response("*[SILENT]*")
    assert is_autonomous_silence_response("**[SILENT]** No changes detected")
    for prose in ("The reply was [SILENT], intentionally.", "we should send [SILENT] at the end"):
        assert not is_autonomous_silence_response(prose)
    assert not is_autonomous_silence_response("")
    assert not is_autonomous_silence_response("   ")


