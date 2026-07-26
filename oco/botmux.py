# -*- coding: utf-8 -*-
"""Long-lived stdin/stdout bridge used by the native botmux OCO adapter."""

from __future__ import annotations

import base64
import html
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, TextIO

from .capability import OCOCapability


INPUT_PREFIX = "::botmux-oco:"
OSC_PREFIX = "\x1b]777;botmux:"
OSC_END = "\x07"


@dataclass(frozen=True)
class BotmuxMessage:
    content: str


def decode_botmux_line(line: str) -> Optional[BotmuxMessage]:
    """Decode one botmux runner control line."""
    normalized = line.rstrip("\r\n")
    if not normalized or not normalized.startswith(INPUT_PREFIX):
        return None

    encoded = normalized[len(INPUT_PREFIX):]
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return BotmuxMessage(content=content)


def encode_osc_marker(kind: str, payload: Dict[str, Any]) -> str:
    """Encode an OSC marker consumed by botmux without rendering it."""
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = base64.b64encode(serialized.encode("utf-8")).decode("ascii")
    return f"{OSC_PREFIX}{kind}:{encoded}{OSC_END}"


def normalize_botmux_content(content: str) -> str:
    """Extract the user request from botmux's optional metadata envelope."""
    opening = re.search(r"<user_message\b[^>]*>", content, flags=re.IGNORECASE)
    if opening is None:
        return content
    closing = content.lower().rfind("</user_message>")
    if closing < opening.end():
        return content
    user_message = html.unescape(content[opening.end():closing]).strip()
    return user_message or content


class OCOBotmuxRunner:
    """Serve multiple botmux turns inside one persistent OCO process."""

    def __init__(
        self,
        session_id: str,
        timeout: int = 600,
        enable_vector_store: bool = False,
        capability: Optional[OCOCapability] = None,
    ):
        if not session_id.strip():
            raise ValueError("session_id is required")
        self.session_id = session_id
        self.timeout = timeout
        self.enable_vector_store = enable_vector_store
        self.capability = capability or OCOCapability()
        self._current_task: Optional[str] = None
        self._output_lock = threading.Lock()

    def serve(self, input_stream: TextIO, output_stream: TextIO) -> None:
        """Read runner control lines until stdin closes."""
        self._write_line(output_stream, "OCO botmux runner ready.")
        self._emit(
            output_stream,
            "thread",
            {"threadId": self.session_id},
        )
        self._prompt(output_stream)

        for line in input_stream:
            message = decode_botmux_line(line)
            if message is None:
                self._prompt(output_stream)
                continue
            self._run_turn(message.content, output_stream)
            self._prompt(output_stream)

    def _run_turn(self, content: str, output_stream: TextIO) -> None:
        content = normalize_botmux_content(content)
        started_at_ms = int(time.time() * 1000)
        turn_id = f"oco-{time.time_ns()}"

        self._write_line(output_stream)
        self._write_line(output_stream, "[oco] processing...")

        try:
            route_context: Dict[str, Any] = {"thread_id": self.session_id}
            if self._current_task:
                route_context["current_task"] = self._current_task

            route = self.capability.route(
                content,
                sender_id=f"botmux:{self.session_id}",
                context=route_context,
            )
            self._current_task = content
            result = self.capability.run(
                goal=content,
                thread_id=self.session_id,
                context={
                    "entrypoint": "botmux",
                    "botmux_session_id": self.session_id,
                    "route": route,
                },
                timeout=self.timeout,
                enable_vector_store=self.enable_vector_store,
                progress_callback=lambda stage, detail, progress: self._progress(
                    output_stream, stage, detail, progress
                ),
            )
            final_text = str(result.get("response") or result.get("error") or result)
        except Exception as exc:
            final_text = f"OCO task failed: {exc}"

        completed_at_ms = int(time.time() * 1000)
        self._write_line(output_stream)
        self._write_line(output_stream, final_text)
        self._emit(
            output_stream,
            "final",
            {
                "turnId": turn_id,
                "content": final_text,
                "startedAtMs": started_at_ms,
                "completedAtMs": completed_at_ms,
            },
        )

    def _progress(
        self,
        output_stream: TextIO,
        stage: str,
        detail: str,
        progress: float,
    ) -> None:
        percent = max(0, min(100, round(progress * 100)))
        self._write_line(output_stream, f"[oco:{stage}] {detail} ({percent}%)")

    def _emit(self, output_stream: TextIO, kind: str, payload: Dict[str, Any]) -> None:
        with self._output_lock:
            output_stream.write(encode_osc_marker(kind, payload))
            output_stream.flush()

    def _write_line(self, output_stream: TextIO, text: str = "") -> None:
        with self._output_lock:
            output_stream.write(text + "\n")
            output_stream.flush()

    def _prompt(self, output_stream: TextIO) -> None:
        with self._output_lock:
            output_stream.write("OCO> ")
            output_stream.flush()
