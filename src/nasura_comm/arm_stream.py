"""SO-101 leader-to-follower streaming over the network (provisional, F-003).

Responsibilities:
    - Read the hardware identity (side/role -> USB serial) from the tracked
      udev rule of the NASURA2026_LeRobot_info checkout.
    - Encode and validate one UDP frame per leader reading.
    - Decide which frames a follower may apply (session, order, freshness).

Non-responsibilities:
    - Serial access, servo control and calibration (LeRobot, scripts/).
    - Networking and process lifecycle (scripts/).

Conventions:
    - One process and one UDP port per side, so a frame for one side can
      never reach the other side's follower; the frame also carries its side
      and is rejected on mismatch.
    - Joint values are LeRobot ``<joint>.pos`` values (degrees, gripper 0..100).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HARDWARE_COMMIT = "8ec5487568089dcf3d5ebf2140b46acd12a02bc2"
"""Pinned NASURA2026_LeRobot_info commit (F-003 External Constraints)."""

UDEV_RULE = Path("so101/udev/99-nasura-so101.rules")
CALIBRATION_ROOT = Path("so101/calibration")

SIDES = ("left", "right")
JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
PORTS = {"left": 47110, "right": 47111}
"""Default UDP port per side."""

MAX_RELATIVE_TARGET_LIMIT = 5.0
"""Upper bound of ``max_relative_target`` in degrees (DD-0025)."""

FRAME_VERSION = 1

_RULE_RE = re.compile(r'ENV\{ID_SERIAL_SHORT\}=="([^"]+)".*SYMLINK\+="([^"]+)"')


def device_id(side: str, role: str) -> str:
    """Return the LeRobot id, e.g. ``left_leader`` (also the udev link name)."""
    if side not in SIDES or role not in ("leader", "follower"):
        raise ValueError(f"bad side/role: {side}/{role}")
    return f"{side}_{role}"


def calibration_file(hardware_dir: Path, side: str, role: str) -> Path:
    """Return the tracked calibration JSON for ``side``/``role``."""
    sub = "teleoperators/so_leader" if role == "leader" else "robots/so_follower"
    return hardware_dir / CALIBRATION_ROOT / sub / f"{device_id(side, role)}.json"


def parse_udev_serials(text: str) -> dict[str, str]:
    """Map link name (e.g. ``left_leader``) to USB serial from the udev rule text."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _RULE_RE.search(line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def check_hardware_dir(
    hardware_dir: Path, head_commit: str | None, side: str, role: str
) -> list[str]:
    """Return problems with the hardware checkout for one device (empty if OK).

    ``head_commit`` is the checkout's HEAD (``None`` if it could not be read).
    """
    errors: list[str] = []
    if head_commit != HARDWARE_COMMIT:
        errors.append(f"hardware checkout is at {head_commit}, expected {HARDWARE_COMMIT}")
    rule = hardware_dir / UDEV_RULE
    if not rule.is_file():
        errors.append(f"udev rule missing: {rule}")
    elif device_id(side, role) not in parse_udev_serials(rule.read_text(encoding="utf-8")):
        errors.append(f"{device_id(side, role)} not in {rule}")
    calib = calibration_file(hardware_dir, side, role)
    if not calib.is_file():
        errors.append(f"calibration missing: {calib}")
    return errors


def check_max_relative_target(value: object) -> str | None:
    """Return an error message unless ``0 < value <= 5`` (DD-0025)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return f"max_relative_target must be a number, got {value!r}"
    if not 0 < value <= MAX_RELATIVE_TARGET_LIMIT:
        return f"max_relative_target must be in (0, {MAX_RELATIVE_TARGET_LIMIT}], got {value}"
    return None


def encode_frame(side: str, session: str, seq: int, ts_ms: int, action: dict[str, float]) -> bytes:
    """Encode one leader reading (``<joint>.pos`` keys) as a UDP payload."""
    pos = {j: float(action[f"{j}.pos"]) for j in JOINTS}
    msg = {"v": FRAME_VERSION, "side": side, "sid": session, "seq": seq, "ts": ts_ms, "pos": pos}
    return json.dumps(msg, separators=(",", ":")).encode()


@dataclass(frozen=True)
class Frame:
    """A validated frame."""

    side: str
    session: str
    seq: int
    ts_ms: int
    pos: dict[str, float]

    def action(self) -> dict[str, float]:
        """Return the frame as a LeRobot action (``<joint>.pos`` keys)."""
        return {f"{j}.pos": v for j, v in self.pos.items()}


def decode_frame(data: bytes) -> Frame | None:
    """Parse and validate a UDP payload; ``None`` if anything is wrong."""
    try:
        msg: Any = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("v") != FRAME_VERSION:
        return None
    side, sid, seq, ts, pos = (msg.get(k) for k in ("side", "sid", "seq", "ts", "pos"))
    if side not in SIDES or not isinstance(sid, str) or not sid:
        return None
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        return None
    if isinstance(ts, bool) or not isinstance(ts, int):
        return None
    if not isinstance(pos, dict) or set(pos) != set(JOINTS):
        return None
    clean: dict[str, float] = {}
    for j in JOINTS:
        v = pos[j]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        clean[j] = float(v)
    return Frame(side, sid, seq, ts, clean)


class FrameGate:
    """Accept frames for one side in order and track freshness.

    A frame is accepted if it is for ``side`` and either starts a new sender
    session or has a larger ``seq`` than the last accepted frame of the
    current session. ``fresh(now)`` is False when nothing was accepted within
    ``timeout_ms``; the follower then holds its position (sends no goal).
    """

    def __init__(self, side: str, timeout_ms: int) -> None:
        """Start with no accepted frame."""
        if side not in SIDES:
            raise ValueError(f"bad side: {side}")
        self.side = side
        self.timeout_ms = timeout_ms
        self.latest: Frame | None = None
        self._accepted_at: int | None = None

    def offer(self, frame: Frame, now_ms: int) -> bool:
        """Offer a decoded frame received at ``now_ms``; return True if accepted."""
        if frame.side != self.side:
            return False
        last = self.latest
        if last is not None and frame.session == last.session and frame.seq <= last.seq:
            return False
        self.latest = frame
        self._accepted_at = now_ms
        return True

    def fresh(self, now_ms: int) -> bool:
        """Return True if a frame was accepted within ``timeout_ms`` of ``now_ms``."""
        return self._accepted_at is not None and now_ms - self._accepted_at <= self.timeout_ms
