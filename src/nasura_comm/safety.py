"""Car-side safety state machine (DD-0006).

Responsibilities:
    - Track INIT / RUN / STOP / ESTOP from heartbeats, link events and E-STOP.
    - Hold the latest commands and produce the effective (safety-checked)
      command: layers L2 (heartbeat 500 ms / link down), L3 (command 300 ms)
      and L4 (E-STOP latch).

Non-responsibilities:
    - I/O and clocks: callers pass ``now`` (monotonic ms).
    - Sending ``sys/state``; this module only raises a change flag.
"""

from __future__ import annotations

import logging
from typing import Any

from nasura_comm.envelope import Envelope

log = logging.getLogger(__name__)

States = ("INIT", "RUN", "STOP", "ESTOP")


def stop_effective(clutch_id: int = 0) -> dict[str, Any]:
    """Return the stop value of the effective command."""
    return {
        "drive": {"v": 0.0, "w": 0.0},
        "arm": {
            "enable": False,
            "clutch_id": clutch_id,
            "p": [0, 0, 0],
            "q": [0, 0, 0, 1],
            "grip": 0.0,
        },
        "stage": {"x": 0.0, "z": 0.0},
    }


class SafetyCore:
    """Pure safety state machine.

    State:
        ``state``, time of entering it (``since``) and ``reason``; last
        heartbeat time; latest ``cmd/*`` payloads with receive times (only
        kept in RUN, discarded on entering STOP/ESTOP); a state-change flag.
    """

    def __init__(self, hb_timeout_ms: int = 500, cmd_timeout_ms: int = 300) -> None:
        """Start in INIT with the given timeouts (ms)."""
        self.hb_timeout_ms = hb_timeout_ms
        self.cmd_timeout_ms = cmd_timeout_ms
        self.state = "INIT"
        self.since = 0
        self.reason = "start"
        self._changed = True
        self._last_hb: int | None = None
        self._cmds: dict[str, tuple[dict[str, Any], int]] = {}
        self._clutch_id = 0

    def _enter(self, state: str, now: int, reason: str) -> None:
        if state == self.state:
            return
        log.info("state %s -> %s (%s)", self.state, state, reason)
        self.state, self.since, self.reason = state, now, reason
        self._changed = True
        if state in ("STOP", "ESTOP"):
            self._cmds.clear()

    def pop_state_changed(self) -> bool:
        """Return True once after each state change (to send ``sys/state``)."""
        changed, self._changed = self._changed, False
        return changed

    def on_link_down(self, now: int | None = None) -> None:
        """Handle loss of the S3 link: RUN -> STOP."""
        if self.state == "RUN":
            self._enter("STOP", self.since if now is None else now, "link down")

    def update(self, now: int) -> None:
        """Apply the heartbeat timeout at ``now``."""
        if (
            self.state == "RUN"
            and self._last_hb is not None
            and now - self._last_hb > self.hb_timeout_ms
        ):
            self._enter("STOP", now, "heartbeat timeout")

    def on_envelope(self, env: Envelope, now: int) -> None:
        """Handle a downstream envelope from the hub."""
        topic = env["topic"]
        if topic == "sys/estop":
            self._enter("ESTOP", now, f"estop from {env['payload'].get('source', '?')}")
            return
        if self.state == "ESTOP":
            if topic == "sys/estop_release":
                self._enter("STOP", now, "estop released")
            return
        self.update(now)
        if topic == "sys/heartbeat":
            self._last_hb = now
            if self.state in ("INIT", "STOP"):
                self._enter("RUN", now, "heartbeat")
        elif topic.startswith("cmd/") and self.state == "RUN":
            self._cmds[topic] = (env["payload"], now)
            if topic == "cmd/arm":
                cid = env["payload"].get("clutch_id")
                if isinstance(cid, int):
                    self._clutch_id = cid

    def _fresh(self, topic: str, now: int) -> dict[str, Any] | None:
        item = self._cmds.get(topic)
        if item is None or now - item[1] > self.cmd_timeout_ms:
            return None
        return item[0]

    def effective(self, now: int) -> dict[str, Any]:
        """Return the effective command at ``now`` (updates timeouts first)."""
        self.update(now)
        eff = stop_effective(self._clutch_id)
        if self.state != "RUN":
            return eff
        drive = self._fresh("cmd/drive", now)
        if drive is not None and drive.get("deadman") is True:
            eff["drive"] = {"v": _f(drive.get("v")), "w": _f(drive.get("w"))}
        arm = self._fresh("cmd/arm", now)
        if arm is not None and arm.get("enable") is True:
            eff["arm"] = {
                "enable": True,
                "clutch_id": self._clutch_id,
                "p": arm.get("p", [0, 0, 0]),
                "q": arm.get("q", [0, 0, 0, 1]),
                "grip": _f(arm.get("grip")),
            }
        elif arm is not None:
            eff["arm"]["grip"] = _f(arm.get("grip"))
        stage = self._fresh("cmd/stage", now)
        if stage is not None:
            eff["stage"] = {"x": _f(stage.get("x")), "z": _f(stage.get("z"))}
        return eff


def _f(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(-1.0, min(1.0, float(value)))
