"""car_ctrl wiring (DD-0010, AD-0007, AD-0008).

Responsibilities:
    - Keep a WebSocket to the hub, act as the S3 offerer (aiortc) and
      reconnect 2 s after any loss.
    - Feed downstream envelopes to ``SafetyCore``; answer heartbeats at once.
    - Every 50 ms (and at once on a state change) send ``out/effective`` to
      UDP out; send ``sys/state`` at 1 Hz and on change.
    - Forward gated local telemetry (UDP in) to the hub.

Non-responsibilities:
    - Driving actuators (downstream of UDP out).
    - Media (handled by the car_media browser page).

Side Effects:
    Opens a WebSocket and WebRTC connection to the hub, sends UDP to
    ``--udp-out``, binds ``--udp-in`` and writes JSON Lines logs.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import ssl
from pathlib import Path
from typing import Any

import aiohttp
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

from nasura_comm import topics
from nasura_comm.clock import mono_ms, wall_ms
from nasura_comm.datachannel import CHANNELS, ChannelPair, channel_options
from nasura_comm.envelope import Envelope, decode, make
from nasura_comm.filters import SeqFilter
from nasura_comm.local_io import (
    UDP_IN_ADDR,
    UDP_OUT_ADDR,
    UDP_OUT_PERIOD_MS,
    TelemetryGate,
    UdpOut,
    build_effective,
    open_udp_in,
)
from nasura_comm.log import EventLog
from nasura_comm.safety import SafetyCore

log = logging.getLogger(__name__)

RECONNECT_S = 2.0
LOOP_S = 0.01
STATE_PERIOD_MS = 1000
DROPPED_LOG_PERIOD_MS = 10_000


def _addr(text: str) -> tuple[str, int]:
    host, port = text.rsplit(":", 1)
    return host, int(port)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse car_ctrl CLI options."""
    ap = argparse.ArgumentParser(prog="python -m nasura_comm.car")
    ap.add_argument("--hub", default="ws://127.0.0.1:8080/ws", help="hub WebSocket URL")
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (self-signed hub, R-1 fallback)",
    )
    ap.add_argument("--udp-out", type=_addr, default=UDP_OUT_ADDR, metavar="HOST:PORT")
    ap.add_argument("--udp-in", type=_addr, default=UDP_IN_ADDR, metavar="HOST:PORT")
    ap.add_argument("--log-dir", type=Path, default=Path("logs"))
    ap.add_argument(
        "--extra-topic",
        action="append",
        default=[],
        help="test aid: register NAME:DIR:CHANNEL:HZ as an extension topic",
    )
    ap.add_argument(
        "--ack-delay-ms", type=int, default=0, help="test aid: delay heartbeat acks (IT-0006)"
    )
    return ap.parse_args(argv)


