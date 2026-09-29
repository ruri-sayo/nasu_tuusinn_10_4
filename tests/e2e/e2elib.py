"""Shared helpers for the F-001 system/E2E tests (specification-derived).

Responsibilities:
    - Start and stop the public entry points (hub, car_ctrl) as real processes on free
      local ports, and headless Chrome instances that open the hub's pages.
    - Provide black-box observers of the public interfaces only: the car's UDP out
      (``out/effective``), the hub's ``/status`` endpoint, the WebSocket protocol
      (DD-0008) and the Chrome DevTools protocol for page reload/inspection.

Non-responsibilities:
    - Does not import or inspect anything under ``src/`` or ``web/``; everything here is
      derived from the requirement/design documents and the README.
    - Does not kill processes it did not start (only PIDs recorded in this module).

Constraints:
    - Real time is used throughout; helpers poll with short sleeps.
    - Chrome is optional: browser-based tests are skipped when it cannot be found
      (override the binary path with the ``CHROME`` environment variable).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Extension topic registered on both hub and car for the telemetry path (ST-0013).
TLM_TOPIC = "tlm/test_value"
TLM_EXTRA = f"{TLM_TOPIC}:up:rel:10"


# ---------------------------------------------------------------------------
# Ports and processes
# ---------------------------------------------------------------------------


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


class Proc:
    """A child process started by this test suite (tracked by PID for cleanup)."""

    def __init__(self, name: str, argv: list[str], log_path: Path) -> None:
        self.name = name
        self.argv = argv
        self.log_path = log_path
        self._log = open(log_path, "ab")  # noqa: SIM115 - closed in stop()
        self.popen = subprocess.Popen(
            argv,
            cwd=REPO_ROOT,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    @property
    def pid(self) -> int:
        return self.popen.pid

    def alive(self) -> bool:
        return self.popen.poll() is None

    def signal(self, sig: int) -> None:
        if self.alive():
            os.kill(self.pid, sig)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the process (and its process group, e.g. Chrome helpers)."""
        if self.alive():
            with contextlib.suppress(ProcessLookupError):
                os.kill(self.pid, signal.SIGCONT)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.pid, signal.SIGTERM)
            try:
                self.popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.pid, signal.SIGKILL)
                self.popen.wait(timeout=timeout)
        else:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self.pid, signal.SIGKILL)
        self._log.close()

    def kill_hard(self) -> None:
        """SIGKILL the process group immediately (simulates a crash)."""
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.pid, signal.SIGKILL)
        self.popen.wait(timeout=5)
        self._log.close()

    def tail(self, n: int = 40) -> str:
        try:
            return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-n:])
        except OSError:
            return ""


@dataclass
class System:
    """Addresses and processes of one hub + car_ctrl deployment on this machine."""

    workdir: Path
    hub_port: int
    udp_out: int
    udp_in: int
    extra_topics: list[str] = field(default_factory=list)
    hub_args: list[str] = field(default_factory=list)
    hub: Proc | None = None
    car: Proc | None = None
    _starts: int = 0

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.hub_port}"

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.hub_port}/ws"

    def _log(self, name: str) -> Path:
        self._starts += 1
        return self.workdir / f"{name}-{self._starts}.out"

    def start_hub(self) -> Proc:
        argv = [
            sys.executable,
            "-m",
            "nasura_comm.hub",
            "--port",
            str(self.hub_port),
            "--log-dir",
            str(self.workdir / "logs"),
        ]
        for t in self.extra_topics:
            argv += ["--extra-topic", t]
        argv += self.hub_args
        self.hub = Proc("hub", argv, self._log("hub"))
        wait_http_ok(f"{self.base}/status", timeout=15, proc=self.hub)
        return self.hub

    def start_car(self) -> Proc:
        argv = [
            sys.executable,
            "-m",
            "nasura_comm.car",
            "--hub",
            self.ws_url,
            "--udp-out",
            f"127.0.0.1:{self.udp_out}",
            "--udp-in",
            f"127.0.0.1:{self.udp_in}",
            "--log-dir",
            str(self.workdir / "logs"),
        ]
        for t in self.extra_topics:
            argv += ["--extra-topic", t]
        self.car = Proc("car", argv, self._log("car"))
        return self.car

    def stop_all(self) -> None:
        for p in (self.car, self.hub):
            if p is not None:
                with contextlib.suppress(Exception):
                    p.stop()


def wait_http_ok(url: str, timeout: float, proc: Proc | None = None) -> None:
    import urllib.request

    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        if proc is not None and not proc.alive():
            raise RuntimeError(f"{proc.name} exited early:\n{proc.tail()}")
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception as e:  # noqa: BLE001 - retried until deadline
            last = e
        time.sleep(0.1)
    raise TimeoutError(f"{url} not ready after {timeout}s: {last}")


def get_status_sync(base: str) -> dict[str, Any]:
    import urllib.request

    with urllib.request.urlopen(f"{base}/status", timeout=2) as r:
        return json.loads(r.read().decode())


