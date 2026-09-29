"""Quest input to high-level command mapping (DD-0004).

Responsibilities:
    - Convert one ``in/quest`` payload into ``cmd/drive``, ``cmd/arm`` and
      ``cmd/stage`` payloads (deadman, dead zone, arm clutch).

Non-responsibilities:
    - Timeouts, E-STOP and sending (``control``).
    - E-STOP gesture detection (done by the Quest page).

Conventions:
    - Stick axes follow the Gamepad API (up is y < 0).
    - Poses are grip poses in WebXR ``local-floor`` (right-handed, +y up,
      -z forward); ``p`` in metres, ``q`` as xyzw quaternion.
"""

from __future__ import annotations

import math
from typing import Any

DEADMAN_THRESHOLD = 0.5
GRIP_THRESHOLD = 0.5
DEAD_ZONE = 0.15

Payload = dict[str, Any]
Quat = tuple[float, float, float, float]


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


def _pose(hand: Payload) -> tuple[list[float], Quat] | None:
    pose = hand.get("pose")
    if not isinstance(pose, dict):
        return None
    p, q = pose.get("p"), pose.get("q")
    if not (isinstance(p, list) and len(p) == 3 and isinstance(q, list) and len(q) == 4):
        return None
    return [_num(v) for v in p], (_num(q[0]), _num(q[1]), _num(q[2]), _num(q[3], 1.0))


def _q_normalize(q: Quat) -> Quat:
    n = math.sqrt(sum(c * c for c in q))
    if n == 0:
        return (0.0, 0.0, 0.0, 1.0)
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def _q_mul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _q_conj(q: Quat) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


class Mapper:
    """Stateful mapping rules.

    State:
        ``clutch_id`` counts arm clutch engagements; the reference pose is the
        right grip pose at the last rising edge of the arm enable.
    """

    def __init__(self) -> None:
        """Start with no clutch engaged and ``clutch_id`` 0."""
        self.clutch_id = 0
        self._ref: tuple[list[float], Quat] | None = None

    def map(self, inp: Payload) -> tuple[Payload, Payload, Payload]:
        """Map an ``in/quest`` payload to ``(drive, arm, stage)`` payloads."""
        left, right = _hand(inp, "left"), _hand(inp, "right")
        deadman = _num(left.get("grip")) > DEADMAN_THRESHOLD

        lx, ly = radial_dead_zone(*_axes(left))
        if deadman:
            drive = {"v": _clamp(-ly), "w": _clamp(-lx), "deadman": True}
        else:
            drive = {"v": 0.0, "w": 0.0, "deadman": False}

        pose = _pose(right)
        enable = _num(right.get("grip")) > GRIP_THRESHOLD and pose is not None
        if enable and pose is not None:
            if self._ref is None:
                self._ref = (pose[0], _q_normalize(pose[1]))
                self.clutch_id += 1
            ref_p, ref_q = self._ref
            p = [pose[0][i] - ref_p[i] for i in range(3)]
            q = _q_normalize(_q_mul(_q_conj(ref_q), _q_normalize(pose[1])))
            arm = {"enable": True, "clutch_id": self.clutch_id, "p": p, "q": list(q)}
        else:
            self._ref = None
            arm = {"enable": False, "clutch_id": self.clutch_id, "p": [0, 0, 0], "q": [0, 0, 0, 1]}
        arm["grip"] = max(0.0, min(1.0, _num(right.get("trigger"))))

        if deadman:
            a, b = bool(right.get("a")), bool(right.get("b"))
            sx = 1.0 if a and not b else (-1.0 if b and not a else 0.0)
            _, ry = radial_dead_zone(*_axes(right))
            stage = {"x": sx, "z": _clamp(-ry)}
        else:
            stage = {"x": 0.0, "z": 0.0}
        return drive, arm, stage
