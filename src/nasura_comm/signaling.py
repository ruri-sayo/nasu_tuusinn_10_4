"""Signaling router (DD-0008).

Responsibilities:
    - Track one connection handle per role and the sessions S1/S2/S3.
    - Decide which signaling messages go where: ``restart`` to offerers when
      both ends are present, relay of ``signal``, ``peer down`` notices.

Non-responsibilities:
    - Owning sockets: handles are opaque; callers execute returned actions.
    - Authentication (not provided; see R-4).

Sessions:
    S1 car_media -> quest, S2 booth -> car_media, S3 car_ctrl -> hub
    (``hub`` is the always-present internal peer). The first role is the
    offerer.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

HUB = "hub"
ROLES = ("quest", "booth", "car_media", "car_ctrl")
SESSIONS: dict[str, tuple[str, str]] = {
    "S1": ("car_media", "quest"),
    "S2": ("booth", "car_media"),
    "S3": ("car_ctrl", HUB),
}


@dataclass(frozen=True)
class Send:
    """Send ``msg`` to the connection ``handle``."""

    handle: Hashable
    msg: dict[str, Any]


@dataclass(frozen=True)
class Close:
    """Close the connection ``handle`` (replaced by a newer one)."""

    handle: Hashable


@dataclass(frozen=True)
class Internal:
    """Deliver ``msg`` to the hub's internal S3 peer."""

    msg: dict[str, Any]


Action = Send | Close | Internal


class SignalRouter:
    """Pure routing state for the hub WebSocket.

    State:
        ``handles``: role -> current connection handle.
    """

    def __init__(self) -> None:
        """Start with no connected roles."""
        self.handles: dict[str, Hashable] = {}

    def present(self, role: str) -> bool:
        """Return True if ``role`` is connected (``hub`` always is)."""
        return role == HUB or role in self.handles

    def _deliver(self, role: str, msg: dict[str, Any]) -> list[Action]:
        if role == HUB:
            return [Internal(msg)]
        handle = self.handles.get(role)
        return [] if handle is None else [Send(handle, msg)]

    def _restart(self, session: str) -> list[Action]:
        offerer, answerer = SESSIONS[session]
        if self.present(offerer) and self.present(answerer):
            return self._deliver(offerer, {"type": "restart", "session": session})
        return []

    def on_hello(self, role: str, handle: Hashable) -> list[Action]:
        """Register ``handle`` for ``role``; return close/restart actions."""
        if role not in ROLES:
            log.warning("hello with unknown role %r", role)
            return []
        actions: list[Action] = []
        old = self.handles.get(role)
        if old is not None and old != handle:
            actions.append(Close(old))
        self.handles[role] = handle
        for session, ends in SESSIONS.items():
            if role in ends:
                actions += self._restart(session)
        return actions

    def on_signal(self, from_role: str, session: str, data: Any) -> list[Action]:
        """Relay ``data`` of ``session`` from ``from_role`` to the other end."""
        ends = SESSIONS.get(session)
        if ends is None or from_role not in ends:
            log.warning("dropped signal %s from %s", session, from_role)
            return []
        other = ends[1] if from_role == ends[0] else ends[0]
        return self._deliver(other, {"type": "signal", "session": session, "data": data})

    def on_restart_req(self, from_role: str, session: str) -> list[Action]:
        """Ask the offerer of ``session`` to restart if both ends are present."""
        ends = SESSIONS.get(session)
        if ends is None or from_role not in ends:
            log.warning("dropped restart_req %s from %s", session, from_role)
            return []
        return self._restart(session)

    def on_close(self, role: str, handle: Hashable) -> list[Action]:
        """Forget ``handle``; notify peers with ``peer down`` if it was current."""
        if self.handles.get(role) != handle:
            return []
        del self.handles[role]
        actions: list[Action] = []
        for session, ends in SESSIONS.items():
            if role in ends:
                other = ends[1] if role == ends[0] else ends[0]
                msg = {"type": "peer", "session": session, "state": "down"}
                actions += self._deliver(other, msg)
        return actions
