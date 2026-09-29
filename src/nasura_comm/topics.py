"""Topic registry (DD-0002).

Responsibilities:
    - Hold the single source of truth for topic specs: fixed (safety/core)
      topics and extension topics.
    - Validate that extensions do not shadow fixed or reserved topics.
    - Export the registry as JSON for browsers (served as ``/topics.json``).

Non-responsibilities:
    - Handling of fixed topics (hard-coded in ``control`` / ``safety``).
    - Rate limiting and sequence filtering (``filters``).

Payload semantics of fixed topics (see 30-detailed-design.md DD-0002):
    - ``v``/``w``/``x``/``z`` are normalized to [-1, 1]; ``w`` > 0 is
      counter-clockwise (REP-103).
    - ``cmd/arm`` ``p`` (m) / ``q`` (quaternion xyzw) are relative to the pose
      at clutch start, in the WebXR ``local-floor`` frame (right-handed, +y up,
      -z forward). ``grip`` is in [0, 1].
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

RESERVED_PREFIXES = ("sys/", "cmd/", "in/", "out/")


@dataclass(frozen=True)
class TopicSpec:
    """Declaration of one topic.

    ``direction`` is ``down`` (hub -> car) or ``up`` (car -> hub).
    ``max_rate_hz`` of ``None`` means no limit. ``fixed`` topics are handled
    in code and cannot be overridden by extensions.
    """

    name: str
    direction: Literal["down", "up"]
    channel: Literal["ctrl", "rel"]
    max_rate_hz: float | None
    fixed: bool
    ver: int = 1


FIXED: tuple[TopicSpec, ...] = (
    TopicSpec("sys/heartbeat", "down", "ctrl", 10, fixed=True),
    TopicSpec("sys/heartbeat_ack", "up", "ctrl", 10, fixed=True),
    TopicSpec("sys/estop", "down", "rel", None, fixed=True),
    TopicSpec("sys/estop_release", "down", "rel", None, fixed=True),
    TopicSpec("sys/state", "up", "rel", 5, fixed=True),
    TopicSpec("cmd/drive", "down", "ctrl", 30, fixed=True),
    TopicSpec("cmd/arm", "down", "ctrl", 30, fixed=True),
    TopicSpec("cmd/stage", "down", "ctrl", 30, fixed=True),
)

EXTENSIONS: list[TopicSpec] = [
    # Add extension topics here, e.g.:
    # TopicSpec("tlm/battery_voltage", "up", "ctrl", 2.0, fixed=False)
]


def validate_extensions(extensions: Iterable[TopicSpec]) -> None:
    """Check extension specs.

    Raises:
        ValueError: If an extension has the name of a fixed topic, uses a
            reserved prefix (``sys/``, ``cmd/``, ``in/``, ``out/``), is marked
            ``fixed`` or is declared twice.
    """
    fixed_names = {t.name for t in FIXED}
    seen: set[str] = set()
    for ext in extensions:
        if ext.name in fixed_names:
            raise ValueError(f"extension shadows fixed topic: {ext.name}")
        if ext.name.startswith(RESERVED_PREFIXES):
            raise ValueError(f"extension uses reserved prefix: {ext.name}")
        if ext.fixed:
            raise ValueError(f"extension must not be fixed: {ext.name}")
        if ext.name in seen:
            raise ValueError(f"duplicate extension: {ext.name}")
        seen.add(ext.name)


class Registry:
    """Lookup table of fixed topics plus a validated set of extensions.

    Immutable after construction.
    """

    def __init__(self, extensions: Iterable[TopicSpec] = ()) -> None:
        """Build the registry. Raises ``ValueError`` on invalid extensions."""
        ext = list(extensions)
        validate_extensions(ext)
        self._specs = {t.name: t for t in (*FIXED, *ext)}

    def lookup(self, name: str) -> TopicSpec | None:
        """Return the spec of ``name``, or ``None`` if unregistered."""
        return self._specs.get(name)

    def to_json(self) -> dict[str, Any]:
        """Return the registry as a JSON-serializable dict for browsers."""
        return {"topics": [asdict(t) for t in self._specs.values()]}


def parse_topic_arg(text: str) -> TopicSpec:
    """Parse ``NAME:DIRECTION:CHANNEL:HZ`` (HZ may be ``-``) into an extension.

    Used by the ``--extra-topic`` test option of hub and car_ctrl.
    """
    name, direction, channel, hz = text.split(":")
    if direction not in ("down", "up") or channel not in ("ctrl", "rel"):
        raise ValueError(f"invalid topic spec: {text}")
    rate = None if hz == "-" else float(hz)
    return TopicSpec(name, direction, channel, rate, fixed=False)  # type: ignore[arg-type]


DEFAULT = Registry(EXTENSIONS)


def lookup(name: str) -> TopicSpec | None:
    """Look up ``name`` in the default registry."""
    return DEFAULT.lookup(name)


def to_json() -> dict[str, Any]:
    """Export the default registry for browsers."""
    return DEFAULT.to_json()
