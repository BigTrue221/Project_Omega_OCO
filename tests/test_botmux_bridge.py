# -*- coding: utf-8 -*-
"""Contract tests for the OCO side of the botmux runner protocol."""

import base64
import io
import json
import re

try:
    from Project_Omega_OCO.oco.botmux import (
        INPUT_PREFIX,
        OCOBotmuxRunner,
        decode_botmux_line,
        normalize_botmux_content,
    )
except ImportError:
    from oco.botmux import (
        INPUT_PREFIX,
        OCOBotmuxRunner,
        decode_botmux_line,
        normalize_botmux_content,
    )


OSC_RE = re.compile(r"\x1b]777;botmux:([^:]+):([A-Za-z0-9+/=]+)\x07")


def _control_line(content: str) -> str:
    payload = json.dumps({"type": "message", "content": content}).encode("utf-8")
    return INPUT_PREFIX + base64.b64encode(payload).decode("ascii") + "\n"


def _markers(output: str):
    return [
        (kind, json.loads(base64.b64decode(encoded).decode("utf-8")))
        for kind, encoded in OSC_RE.findall(output)
    ]


class FakeCapability:
    def __init__(self):
        self.route_calls = []
        self.run_calls = []

    def route(self, message, sender_id, context):
        self.route_calls.append((message, sender_id, context))
        return {
            "path": "oco",
            "thread_id": "router-generated-id",
            "complexity": "complex",
            "reasoning": "test",
            "metadata": {},
        }

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        kwargs["progress_callback"]("planning", "building plan", 0.5)
        return {"success": True, "response": "bridge result"}


def test_decode_botmux_line_preserves_multiline_unicode_content():
    message = decode_botmux_line(_control_line("first line\nsecond line"))

    assert message is not None
    assert message.content == "first line\nsecond line"


def test_normalize_botmux_content_extracts_user_request():
    content = (
        "<role>architect</role>\n\n"
        "<user_message>\nAnalyze A &amp; B\n</user_message>\n\n"
        '<sender type="human" name="Alice" />'
    )

    assert normalize_botmux_content(content) == "Analyze A & B"
    assert normalize_botmux_content("plain request") == "plain request"


def test_runner_maps_botmux_session_to_oco_thread_and_emits_final_marker():
    capability = FakeCapability()
    output = io.StringIO()
    runner = OCOBotmuxRunner(
        session_id="botmux-session-123",
        timeout=42,
        capability=capability,
    )

    runner.serve(io.StringIO(_control_line("analyze architecture")), output)

    assert capability.route_calls[0][1] == "botmux:botmux-session-123"
    run_call = capability.run_calls[0]
    assert run_call["thread_id"] == "botmux-session-123"
    assert run_call["timeout"] == 42
    assert run_call["context"]["entrypoint"] == "botmux"
    assert run_call["context"]["botmux_session_id"] == "botmux-session-123"

    markers = _markers(output.getvalue())
    assert markers[0] == ("thread", {"threadId": "botmux-session-123"})
    assert markers[-1][0] == "final"
    assert markers[-1][1]["content"] == "bridge result"
    assert "[oco:planning] building plan (50%)" in output.getvalue()


def test_runner_ignores_non_protocol_input():
    capability = FakeCapability()
    output = io.StringIO()
    runner = OCOBotmuxRunner(session_id="session", capability=capability)

    runner.serve(io.StringIO("plain text\n::botmux-oco:not-base64\n"), output)

    assert capability.route_calls == []
    assert capability.run_calls == []
    assert [kind for kind, _ in _markers(output.getvalue())] == ["thread"]