@pytest.fixture
def workdir() -> Any:
    d = Path(tempfile.mkdtemp(prefix="nasura-e2e-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def system(workdir: Path) -> Any:
    """A running hub + car_ctrl pair with the test telemetry topic registered on both."""
    sysm = System(
        workdir=workdir,
        hub_port=free_tcp_port(),
        udp_out=free_udp_port(),
        udp_in=free_udp_port(),
        extra_topics=[TLM_EXTRA],
    )
    try:
        sysm.start_hub()
        sysm.start_car()
        yield sysm
    finally:
        sysm.stop_all()


# ---------------------------------------------------------------------------
# UDP out observer (DD-0007: out/effective datagrams)
# ---------------------------------------------------------------------------


class UdpRecorder:
    """Receives ``out/effective`` datagrams in a background thread.

    Each record is ``(t_monotonic_s, envelope_dict)``. Undecodable datagrams are kept
    as ``None`` payloads so a test can notice them.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self.records: list[tuple[float, dict[str, Any] | None]] = []
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", port))
        self._sock.settimeout(0.1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data, _ = self._sock.recvfrom(65536)
            except TimeoutError:
                continue
            except OSError:
                return
            t = time.monotonic()
            try:
                env = json.loads(data.decode())
            except (ValueError, UnicodeDecodeError):
                env = None
            with self._lock:
                self.records.append((t, env))

    def snapshot(self, since: float = 0.0) -> list[tuple[float, dict[str, Any] | None]]:
        with self._lock:
            return [r for r in self.records if r[0] >= since]

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            return self.records[-1][1] if self.records else None

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        self._sock.close()


@pytest.fixture
def udp_out(system: System) -> Any:
    rec = UdpRecorder(system.udp_out)
    yield rec
    rec.close()


def eff_state(env: dict[str, Any] | None) -> str | None:
    if not env:
        return None
    return env.get("payload", {}).get("state")


def eff_drive(env: dict[str, Any] | None) -> tuple[float, float]:
    d = (env or {}).get("payload", {}).get("drive", {})
    return float(d.get("v", 0.0)), float(d.get("w", 0.0))


def eff_is_stopped(env: dict[str, Any] | None) -> bool:
    """True when the effective command carries stop values (drive 0, arm disabled, stage 0)."""
    p = (env or {}).get("payload", {})
    v, w = eff_drive(env)
    arm = p.get("arm", {})
    stage = p.get("stage", {})
    return (
        v == 0.0
        and w == 0.0
        and not arm.get("enable", False)
        and float(stage.get("x", 0.0)) == 0.0
        and float(stage.get("z", 0.0)) == 0.0
    )


async def wait_udp(
    rec: UdpRecorder,
    pred: Callable[[dict[str, Any] | None], bool],
    timeout: float,
    since: float | None = None,
) -> tuple[float, dict[str, Any] | None]:
    """Wait until a datagram (received at/after ``since``) satisfies ``pred``."""
    start = time.monotonic() if since is None else since
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for t, env in rec.snapshot(start):
            if pred(env):
                return t, env
        await asyncio.sleep(0.02)
    last = rec.latest()
    raise AssertionError(f"no matching UDP out datagram within {timeout}s; latest={last}")


# ---------------------------------------------------------------------------
# WebSocket client for the DD-0008 protocol
# ---------------------------------------------------------------------------


class WsClient:
    """A minimal browser-less client speaking the hub's WebSocket protocol."""

    def __init__(self, url: str, role: str) -> None:
        self.url = url
        self.role = role
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.messages: list[dict[str, Any]] = []
        self.welcome: dict[str, Any] | None = None
        self.close_code: int | None = None
        self._reader: asyncio.Task[None] | None = None
        self._seq: dict[str, int] = {}

    async def connect(self, timeout: float = 5.0) -> WsClient:
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(self.url, heartbeat=None)
        await self.ws.send_json({"type": "hello", "role": self.role})
        self._reader = asyncio.create_task(self._read())
        deadline = time.monotonic() + timeout
        while self.welcome is None:
            if time.monotonic() > deadline:
                raise AssertionError(f"no welcome for role {self.role}")
            if self.close_code is not None:
                raise AssertionError(f"closed before welcome: {self.close_code}")
            await asyncio.sleep(0.02)
        return self

    async def _read(self) -> None:
        assert self.ws is not None
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                with contextlib.suppress(ValueError):
                    data = json.loads(msg.data)
                    if data.get("type") == "welcome" and self.welcome is None:
                        self.welcome = data
                    self.messages.append(data)
        self.close_code = self.ws.close_code if self.ws.close_code is not None else -1

    @property
    def closed(self) -> bool:
        return self.close_code is not None

    async def send_env(self, topic: str, payload: dict[str, Any]) -> None:
        assert self.ws is not None
        seq = self._seq.get(topic, 0) + 1
        self._seq[topic] = seq
        env = {
            "topic": topic,
            "ver": 1,
            "seq": seq,
            "ts": now_ms(),
            "src": self.role,
            "payload": payload,
        }
        await self.ws.send_json({"type": "env", "env": env})

    def envs(self, topic: str) -> list[dict[str, Any]]:
        out = []
        for m in self.messages:
            if m.get("type") == "env" and m.get("env", {}).get("topic") == topic:
                out.append(m["env"])
        return out

    async def close(self) -> None:
        if self.ws is not None and not self.ws.closed:
            with contextlib.suppress(Exception):
                await self.ws.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(BaseException):
                await self._reader
        if self.session is not None:
            await self.session.close()


def quest_input(
    *,
    deadman: bool = True,
    lx: float = 0.0,
    ly: float = 0.0,
    right_grip: float = 0.0,
    right_pose: dict[str, Any] | None = None,
    trigger: float = 0.0,
    a: bool = False,
    b: bool = False,
    ry: float = 0.0,
) -> dict[str, Any]:
    """Build an ``in/quest`` payload per DD-0004 (Gamepad axes: up is y < 0)."""
    return {
        "left": {
            "axes": [lx, ly],
            "trigger": 0.0,
            "grip": 1.0 if deadman else 0.0,
            "x": False,
            "y": False,
            "thumb": False,
            "pose": None,
        },
        "right": {
            "axes": [0.0, ry],
            "trigger": trigger,
            "grip": right_grip,
            "a": a,
            "b": b,
            "thumb": False,
            "pose": right_pose,
        },
    }


class InputPump:
    """Sends ``in/quest`` at 30 Hz from a WsClient until stopped (like the quest page)."""

    def __init__(self, client: WsClient, payload: dict[str, Any], hz: float = 30.0) -> None:
        self.client = client
        self.payload = payload
        self.period = 1.0 / hz
        self._task: asyncio.Task[None] | None = None

    def start(self) -> InputPump:
        self._task = asyncio.create_task(self._run())
        return self

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self.client.send_env("in/quest", self.payload)
            await asyncio.sleep(self.period)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(BaseException):
                await self._task
            self._task = None


async def get_status(base: str) -> dict[str, Any]:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}/status", timeout=aiohttp.ClientTimeout(total=2)) as r:
            assert r.status == 200
            return await r.json(content_type=None)


async def wait_status(
    base: str, pred: Callable[[dict[str, Any]], bool], timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        with contextlib.suppress(Exception):
            last = await get_status(base)
            if pred(last):
                return last
        await asyncio.sleep(0.2)
    raise AssertionError(f"/status condition not met within {timeout}s; last={last}")


def s3_up(st: dict[str, Any]) -> bool:
    return st.get("sessions", {}).get("S3") == "connected"


# ---------------------------------------------------------------------------
# Headless Chrome + DevTools protocol
# ---------------------------------------------------------------------------


def chrome_path() -> str | None:
    cand = os.environ.get("CHROME") or DEFAULT_CHROME
    if os.path.isfile(cand) and os.access(cand, os.X_OK):
        return cand
    found = shutil.which(cand)
    return found


class ChromePage:
    """One headless Chrome process (own profile) showing one hub page."""

    def __init__(self, binary: str, url: str, workdir: Path, name: str) -> None:
        self.url = url
        self.name = name
        self.profile = Path(tempfile.mkdtemp(prefix=f"chrome-{name}-", dir=workdir))
        argv = [
            binary,
            "--headless=new",
            f"--user-data-dir={self.profile}",
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--window-size=1280,720",
            "--remote-debugging-port=0",
            url,
        ]
        self.proc = Proc(f"chrome-{name}", argv, workdir / f"chrome-{name}.out")

    def devtools_port(self, timeout: float = 30.0) -> int:
        f = self.profile / "DevToolsActivePort"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if f.exists():
                lines = f.read_text().splitlines()
                if lines and lines[0].strip().isdigit():
                    return int(lines[0])
            if not self.proc.alive():
                raise RuntimeError(f"chrome {self.name} exited:\n{self.proc.tail()}")
            time.sleep(0.1)
        raise TimeoutError(f"chrome {self.name}: no DevToolsActivePort")

    async def _page_ws_url(self) -> str:
        port = self.devtools_port()
        async with aiohttp.ClientSession() as s:
            for _ in range(100):
                with contextlib.suppress(Exception):
                    async with s.get(f"http://127.0.0.1:{port}/json") as r:
                        targets = await r.json(content_type=None)
                    for t in targets:
                        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                            return str(t["webSocketDebuggerUrl"])
                await asyncio.sleep(0.1)
        raise AssertionError(f"chrome {self.name}: no page target")

    async def cdp(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one DevTools command on a short-lived connection and return its result."""
        url = await self._page_ws_url()
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(url, max_msg_size=0) as ws:
                await ws.send_json({"id": 1, "method": method, "params": params or {}})
                async for msg in ws:
                    data = json.loads(msg.data)
                    if data.get("id") == 1:
                        if "error" in data:
                            raise AssertionError(f"CDP {method}: {data['error']}")
                        return dict(data.get("result", {}))
        raise AssertionError(f"CDP {method}: no reply")

    async def evaluate(self, expr: str) -> Any:
        res = await self.cdp(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
        )
        return res.get("result", {}).get("value")

    def stop(self) -> None:
        self.proc.stop()
