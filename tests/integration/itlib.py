"""Helpers for F-001 integration tests (50-integration-test-spec.md).

hub and car_ctrl run as real subprocesses. quest / booth / car_media are played by
WebSocket test clients, and a UDP receiver stands in for the downstream consumer of
``out/effective``. Everything is derived from the AD/DD documents and the public CLI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

S3_CONNECT_TIMEOUT_S = 10.0
DRIVE_EPS = 1e-6


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Payload helpers (DD-0004, DD-0007)
# ---------------------------------------------------------------------------


def quest_payload(deadman: bool, left_y: float = 0.0) -> dict[str, Any]:
    """Build an ``in/quest`` payload per DD-0004 (deadman = left.grip > 0.5)."""
    return {
        "left": {
            "axes": [0.0, left_y],
            "trigger": 0.0,
            "grip": 1.0 if deadman else 0.0,
            "x": False,
            "y": False,
            "thumb": False,
            "pose": None,
        },
        "right": {
            "axes": [0.0, 0.0],
            "trigger": 0.0,
            "grip": 0.0,
            "a": False,
            "b": False,
            "thumb": False,
            "pose": None,
        },
    }


def drive_of(env: dict[str, Any]) -> tuple[float, float]:
    drive = env["payload"]["drive"]
    return float(drive["v"]), float(drive["w"])


def is_stopped_drive(env: dict[str, Any]) -> bool:
    v, w = drive_of(env)
    return abs(v) < DRIVE_EPS and abs(w) < DRIVE_EPS


def state_of(env: dict[str, Any]) -> str:
    return str(env["payload"]["state"])


# ---------------------------------------------------------------------------
# UDP out receiver (stand-in for the downstream adapter, AD-0008)
# ---------------------------------------------------------------------------


@dataclass
class UdpRecord:
    t: float  # event loop monotonic time (s)
    env: dict[str, Any]


class UdpOutReceiver(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.records: list[UdpRecord] = []
        self.invalid = 0
        self._event = asyncio.Event()
        self._loop = asyncio.get_running_loop()

    def datagram_received(self, data: bytes, addr: Any) -> None:
        try:
            env = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.invalid += 1
            return
        self.records.append(UdpRecord(self._loop.time(), env))
        self._event.set()

    def since(self, t0: float) -> list[UdpRecord]:
        return [r for r in self.records if r.t >= t0]

    async def wait_for(
        self,
        pred: Callable[[dict[str, Any]], bool],
        timeout: float,
        since: float | None = None,
    ) -> UdpRecord | None:
        """Return the first record at/after ``since`` that satisfies ``pred``."""
        t0 = self._loop.time() if since is None else since
        deadline = self._loop.time() + timeout
        idx = 0
        while True:
            while idx < len(self.records):
                rec = self.records[idx]
                idx += 1
                if rec.t >= t0 and rec.env.get("topic") == "out/effective" and pred(rec.env):
                    return rec
            remaining = deadline - self._loop.time()
            if remaining <= 0:
                return None
            self._event.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._event.wait(), remaining)


# ---------------------------------------------------------------------------
# WebSocket test client (DD-0008)
# ---------------------------------------------------------------------------


@dataclass
class WsClient:
    role: str
    ws: aiohttp.ClientWebSocketResponse
    welcome: dict[str, Any]
    messages: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False
    _seq: dict[str, int] = field(default_factory=dict)
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _reader: asyncio.Task[None] | None = None

    def start_reader(self) -> None:
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    with contextlib.suppress(json.JSONDecodeError):
                        self.messages.append(json.loads(msg.data))
                        self._event.set()
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    break
        except (aiohttp.ClientError, ConnectionError):
            pass
        finally:
            self.closed = True
            self._event.set()

    async def send(self, msg: dict[str, Any]) -> None:
        await self.ws.send_str(json.dumps(msg))

    async def send_env(self, topic: str, payload: dict[str, Any]) -> None:
        seq = self._seq.get(topic, 0)
        self._seq[topic] = seq + 1
        env = {
            "topic": topic,
            "ver": 1,
            "seq": seq,
            "ts": now_ms(),
            "src": self.role,
            "payload": payload,
        }
        await self.send({"type": "env", "env": env})

    async def wait_for(
        self, pred: Callable[[dict[str, Any]], bool], timeout: float, start: int = 0
    ) -> dict[str, Any] | None:
        """Return the first message (from index ``start``) matching ``pred``."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        idx = start
        while True:
            while idx < len(self.messages):
                msg = self.messages[idx]
                idx += 1
                if pred(msg):
                    return msg
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            self._event.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._event.wait(), remaining)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.ws.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader


