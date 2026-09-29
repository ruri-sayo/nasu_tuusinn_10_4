"""IT-0005: signaling relay and reconnection through the hub WebSocket."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from itlib import System

SDP = {"type": "offer", "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=IT-0005\r\n"}
CANDIDATE = {
    "candidate": "candidate:1 1 udp 2130706431 127.0.0.1 50000 typ host",
    "sdpMid": "0",
    "sdpMLineIndex": 0,
}


def _is_restart(session: str) -> Any:
    return lambda m: m.get("type") == "restart" and m.get("session") == session


def _signals(messages: list[dict[str, Any]], start: int = 0) -> list[dict[str, Any]]:
    return [m for m in messages[start:] if m.get("type") == "signal"]


@pytest.mark.verifies("AD-0002", spec="IT-0005")
@pytest.mark.verifies("AD-0004", spec="IT-0005")
async def test_signaling_relay_and_reconnect(system: System) -> None:
    booth = await system.connect("booth")

    # 1. car_media then quest connect -> car_media receives restart(S1).
    car_media = await system.connect("car_media")
    quest = await system.connect("quest")
    msg = await car_media.wait_for(_is_restart("S1"), timeout=2.0)
    assert msg is not None, "car_media did not receive restart(S1)"

    # 2. car_media sends S1 sdp, quest sends S1 candidate -> each reaches only the peer.
    cm_mark, q_mark, b_mark = len(car_media.messages), len(quest.messages), len(booth.messages)
    await car_media.send({"type": "signal", "session": "S1", "data": {"sdp": SDP}})
    await quest.send({"type": "signal", "session": "S1", "data": {"candidate": CANDIDATE}})
    got_q = await quest.wait_for(
        lambda m: m.get("type") == "signal" and "sdp" in m.get("data", {}),
        timeout=2.0,
        start=q_mark,
    )
    got_cm = await car_media.wait_for(
        lambda m: m.get("type") == "signal" and "candidate" in m.get("data", {}),
        timeout=2.0,
        start=cm_mark,
    )
    await asyncio.sleep(0.3)
    assert got_q is not None, "quest did not receive the S1 sdp"
    assert got_q["session"] == "S1" and got_q["data"]["sdp"] == SDP
    assert got_cm is not None, "car_media did not receive the S1 candidate"
    assert got_cm["session"] == "S1" and got_cm["data"]["candidate"] == CANDIDATE
    # Only the peer receives: no echo to the sender, nothing to booth.
    assert len(_signals(quest.messages, q_mark)) == 1
    assert len(_signals(car_media.messages, cm_mark)) == 1
    assert _signals(booth.messages, b_mark) == []

    # 3. quest disconnects -> car_media receives peer down(S1).
    cm_mark = len(car_media.messages)
    await quest.close()
    msg = await car_media.wait_for(
        lambda m: m.get("type") == "peer" and m.get("session") == "S1" and m.get("state") == "down",
        timeout=2.0,
        start=cm_mark,
    )
    assert msg is not None, "car_media did not receive peer down(S1)"

    # quest reconnects -> car_media receives restart(S1) again.
    cm_mark = len(car_media.messages)
    await system.connect("quest")
    msg = await car_media.wait_for(_is_restart("S1"), timeout=2.0, start=cm_mark)
    assert msg is not None, "car_media did not receive restart(S1) after quest reconnect"
