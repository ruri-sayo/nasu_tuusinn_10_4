"""Hub server wiring (DD-0009).

Responsibilities:
    - Serve the web pages, ``/config.json``, ``/topics.json`` and ``/status``.
    - Terminate the ``/ws`` WebSocket for every role and execute
      ``SignalRouter`` actions.
    - Act as the S3 answerer (aiortc) and run ``ControlCore`` on a timer.
    - Relay ``sys/state`` and extension topics from car_ctrl to quest/booth.

Non-responsibilities:
    - Media relay (browsers connect S1/S2 peer to peer; no SFU).
    - Authentication (R-4).

Side Effects:
    Listens on TCP (HTTP/WebSocket), opens WebRTC connections (UDP), writes
    JSON Lines logs, and with ``--tls-self-signed`` runs ``openssl`` to create
    a certificate under ``.certs/``.

Async:
    Everything runs on one asyncio loop; no threads.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

from nasura_comm import topics
from nasura_comm.clock import mono_ms, wall_ms
from nasura_comm.config import (
    ROLES,
    HubConfig,
    StatusSnapshot,
    build_config_json,
    build_status,
)
from nasura_comm.control import ControlCore
from nasura_comm.datachannel import ChannelPair
from nasura_comm.envelope import Envelope, decode
from nasura_comm.filters import SeqFilter
from nasura_comm.log import EventLog
from nasura_comm.mapping import Mapper
from nasura_comm.signaling import Close, Internal, Send, SignalRouter

log = logging.getLogger(__name__)

TICK_S = 0.005
REPLACED_CLOSE_CODE = 4001
"""WebSocket close code for a connection replaced by a newer one of the same role."""
STATS_STALE_MS = 5000
INPUT_TOPICS = {
    "quest": {"in/quest", "in/estop", "in/estop_release"},
    "booth": {"in/estop", "in/estop_release"},
}


class Hub:
    """State of the hub process.

    Lifecycle:
        ``start`` launches the control timer; ``stop`` closes the S3 peer and
        the timer. WebSocket handles are the aiohttp ``WebSocketResponse``
        objects.
    """

    def __init__(self, cfg: HubConfig, events: EventLog | None = None) -> None:
        """Create the hub from ``cfg``."""
        self.cfg = cfg
        extras = [topics.parse_topic_arg(t) for t in cfg.extra_topics]
        self.registry = topics.Registry([*topics.EXTENSIONS, *extras])
        self.router = SignalRouter()
        self.core = ControlCore(Mapper())
        self.seq = SeqFilter()
        self.channels = ChannelPair(self.registry)
        self.pc: RTCPeerConnection | None = None
        self.stats: dict[str, dict[str, Any]] = {}
        self.dropped: Counter[str] = Counter()
        self.car_dropped: dict[str, int] = {}
        self.telemetry: dict[str, Any] = {}
        self.events = events
        self._task: asyncio.Task[None] | None = None
        self._last_log = 0

    # ---- lifecycle -------------------------------------------------------

    async def start(self, _app: web.Application | None = None) -> None:
        """Start the control timer."""
        self._task = asyncio.create_task(self._control_loop())

    async def stop(self, _app: web.Application | None = None) -> None:
        """Stop the timer and close the S3 peer."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._close_pc()

    def _event(self, kind: str, **fields: Any) -> None:
        if self.events:
            self.events.event(kind, **fields)

    # ---- control ---------------------------------------------------------

    async def _control_loop(self) -> None:
        while True:
            now = mono_ms()
            for env in self.core.tick(now, wall_ms()):
                self.channels.send(env)
            if now - self._last_log >= 1000:
                self._last_log = now
                self._event(
                    "control",
                    rtt_ms=self.core.rtt_ms,
                    rtt_ewma_ms=self.core.rtt_ewma_ms,
                    car_state=self.core.car_state,
                    latched=self.core.latched,
                )
            await asyncio.sleep(TICK_S)

    def _handle_input(self, role: str, env_obj: Any) -> None:
        env = decode(json.dumps(env_obj)) if isinstance(env_obj, dict) else None
        if env is None:
            self.dropped["invalid"] += 1
            return
        if env["topic"] not in INPUT_TOPICS.get(role, set()):
            self.dropped[env["topic"]] += 1
            return
        env["src"] = role  # never trust the client-declared source
        for out in self.core.on_input(env, mono_ms(), wall_ms()):
            self._event(out["topic"], **out["payload"])
            self.channels.send(out)

    def _on_car_message(self, data: str | bytes) -> None:
        env = decode(data)
        if env is None:
            self.dropped["invalid"] += 1
            return
        topic = env["topic"]
        spec = self.registry.lookup(topic)
        if spec is None or spec.direction != "up" or env["ver"] > spec.ver:
            self.dropped[topic] += 1
            return
        if spec.channel == "ctrl" and not self.seq.accept(env["src"], topic, env["seq"]):
            return
        if topic in ("sys/heartbeat_ack", "sys/state"):
            prev = self.core.car_state
            self.core.on_car(env, mono_ms())
            if topic == "sys/state":
                dropped = env["payload"].get("dropped")
                if isinstance(dropped, dict):
                    self.car_dropped = {
                        str(k): int(v) for k, v in dropped.items() if isinstance(v, int)
                    }
                if self.core.car_state != prev:
                    self._event("car_state", **env["payload"])
                self._broadcast(env)
            return
        self.telemetry[topic] = env["payload"]
        self._broadcast(env)

    def _broadcast(self, env: Envelope) -> None:
        msg = {"type": "env", "env": env}
        for role in ("quest", "booth"):
            ws = self.router.handles.get(role)
            if isinstance(ws, web.WebSocketResponse) and not ws.closed:
                asyncio.ensure_future(_send_json(ws, msg))

    # ---- S3 peer ---------------------------------------------------------

    async def _close_pc(self) -> None:
        pc, self.pc = self.pc, None
        self.channels = ChannelPair(self.registry)
        if pc is not None:
            await pc.close()

    async def _internal(self, msg: dict[str, Any]) -> None:
        if msg.get("type") == "peer":
            self._event("s3_down")
            await self._close_pc()
            return
        if msg.get("type") != "signal":
            return
        sdp = (msg.get("data") or {}).get("sdp")
        if not isinstance(sdp, dict) or sdp.get("type") != "offer":
            return  # aiortc embeds candidates in the SDP; trickle is not used on S3
        await self._close_pc()
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.pc = pc
        channels = self.channels

        @pc.on("datachannel")
        def _on_dc(channel: Any) -> None:
            channels.attach(channel)
            channel.on("message", self._on_car_message)

            channel.on("open", lambda: self._on_channel_open(channels))

            if channel.readyState == "open":
                self._on_channel_open(channels)

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            self._event("s3_state", state=pc.connectionState)
            if pc.connectionState in ("failed", "closed") and self.pc is pc:
                await self._close_pc()

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp["sdp"], type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        local = pc.localDescription
        answer = {"sdp": {"type": local.type, "sdp": local.sdp}}
        await self._run(self.router.on_signal("hub", "S3", answer))

    def _on_channel_open(self, channels: ChannelPair) -> None:
        if channels is self.channels and channels.is_open():
            self._event("s3_open")
            self.core.rtt_ms = self.core.rtt_ewma_ms = None  # do not show the old link's RTT
            for env in self.core.on_link_up(mono_ms(), wall_ms()):
                channels.send(env)

    def s3_state(self) -> str | None:
        """Return the S3 state for ``/status``."""
        if self.channels.is_open():
            return "connected"
        if self.pc is None:
            return None if not self.router.present("car_ctrl") else "connecting"
        return str(self.pc.connectionState)

    # ---- WebSocket -------------------------------------------------------

    async def _run(self, actions: list[Any]) -> None:
        for a in actions:
            if isinstance(a, Send) and isinstance(a.handle, web.WebSocketResponse):
                await _send_json(a.handle, a.msg)
            elif isinstance(a, Close) and isinstance(a.handle, web.WebSocketResponse):
                await a.handle.close(code=REPLACED_CLOSE_CODE, message=b"replaced")
            elif isinstance(a, Internal):
                await self._internal(a.msg)

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle one WebSocket connection for its whole life."""
        ws = web.WebSocketResponse(heartbeat=5.0)
        await ws.prepare(request)
        role: str | None = None
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                kind = data.get("type")
                if kind == "hello" and role is None:
                    r = data.get("role")
                    if r not in ROLES:
                        log.warning("unknown role %r", r)
                        break
                    role = str(r)
                    self._event("connect", role=role, peer=request.remote)
                    await _send_json(
                        ws,
                        {
                            "type": "welcome",
                            "config": build_config_json(self.cfg),
                            "topics": self.registry.to_json(),
                        },
                    )
                    await self._run(self.router.on_hello(role, ws))
                elif role is None:
                    continue
                elif kind == "signal":
                    await self._run(
                        self.router.on_signal(role, str(data.get("session")), data.get("data"))
                    )
                elif kind == "restart_req":
                    self._event("restart_req", role=role, session=data.get("session"))
                    await self._run(self.router.on_restart_req(role, str(data.get("session"))))
                elif kind == "env":
                    self._handle_input(role, data.get("env"))
                elif kind == "stats":
                    session = str(data.get("session"))
                    if session in ("S1", "S2"):
                        self.stats.setdefault(session, {})[role] = {
                            "at": mono_ms(),
                            "data": data.get("data"),
                        }
                        self._event("stats", role=role, session=session, data=data.get("data"))
        finally:
            if role is not None:
                self._event("disconnect", role=role)
                await self._run(self.router.on_close(role, ws))
        return ws

    # ---- HTTP ------------------------------------------------------------

    def snapshot(self) -> StatusSnapshot:
        """Collect current values for ``/status``."""
        now = mono_ms()
        sessions: dict[str, str | None] = {}
        stats: dict[str, Any] = {}
        for s in ("S1", "S2"):
            reports = {
                r: v
                for r, v in self.stats.get(s, {}).items()
                if now - v["at"] < STATS_STALE_MS and self.router.present(r)
            }
            stats[s] = {r: v["data"] for r, v in reports.items()} or None
            states = [
                v["data"].get("state") for v in reports.values() if isinstance(v["data"], dict)
            ]
            sessions[s] = (
                "connected"
                if states and all(x == "connected" for x in states)
                else (states[0] if states else None)
            )
        sessions["S3"] = self.s3_state()
        return StatusSnapshot(
            roles={r: self.router.present(r) for r in ROLES},
            sessions=sessions,
            rtt_ms=self.core.rtt_ms,
            rtt_ewma_ms=self.core.rtt_ewma_ms,
            car_state=self.core.car_state if self.channels.is_open() else None,
            latched=self.core.latched,
            last_input_age_ms=self.core.last_input_age_ms(now),
            stats=stats,
            dropped={**self.car_dropped, **{k: v for k, v in self.dropped.items()}},
            telemetry=dict(self.telemetry),
            up_budget_bps=self.cfg.up_budget_bps,
        )

    async def status(self, _r: web.Request) -> web.Response:
        """``GET /status``."""
        return web.json_response(build_status(self.snapshot()), headers=_NO_CACHE)

    async def config_json(self, _r: web.Request) -> web.Response:
        """``GET /config.json``."""
        return web.json_response(build_config_json(self.cfg), headers=_NO_CACHE)

    async def topics_json(self, _r: web.Request) -> web.Response:
        """``GET /topics.json``."""
        return web.json_response(self.registry.to_json(), headers=_NO_CACHE)


_NO_CACHE = {"Cache-Control": "no-cache"}

INDEX_HTML = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>NASURA hub</title>
<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;padding:2rem}
a{color:#8cf;font-size:1.4rem;display:block;margin:.8rem 0}</style></head><body>
<h1>NASURA hub</h1>
<a href="/quest/">quest（Quest 3S）</a><a href="/booth/">booth（操縦ブース）</a>
<a href="/car/">car（車載モニタ）</a><a href="/status">/status</a></body></html>"""


