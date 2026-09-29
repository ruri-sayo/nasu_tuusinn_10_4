"""Common message envelope (DD-0001).

Responsibilities:
    - Build, serialize and validate the envelope
      ``{topic, ver, seq, ts, src, payload}`` shared by every message on
      WebSocket, DataChannel and local UDP.

Non-responsibilities:
    - Topic registration, direction and rate checks (see ``topics`` / ``filters``).
    - Payload schema validation per topic (handled by the consumer).
"""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

MAX_BYTES = 16 * 1024
"""Maximum encoded size of one message in bytes (16 KiB)."""

MAX_TOPIC_LEN = 64
_TOPIC_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)+$")


class Envelope(TypedDict):
    """Decoded envelope.

    ``ts`` is the sender's UNIX epoch time in milliseconds. ``seq`` increases
    monotonically per (src, topic).
    """

    topic: str
    ver: int
    seq: int
    ts: int
    src: str
    payload: dict[str, Any]


def is_valid_topic(topic: object) -> bool:
    """Return True if ``topic`` matches the topic naming rule (max 64 chars)."""
    return isinstance(topic, str) and len(topic) <= MAX_TOPIC_LEN and bool(_TOPIC_RE.match(topic))


def make(
    topic: str, payload: dict[str, Any], src: str, seq: int, ts: int, ver: int = 1
) -> Envelope:
    """Build an envelope. ``ts`` is epoch milliseconds."""
    return {"topic": topic, "ver": ver, "seq": seq, "ts": ts, "src": src, "payload": payload}


def encode(env: Envelope) -> str:
    """Serialize an envelope to compact JSON."""
    return json.dumps(env, separators=(",", ":"), ensure_ascii=False)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def decode(text: str | bytes) -> Envelope | None:
    """Parse and validate an envelope.

    Returns:
        The envelope, or ``None`` if the input is larger than 16 KiB, is not
        valid JSON, misses a key, has a wrongly typed value or an invalid
        topic. Never raises for malformed input.
    """
    raw = text.encode("utf-8", "replace") if isinstance(text, str) else text
    if len(raw) > MAX_BYTES:
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    topic, ver, seq, ts = obj.get("topic"), obj.get("ver"), obj.get("seq"), obj.get("ts")
    src, payload = obj.get("src"), obj.get("payload")
    if not (isinstance(topic, str) and is_valid_topic(topic)):
        return None
    if not (isinstance(ver, int) and _is_int(ver) and ver >= 1):
        return None
    if not (isinstance(seq, int) and _is_int(seq) and seq >= 0):
        return None
    if not (isinstance(ts, int) and _is_int(ts)):
        return None
    if not (isinstance(src, str) and src):
        return None
    if not isinstance(payload, dict):
        return None
    return make(topic, payload, src, seq, ts, ver)