class QuestSender:
    """Sends ``in/quest`` at 30 Hz from a quest client (AD-0005)."""

    PERIOD_S = 1.0 / 30.0

    def __init__(self, client: WsClient, payload: dict[str, Any]) -> None:
        self.client = client
        self.payload = payload
        self.last_sent: float | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_t = loop.time()
        while True:
            try:
                await self.client.send_env("in/quest", self.payload)
                self.last_sent = loop.time()
            except (aiohttp.ClientError, ConnectionError, RuntimeError):
                # Connection lost (e.g. hub killed): stop sending.
                return
            next_t += self.PERIOD_S
            await asyncio.sleep(max(0.0, next_t - loop.time()))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


# ---------------------------------------------------------------------------
# System under test
# ---------------------------------------------------------------------------


class System:
    def __init__(self, tmp_path: Path, extra_topics: tuple[str, ...] = ()) -> None:
        self.tmp_path = tmp_path
        self.extra_topics = extra_topics
        self.port = free_tcp_port()
        self.udp_in_port = free_udp_port()
        self.udp_out_port = 0
        self.hub: subprocess.Popen[bytes] | None = None
        self.car: subprocess.Popen[bytes] | None = None
        self.udp: UdpOutReceiver | None = None
        self._udp_transport: asyncio.DatagramTransport | None = None
        self.session: aiohttp.ClientSession | None = None
        self.clients: list[WsClient] = []
        self.senders: list[QuestSender] = []
        self._n_hub = 0
        self._n_car = 0
        self._logs: list[Any] = []

    # -- URLs -------------------------------------------------------------

    @property
    def http_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws"

    # -- lifecycle --------------------------------------------------------

    async def open(self) -> None:
        loop = asyncio.get_running_loop()
        transport, proto = await loop.create_datagram_endpoint(
            UdpOutReceiver, local_addr=("127.0.0.1", 0)
        )
        self._udp_transport = transport
        self.udp = proto
        self.udp_out_port = int(transport.get_extra_info("sockname")[1])
        self.session = aiohttp.ClientSession()

    def _extra_args(self) -> list[str]:
        args: list[str] = []
        for spec in self.extra_topics:
            args += ["--extra-topic", spec]
        return args

    def _spawn(self, name: str, args: list[str]) -> subprocess.Popen[bytes]:
        log = open(self.tmp_path / f"{name}.stdout.log", "wb")
        self._logs.append(log)
        return subprocess.Popen(
            [sys.executable, "-m", *args],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    async def start_hub(self) -> None:
        self._n_hub += 1
        log_dir = self.tmp_path / f"hub_logs_{self._n_hub}"
        log_dir.mkdir()
        self.hub = self._spawn(
            f"hub{self._n_hub}",
            [
                "nasura_comm.hub",
                "--port",
                str(self.port),
                "--log-dir",
                str(log_dir),
                *self._extra_args(),
            ],
        )
        await self._wait_http_up(10.0)

    async def start_car(self, ack_delay_ms: int | None = None) -> None:
        self._n_car += 1
        log_dir = self.tmp_path / f"car_logs_{self._n_car}"
        log_dir.mkdir()
        args = [
            "nasura_comm.car",
            "--hub",
            self.ws_url,
            "--udp-out",
            f"127.0.0.1:{self.udp_out_port}",
            "--udp-in",
            f"127.0.0.1:{self.udp_in_port}",
            "--log-dir",
            str(log_dir),
            *self._extra_args(),
        ]
        if ack_delay_ms is not None:
            args += ["--ack-delay-ms", str(ack_delay_ms)]
        self.car = self._spawn(f"car{self._n_car}", args)

    @staticmethod
    def _kill(proc: subprocess.Popen[bytes] | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)

    def kill_hub(self) -> None:
        """SIGKILL the hub process (IT-0002)."""
        self._kill(self.hub)

    def kill_car(self) -> None:
        self._kill(self.car)

    def processes_alive(self) -> bool:
        return all(p is not None and p.poll() is None for p in (self.hub, self.car))

    async def close(self) -> None:
        for sender in self.senders:
            with contextlib.suppress(Exception):
                await sender.stop()
        for client in self.clients:
            with contextlib.suppress(Exception):
                await client.close()
        self._kill(self.car)
        self._kill(self.hub)
        if self.session is not None:
            await self.session.close()
        if self._udp_transport is not None:
            self._udp_transport.close()
        for log in self._logs:
            log.close()

    # -- HTTP /status (DD-0009) ------------------------------------------

    async def status(self) -> dict[str, Any]:
        assert self.session is not None
        async with self.session.get(
            f"{self.http_url}/status", timeout=aiohttp.ClientTimeout(total=2)
        ) as resp:
            assert resp.status == 200
            data: dict[str, Any] = await resp.json(content_type=None)
            return data

    async def _wait_http_up(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            if self.hub is not None and self.hub.poll() is not None:
                raise RuntimeError(f"hub exited with code {self.hub.returncode}")
            try:
                await self.status()
                return
            except (aiohttp.ClientError, asyncio.TimeoutError, AssertionError) as exc:
                last_exc = exc
            await asyncio.sleep(0.1)
        raise TimeoutError(f"hub HTTP not up within {timeout}s: {last_exc!r}")

    async def wait_status(
        self, pred: Callable[[dict[str, Any]], bool], timeout: float
    ) -> dict[str, Any] | None:
        """Poll ``/status`` until ``pred`` holds; return that status or None."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                st = await self.status()
                if pred(st):
                    return st
            except (aiohttp.ClientError, asyncio.TimeoutError, AssertionError):
                pass
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.1)

    async def wait_s3_connected(self, timeout: float = S3_CONNECT_TIMEOUT_S) -> None:
        st = await self.wait_status(
            lambda s: s.get("sessions", {}).get("S3") == "connected", timeout
        )
        assert st is not None, f"S3 did not become connected within {timeout}s"

    # -- WebSocket clients -----------------------------------------------

    async def connect(self, role: str) -> WsClient:
        assert self.session is not None
        ws = await self.session.ws_connect(self.ws_url, heartbeat=None)
        await ws.send_str(json.dumps({"type": "hello", "role": role}))
        welcome: dict[str, Any] | None = None
        pending: list[dict[str, Any]] = []
        deadline = time.monotonic() + 5.0
        while welcome is None:
            msg = await ws.receive(timeout=max(0.1, deadline - time.monotonic()))
            if msg.type != aiohttp.WSMsgType.TEXT:
                raise RuntimeError(f"unexpected WS message while waiting welcome: {msg}")
            data = json.loads(msg.data)
            if data.get("type") == "welcome":
                welcome = data
            else:
                pending.append(data)
        client = WsClient(role=role, ws=ws, welcome=welcome, messages=pending)
        client.start_reader()
        self.clients.append(client)
        return client

    async def start_driving(self, quest: WsClient | None = None) -> QuestSender:
        """Reach "the IT-0001 state": quest sends deadman=true, left.y=-1 at 30 Hz."""
        if quest is None:
            quest = await self.connect("quest")
        sender = QuestSender(quest, quest_payload(deadman=True, left_y=-1.0))
        self.senders.append(sender)
        sender.start()
        return sender


async def reach_run(system: System, timeout: float = 1.0) -> tuple[QuestSender, UdpRecord]:
    """Start 30 Hz driving input and wait for RUN with drive.v ~= 1.0."""
    assert system.udp is not None
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    sender = await system.start_driving()
    rec = await system.udp.wait_for(
        lambda e: state_of(e) == "RUN" and abs(drive_of(e)[0] - 1.0) < 0.05,
        timeout=timeout,
        since=t0,
    )
    assert rec is not None, "out/effective did not reach state=RUN, drive.v~1.0"
    return sender, rec
