"""IT-0001: a command reaches the on-car UDP out."""

from __future__ import annotations

import asyncio

import pytest
from itlib import System, drive_of, reach_run


@pytest.mark.verifies("AD-0005", spec="IT-0001")
@pytest.mark.verifies("AD-0008", spec="IT-0001")
async def test_quest_input_reaches_udp_out(system: System) -> None:
    assert system.udp is not None
    # Pass: out/effective with state=RUN and drive.v ~= 1.0 within 1 s of input start.
    _, first = await reach_run(system, timeout=1.0)
    v, w = drive_of(first.env)
    assert v == pytest.approx(1.0, abs=0.05)
    assert w == pytest.approx(0.0, abs=0.05)
    assert first.env["topic"] == "out/effective"

    # Pass: mean reception interval of out/effective is 50 +/- 10 ms.
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await asyncio.sleep(2.0)
    times = [r.t for r in system.udp.since(t0) if r.env.get("topic") == "out/effective"]
    assert len(times) >= 2
    mean_ms = (times[-1] - times[0]) / (len(times) - 1) * 1000.0
    assert 40.0 <= mean_ms <= 60.0, f"mean interval {mean_ms:.1f} ms"