async def _send_json(ws: web.WebSocketResponse, msg: dict[str, Any]) -> None:
    if ws.closed:
        return
    with contextlib.suppress(ConnectionError, RuntimeError):
        await ws.send_str(json.dumps(msg, separators=(",", ":")))


@web.middleware
async def _no_cache(request: web.Request, handler: Any) -> web.StreamResponse:
    resp: web.StreamResponse = await handler(request)
    if not resp.prepared:
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def create_app(cfg: HubConfig, events: EventLog | None = None) -> web.Application:
    """Build the aiohttp application."""
    hub = Hub(cfg, events)
    app = web.Application(middlewares=[_no_cache])
    app["hub"] = hub
    web_dir = Path(cfg.web_dir)

    async def index(_r: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML, content_type="text/html")

    def page(name: str) -> Any:
        async def handler(_r: web.Request) -> web.FileResponse:
            return web.FileResponse(web_dir / name / "index.html")

        return handler

    def redirect(to: str) -> Any:
        async def handler(_r: web.Request) -> web.Response:
            raise web.HTTPFound(to)

        return handler

    app.router.add_get("/", index)
    app.router.add_get("/ws", hub.ws_handler)
    app.router.add_get("/status", hub.status)
    app.router.add_get("/config.json", hub.config_json)
    app.router.add_get("/topics.json", hub.topics_json)
    for name in ("quest", "booth", "car"):
        app.router.add_get(f"/{name}", redirect(f"/{name}/"))
        app.router.add_get(f"/{name}/", page(name))
    for name in ("quest", "booth", "car", "common", "vendor"):
        if (web_dir / name).is_dir():
            app.router.add_static(f"/{name}/", web_dir / name)
    app.on_startup.append(hub.start)
    app.on_cleanup.append(hub.stop)
    return app


def self_signed_context(directory: Path = Path(".certs")) -> ssl.SSLContext:
    """Create (once) and load a self-signed certificate for the R-1 fallback.

    Side Effects:
        Runs ``openssl`` and writes ``hub.key`` / ``hub.crt`` in ``directory``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    key, crt = directory / "hub.key", directory / "hub.crt"
    if not (key.exists() and crt.exists()):
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "365",
                "-subj",
                "/CN=nasura-hub",
                "-keyout",
                str(key),
                "-out",
                str(crt),
            ],
            check=True,
            capture_output=True,
        )
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(crt, key)
    return ctx
