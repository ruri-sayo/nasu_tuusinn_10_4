"""IT-0004: telemetry injection via UDP in, and discarding of unregistered / excess data."""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any

import pytest
from itlib import System, now_ms

EXTRA = ("tlm/test_value:up:ctrl:5",)


class _Injector:
    """Plays a local on-car module throwing envelopes into UDP in (AD-0008)."""

    def __init__(self, port: int) -> None:
        self.addr = ("127.0.0.1", port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq: dict[str, int] = {}

    def send(self, topic: str, payload: dict[str, Any]) -> None:
        seq = self.seq.get(topic, 0)
        self.seq[topic] = seq + 1
        env = {
            "topic": topic,
            "ver": 1,
            "seq": seq,
            "ts": now_ms(),
            "src": "car_local",
            "payload": payload,
        }
        self.sock.sendto(json.dumps(env).encode("utf-8"), self.addr)

    async def stream(self, topic: str, hz: float, duration_s: float, phase: int) -> int:
        loop = asyncio.get_running_loop()
        period = 1.0 / hz
        n = round(hz * duration_s)
        start = loop.time()
        for i in range(n):
            self.send(topic, {"phase": phase, "i": i})
            await asyncio.sleep(max(0.0, start + (i + 1) * period - loop.time()))
        return n

    def close(self) -> None:
        self.sock.close()


def _count(messages: list[dict[str, Any]], topic: str, phase: int) -> int:
    n = 0
    for m in messages:
        if m.get("type") != "env":
            continue
        env = m.get("env", {})
        if env.get("topic") == topic and env.get("payload", {}).get("phase") == phase:
            n += 1
    return n


@pytest.mark.verifies("AD-0006", spec="IT-0004")
@pytest.mark.verifies("AD-0008", spec="IT-0004")
async def test_telemetry_injection_and_discard(make_system: Any) -> None:
    system: System = await make_system(extra_topics=EXTRA)
    booth = await system.connect("booth")
    inj = _Injector(system.udp_in_port)
    try:
        # 1. tlm/test_value at 5 Hz for 3 s -> 15 +/- 2 delivered to booth as env.
        await inj.stream("tlm/test_value", 5.0, 3.0, phase=1)
        await asyncio.sleep(0.5)
        n1 = _count(booth.messages, "tlm/test_value", 1)
        assert 13 <= n1 <= 17, f"phase 1 delivered {n1}"
        assert system.processes_alive()

        # 2. unregistered tlm/unknown -> not delivered, counted in /status dropped.
        for i in range(3):
            inj.send("tlm/unknown", {"phase": 2, "i": i})
            await asyncio.sleep(0.05)
        st = await system.wait_status(
            lambda s: s.get("dropped", {}).get("tlm/unknown", 0) >= 1, timeout=11.0
        )
        assert st is not None, "tlm/unknown not counted in /status dropped"
        assert _count(booth.messages, "tlm/unknown", 2) == 0
        assert system.processes_alive()

        # 3. tlm/test_value at 50 Hz for 2 s -> limited to 10 +/- 2.
        await inj.stream("tlm/test_value", 50.0, 2.0, phase=3)
        await asyncio.sleep(0.5)
        n3 = _count(booth.messages, "tlm/test_value", 3)
        assert 8 <= n3 <= 12, f"phase 3 delivered {n3}"
        assert _count(booth.messages, "tlm/unknown", 2) == 0
        assert system.processes_alive()
        await system.status()  # hub still answers
    finally:
        inj.close()
