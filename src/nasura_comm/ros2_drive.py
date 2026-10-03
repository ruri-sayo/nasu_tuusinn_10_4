"""ROS 2 drive-adapter domain logic (DD-0017 through DD-0020).

Responsibilities:
    - Validate ``out/effective`` UDP datagrams.
    - Map a safety-judged drive command to ROS Joy axes.
    - Track sequence generations, input timeout and publisher conflicts.

Non-responsibilities:
    - ROS 2 communication and UDP socket ownership (``ros2_drive_node``).
    - PWM calculation or motor actuation (``joy_motor_controller``).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from nasura_comm.envelope import decode

SafetyState = Literal["INIT", "RUN", "STOP", "ESTOP"]
DriveStatus = Literal["waiting", "active", "stopped", "timeout", "conflict"]
_SAFETY_STATES = {"INIT", "RUN", "STOP", "ESTOP"}


@dataclass(frozen=True)
class EffectiveDrive:
    """One validated safety-judged drive command.

    ``v`` and ``w`` are normalized to ``[-1, 1]``. Positive ``w`` is
    counter-clockwise. ``seq`` is the car_ctrl sequence number.
    """

    state: SafetyState
    v: float
    w: float
    seq: int


def _normalized_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        return None
    return number


def decode_effective(data: bytes) -> EffectiveDrive | None:
    """Validate and decode one ``out/effective`` datagram.

    Returns:
        A normalized drive command, or ``None`` for any contract violation.
    """
    env = decode(data)
    if (
        env is None
        or env["topic"] != "out/effective"
        or env["ver"] != 1
        or env["src"] != "car_ctrl"
    ):
        return None
    payload = env["payload"]
    state = payload.get("state")
    drive = payload.get("drive")
    if state not in _SAFETY_STATES or not isinstance(drive, dict):
        return None
    v = _normalized_number(drive.get("v"))
    w = _normalized_number(drive.get("w"))
    if v is None or w is None:
        return None
    return EffectiveDrive(state, v, w, env["seq"])


def to_joy_axes(effective: EffectiveDrive) -> tuple[float, float]:
    """Return ``(axis_x, axis_y)`` for ``joy_motor_controller``.

    Non-RUN safety states always produce neutral axes.
    """
    if effective.state != "RUN":
        return 0.0, 0.0
    return effective.w, effective.v


class DriveInputState:
    """Own input freshness, sequence generation and conflict state.

    A timeout resets the accepted sequence generation so a restarted
    ``car_ctrl`` can begin again at sequence zero. Publisher conflicts latch
    until this object, and therefore the adapter process, is restarted.
    """

    def __init__(self, timeout_ms: int = 200) -> None:
        """Create a neutral state with the given timeout in milliseconds."""
        self.timeout_ms = timeout_ms
        self.latest: EffectiveDrive | None = None
        self.last_valid_ms: int | None = None
        self.last_seq: int | None = None
        self.conflict = False
        self.dropped: Counter[str] = Counter()
        self._reported_status: DriveStatus | None = None

    def _timed_out(self, now_ms: int) -> bool:
        return self.last_valid_ms is None or now_ms - self.last_valid_ms >= self.timeout_ms

    def accept(self, data: bytes, now_ms: int) -> bool:
        """Accept a valid, forward-moving datagram received at ``now_ms``."""
        effective = decode_effective(data)
        if effective is None:
            self.dropped["invalid"] += 1
            return False
        if self._timed_out(now_ms):
            self.last_seq = None
        if self.last_seq is not None and effective.seq <= self.last_seq:
            self.dropped["sequence"] += 1
            return False
        self.latest = effective
        self.last_seq = effective.seq
        self.last_valid_ms = now_ms
        return True

    def latch_conflict(self) -> None:
        """Permanently select neutral output after another publisher is found."""
        self.conflict = True

    def axes(self, now_ms: int) -> tuple[float, float]:
        """Return safe axes for the current state at monotonic ``now_ms``."""
        if self.conflict or self._timed_out(now_ms) or self.latest is None:
            return 0.0, 0.0
        return to_joy_axes(self.latest)

    def status(self, now_ms: int) -> DriveStatus:
        """Return the diagnostic state at monotonic ``now_ms``."""
        if self.conflict:
            return "conflict"
        if self.last_valid_ms is None:
            return "waiting"
        if self._timed_out(now_ms):
            return "timeout"
        if self.latest is None or self.latest.state != "RUN":
            return "stopped"
        return "active"

    def transition(self, now_ms: int) -> DriveStatus | None:
        """Return a new diagnostic state once, or ``None`` if unchanged."""
        current = self.status(now_ms)
        if current == self._reported_status:
            return None
        self._reported_status = current
        return current
