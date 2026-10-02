"""Hub control core (DD-0005).

Responsibilities:
    - Turn Quest input envelopes into periodic ``cmd/*`` envelopes.
    - Emit ``sys/heartbeat`` periodically and compute RTT from acks.
    - Enforce hub-side safety layer L1 (input timeout) and the
      E-STOP latch (release only from ``booth``).

Non-responsibilities:
    - I/O, clocks and channel selection: callers pass ``now`` (monotonic ms)
      and send the returned envelopes.

Timing:
    - ``now`` is monotonic milliseconds. ``t_hub`` in heartbeats uses the same
      clock so RTT stays within the hub. Envelope ``ts`` is epoch ms and is
      given separately via ``wall_ms`` (defaults to ``now``).
"""

from __future__ import annotations

import logging
from typing import Any

from nasura_comm.envelope import Envelope, make
from nasura_comm.mapping import Mapper

log = logging.getLogger(__name__)

RTT_EWMA_ALPHA = 0.2
CMD_TOPICS = ("cmd/drive", "cmd/stage")


def stop_commands() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the stop values for ``(drive, stage)``."""
    return {"v": 0.0, "w": 0.0}, {"x": 0.0, "z": 0.0}


class ControlCore:
    """Pure hub-side control state.

    State:
        Latest Quest input and its receive time, E-STOP latch, heartbeat
        counter, RTT (latest and EWMA), latest car state, per-topic seq.
    """

    def __init__(
        self,
        mapper: Mapper,
        input_timeout_ms: int = 300,
        hb_period_ms: int = 100,
        cmd_period_ms: int = 33,
    ) -> None:
        """Create the core with the given timeouts and periods (ms)."""
        self.mapper = mapper
        self.input_timeout_ms = input_timeout_ms
        self.hb_period_ms = hb_period_ms
        self.cmd_period_ms = cmd_period_ms
        self.latched = False
        self.rtt_ms: int | None = None
        self.rtt_ewma_ms: float | None = None
        self.car_state: str | None = None
        self._input: dict[str, Any] | None = None
        self._input_at: int | None = None
        self._hb = 0
        self._next_hb: int | None = None
        self._next_cmd: int | None = None
        self._seq: dict[str, int] = {}
        self._stopped: bool | None = None

    def _env(self, topic: str, payload: dict[str, Any], wall_ms: int) -> Envelope:
        seq = self._seq.get(topic, -1) + 1
        self._seq[topic] = seq
        return make(topic, payload, "hub", seq, wall_ms)

    def last_input_age_ms(self, now: int) -> int | None:
        """Age of the latest Quest input in ms, or ``None`` if none yet."""
        return None if self._input_at is None else now - self._input_at

    def on_input(self, env: Envelope, now: int, wall_ms: int | None = None) -> list[Envelope]:
        """Handle an ``in/*`` envelope from a browser; return envelopes to send."""
        wall = now if wall_ms is None else wall_ms
        topic, src = env["topic"], env["src"]
        if topic == "in/quest":
            self._input = env["payload"]
            self._input_at = now
            return []
        if topic == "in/estop":
            self.latched = True
            source = src if src in ("quest", "booth") else "hub"
            reason = env["payload"].get("reason", "")
            log.warning("E-STOP from %s: %s", source, reason)
            return [self._env("sys/estop", {"source": source, "reason": str(reason)}, wall)]
        if topic == "in/estop_release":
            if src != "booth":
                log.warning("ignored estop_release from %s", src)
                return []
            self.latched = False
            log.warning("E-STOP released from booth")
            return [self._env("sys/estop_release", {"source": "booth"}, wall)]
        log.info("ignored input topic %s from %s", topic, src)
        return []

    def on_link_up(self, now: int, wall_ms: int | None = None) -> list[Envelope]:
        """Re-send the E-STOP if latched when the S3 link (re)opens."""
        if not self.latched:
            return []
        wall = now if wall_ms is None else wall_ms
        return [self._env("sys/estop", {"source": "hub", "reason": "latched on reconnect"}, wall)]

    def on_car(self, env: Envelope, now: int) -> None:
        """Handle an envelope from car_ctrl (heartbeat ack, state)."""
        topic, payload = env["topic"], env["payload"]
        if topic == "sys/heartbeat_ack":
            t_hub = payload.get("t_hub")
            if isinstance(t_hub, int) and not isinstance(t_hub, bool):
                self.rtt_ms = now - t_hub
                self.rtt_ewma_ms = (
                    float(self.rtt_ms)
                    if self.rtt_ewma_ms is None
                    else RTT_EWMA_ALPHA * self.rtt_ms + (1 - RTT_EWMA_ALPHA) * self.rtt_ewma_ms
                )
            state = payload.get("state")
            if isinstance(state, str):
                self.car_state = state
        elif topic == "sys/state":
            state = payload.get("state")
            if isinstance(state, str):
                self.car_state = state

    def _should_stop(self, now: int) -> bool:
        age = self.last_input_age_ms(now)
        return self.latched or self._input is None or age is None or age > self.input_timeout_ms

    def _commands(self, now: int) -> tuple[dict[str, Any], dict[str, Any]]:
        if self._should_stop(now):
            return stop_commands()
        assert self._input is not None
        return self.mapper.map(self._input)

    def tick(self, now: int, wall_ms: int | None = None) -> list[Envelope]:
        """Return the envelopes due at ``now`` (heartbeat and/or commands)."""
        wall = now if wall_ms is None else wall_ms
        out: list[Envelope] = []
        if self._next_hb is None or now >= self._next_hb:
            self._hb += 1
            out.append(self._env("sys/heartbeat", {"hb": self._hb, "t_hub": now}, wall))
            self._next_hb = now + self.hb_period_ms
        # A change to stop values (input timeout) is sent at once, not on the next period.
        stop_now = self._should_stop(now) and self._stopped is False
        if self._next_cmd is None or now >= self._next_cmd or stop_now:
            self._stopped = self._should_stop(now)
            for topic, payload in zip(CMD_TOPICS, self._commands(now), strict=True):
                out.append(self._env(topic, payload, wall))
            self._next_cmd = now + self.cmd_period_ms
        return out