class CarCtrl:
    """State of the car_ctrl process.

    State:
        ``safety`` (SafetyCore), the current S3 peer connection and channels,
        per-topic outgoing seq numbers, telemetry gate counters.
    """

    def __init__(self, args: argparse.Namespace, events: EventLog | None = None) -> None:
        """Create car_ctrl from parsed CLI options."""
        self.args = args
        extras = [topics.parse_topic_arg(t) for t in args.extra_topic]
        self.registry = topics.Registry([*topics.EXTENSIONS, *extras])
        self.safety = SafetyCore()
        self.seqf = SeqFilter()
        self.gate = TelemetryGate(self.registry)
        self.channels = ChannelPair(self.registry)
        self.pc: RTCPeerConnection | None = None
        self.ws: Any = None
        self.events = events
        self._seq: dict[str, int] = {}
        self._udp_out: UdpOut | None = None
        self._moving = False

    def _event(self, kind: str, **fields: Any) -> None:
        if self.events:
            self.events.event(kind, **fields)

    def _env(self, topic: str, payload: dict[str, Any]) -> Envelope:
        seq = self._seq.get(topic, -1) + 1
        self._seq[topic] = seq
        return make(topic, payload, "car_ctrl", seq, wall_ms())

    # ---- main ------------------------------------------------------------

    async def run(self) -> None:
        """Run until cancelled."""
        self._udp_out = await UdpOut.open(self.args.udp_out)
        udp_in = await open_udp_in(self._on_udp_in, self.args.udp_in)
        periodic = asyncio.create_task(self._periodic())
        try:
            while True:
                try:
                    await self._session()
                except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as e:
                    log.info("hub connection failed: %s", e)
                self._link_down("hub connection lost")
                await self._close_pc()
                await asyncio.sleep(RECONNECT_S)
        finally:
            periodic.cancel()
            udp_in.close()
            self._udp_out.close()
            await self._close_pc()

    def _link_down(self, reason: str) -> None:
        self.safety.on_link_down(mono_ms())
        self._event("link_down", reason=reason)

    async def _session(self) -> None:
        ssl_ctx: ssl.SSLContext | bool = False if self.args.insecure else True
        async with (
            aiohttp.ClientSession() as http,
            http.ws_connect(
                self.args.hub,
                heartbeat=5.0,
                ssl=ssl_ctx,
                timeout=aiohttp.ClientWSTimeout(ws_close=2),
            ) as ws,
        ):
            self.ws = ws
            log.info("connected to hub %s", self.args.hub)
            self._event("connect", hub=self.args.hub)
            await ws.send_json({"type": "hello", "role": "car_ctrl"})
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if not isinstance(data, dict) or data.get("session") not in (None, "S3"):
                    continue
                kind = data.get("type")
                if kind == "restart":
                    await self._offer(ws)
                elif kind == "signal":
                    sdp = (data.get("data") or {}).get("sdp")
                    if (
                        self.pc is not None
                        and isinstance(sdp, dict)
                        and sdp.get("type") == "answer"
                    ):
                        await self.pc.setRemoteDescription(
                            RTCSessionDescription(sdp=sdp["sdp"], type="answer")
                        )
                elif kind == "peer":
                    self._link_down("peer down")
                    await self._close_pc()
        self.ws = None

    # ---- S3 --------------------------------------------------------------

    async def _close_pc(self) -> None:
        pc, self.pc = self.pc, None
        self.channels = ChannelPair(self.registry)
        if pc is not None:
            await pc.close()

    async def _offer(self, ws: Any) -> None:
        await self._close_pc()
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.pc = pc
        channels = self.channels
        for name in CHANNELS:
            ch = pc.createDataChannel(name, **channel_options(name))
            channels.attach(ch)
            ch.on("message", self._on_message)

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            self._event("s3_state", state=pc.connectionState)
            if pc.connectionState in ("failed", "closed") and self.pc is pc:
                self._link_down(f"pc {pc.connectionState}")
                await ws.close()  # reconnect loop re-establishes the session

        await pc.setLocalDescription(await pc.createOffer())
        local = pc.localDescription
        await ws.send_json(
            {
                "type": "signal",
                "session": "S3",
                "data": {"sdp": {"type": local.type, "sdp": local.sdp}},
            }
        )

    def _on_message(self, data: str | bytes) -> None:
        env = decode(data)
        if env is None:
            return
        topic = env["topic"]
        spec = self.registry.lookup(topic)
        if spec is None or spec.direction != "down" or env["ver"] > spec.ver:
            return
        if spec.channel == "ctrl" and not self.seqf.accept(env["src"], topic, env["seq"]):
            return
        now = mono_ms()
        self.safety.on_envelope(env, now)
        if topic == "sys/heartbeat":
            ack = self._env(
                "sys/heartbeat_ack",
                {
                    "hb": env["payload"].get("hb"),
                    "t_hub": env["payload"].get("t_hub"),
                    "state": self.safety.state,
                },
            )
            if self.args.ack_delay_ms > 0:
                asyncio.get_running_loop().call_later(
                    self.args.ack_delay_ms / 1000, self.channels.send, ack
                )
            else:
                self.channels.send(ack)
        if topic in ("sys/estop", "sys/estop_release"):
            self._event(topic, **env["payload"])
        if topic == "cmd/drive":
            moving = self.safety.effective(now)["drive"] != {"v": 0.0, "w": 0.0}
            if self._moving and not moving:
                self._send_effective(now)  # propagate a stop without waiting for the period
            self._moving = moving
        self._after_update(now)

    # ---- periodic / local I/O -------------------------------------------

    def _state_env(self, now: int) -> Envelope:
        since_wall = wall_ms() - (now - self.safety.since)
        return self._env(
            "sys/state",
            {
                "state": self.safety.state,
                "since": since_wall,
                "reason": self.safety.reason,
                "dropped": dict(self.gate.dropped),
            },
        )

    def _send_effective(self, now: int) -> None:
        eff = self.safety.effective(now)
        seq = self._seq.get("out/effective", -1) + 1
        self._seq["out/effective"] = seq
        if self._udp_out is not None:
            self._udp_out.send(build_effective(self.safety.state, eff, seq, wall_ms()))

    def _after_update(self, now: int) -> None:
        self.safety.update(now)
        if self.safety.pop_state_changed():
            self._event("state", state=self.safety.state, reason=self.safety.reason)
            self._send_effective(now)
            self.channels.send(self._state_env(now))

    async def _periodic(self) -> None:
        next_out = next_state = next_dropped = mono_ms()
        last_dropped: dict[str, int] = {}
        while True:
            now = mono_ms()
            self._after_update(now)
            if now >= next_out:
                self._send_effective(now)
                next_out += UDP_OUT_PERIOD_MS
                if now > next_out:
                    next_out = now + UDP_OUT_PERIOD_MS
            if now >= next_state:
                self.channels.send(self._state_env(now))
                next_state = now + STATE_PERIOD_MS
            if now >= next_dropped:
                diff = {
                    k: v - last_dropped.get(k, 0)
                    for k, v in self.gate.dropped.items()
                    if v != last_dropped.get(k, 0)
                }
                if diff:
                    self._event("dropped", diff=diff)
                last_dropped = dict(self.gate.dropped)
                next_dropped = now + DROPPED_LOG_PERIOD_MS
            await asyncio.sleep(LOOP_S)

    def _on_udp_in(self, data: bytes) -> None:
        res = self.gate.check(data, mono_ms())
        if res is not None:
            channel, env = res
            self.channels.send(env, channel)


async def amain(args: argparse.Namespace, events: EventLog | None = None) -> None:
    """Run car_ctrl."""
    car = CarCtrl(args, events)
    task = asyncio.current_task()
    if task is not None:
        # Exit cleanly on SIGTERM (systemd stop, test teardown) so logs and
        # coverage data are flushed.
        with contextlib.suppress(NotImplementedError):
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    with contextlib.suppress(asyncio.CancelledError):
        await car.run()
