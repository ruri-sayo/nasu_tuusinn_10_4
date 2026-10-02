"""Quest input to high-level command mapping (DD-0004).

Responsibilities:
    - Convert one ``in/quest`` payload into ``cmd/drive`` and ``cmd/stage``
      payloads (dead zone, button mapping).

Non-responsibilities:
    - Timeouts, E-STOP and sending (``control``).
    - E-STOP gesture detection (done by the Quest page).
    - Arm control (the SO-101 leader arm is a separate feature); the
      ``trigger``/``grip``/``pose`` fields of the input are ignored.

Conventions:
    - Stick axes follow the Gamepad API (up is y < 0).
"""

from __future__ import annotations

import math
from typing import Any

DEAD_ZONE = 0.15

Payload = dict[str, Any]


def _num(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    f = float(value)
    return f if math.isfinite(f) else default


def _hand(inp: Payload, side: str) -> Payload:
    h = inp.get(side)
    return h if isinstance(h, dict) else {}


def _axes(hand: Payload) -> tuple[float, float]:
    axes = hand.get("axes")
    if not isinstance(axes, list) or len(axes) < 2:
        return 0.0, 0.0
    return _num(axes[0]), _num(axes[1])


def radial_dead_zone(x: float, y: float, zone: float = DEAD_ZONE) -> tuple[float, float]:
    """Apply a radial dead zone and rescale the outside to magnitude 0..1."""
    mag = math.hypot(x, y)
    if mag < zone:
        return 0.0, 0.0
    scaled = min((mag - zone) / (1.0 - zone), 1.0)
    return x / mag * scaled, y / mag * scaled


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


class Mapper:
    """Stateless mapping rules, kept as a class so the rules can be swapped."""

    def map(self, inp: Payload) -> tuple[Payload, Payload]:
        """Map an ``in/quest`` payload to ``(drive, stage)`` payloads.

        ``drive`` ``v``/``w`` and ``stage`` ``x``/``z`` are normalized to
        [-1, 1]; ``w`` > 0 turns left (counter-clockwise).
        """
        left, right = _hand(inp, "left"), _hand(inp, "right")
        lx, ly = radial_dead_zone(*_axes(left))
        drive = {"v": _clamp(-ly), "w": _clamp(-lx)}
        a, b = bool(right.get("a")), bool(right.get("b"))
        sx = 1.0 if a and not b else (-1.0 if b and not a else 0.0)
        _, ry = radial_dead_zone(*_axes(right))
        stage = {"x": sx, "z": _clamp(-ry)}
        return drive, stage
