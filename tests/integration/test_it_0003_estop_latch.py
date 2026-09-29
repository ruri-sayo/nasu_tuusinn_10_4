"""IT-0003: E-STOP latches and can be released only from the booth."""

from __future__ import annotations

import asyncio

import pytest
from itlib import System, drive_of, is_stopped_drive, reach_run, state_of


def _car_state(st: dict) -> str | None:
    return st.get("control", {}).get("car_state")


@pytest.mark.verifies("AD-0007", spec="IT-0003")
async def test_estop_latch_and_release(system: System) -> None:
    assert system.udp is not None
    loop = asyncio.get_running_loop()
    sender, _ = await reach_run(system)
    quest = sender.client
    booth = await system.connect("booth")
    await asyncio.sleep(0.3)
    st = await system.wait_status(lambda s: _car_state(s) == "RUN", timeout=2.0)
    assert st is not None, "hub /status car_state is not RUN before E-STOP"

    # 1. quest sends in/estop -> ESTOP with drive 0/0 within 200 ms.
    t1 = loop.time()
    await quest.send_env("in/estop", {"source": "quest", "reason": "IT-0003"})
    rec = await system.udp.wait_for(
        lambda e: state_of(e) == "ESTOP" and is_stopped_drive(e), timeout=1.0, since=t1
    )
    assert rec is not None, "no out/effective with state=ESTOP, drive 0/0 within 1 s"
    latency_ms = (rec.t - t1) * 1000.0
    assert latency_ms <= 200.0, f"ESTOP observed {latency_ms:.0f} ms after in/estop"
    st = await system.wait_status(lambda s: _car_state(s) == "ESTOP", timeout=2.0)
    assert st is not None, "hub /status car_state did not become ESTOP"

    # 2. quest sends in/estop_release -> stays ESTOP.
    t2 = loop.time()
    await quest.send_env("in/estop_release", {"source": "quest"})
    await asyncio.sleep(1.0)
    after = [r.env for r in system.udp.since(t2) if r.env.get("topic") == "out/effective"]
    assert after, "no out/effective received"
    assert all(state_of(e) == "ESTOP" and is_stopped_drive(e) for e in after), [
        (state_of(e), drive_of(e)) for e in after
    ]
    assert _car_state(await system.status()) == "ESTOP"

    # 3. booth sends in/estop_release -> back to RUN and commands follow the input.
    t3 = loop.time()
    await booth.send_env("in/estop_release", {"source": "booth"})
    rec = await system.udp.wait_for(
        lambda e: state_of(e) == "RUN" and abs(drive_of(e)[0] - 1.0) < 0.05,
        timeout=2.0,
        since=t3,
    )
    assert rec is not None, "car did not return to RUN with drive.v~1.0 after booth release"
    st = await system.wait_status(lambda s: _car_state(s) == "RUN", timeout=2.0)
    assert st is not None, "hub /status car_state did not return to RUN"
