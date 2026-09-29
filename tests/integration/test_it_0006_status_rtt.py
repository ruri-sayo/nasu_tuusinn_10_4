"""IT-0006: RTT and car state appear in /status."""

from __future__ import annotations

import asyncio
from numbers import Real
from typing import Any

import pytest
from itlib import System, reach_run


def _rtt(st: dict[str, Any]) -> Any:
    return st.get("control", {}).get("rtt_ms")


@pytest.mark.verifies("AD-0009", spec="IT-0006")
async def test_status_reports_rtt_and_state(system: System) -> None:
    await reach_run(system)
    await asyncio.sleep(1.0)

    # 1. /status in the IT-0001 state.
    st = await system.status()
    assert st["roles"]["car_ctrl"] is True
    assert st["sessions"]["S3"] == "connected"
    rtt0 = _rtt(st)
    assert isinstance(rtt0, Real) and not isinstance(rtt0, bool), f"rtt_ms={rtt0!r}"
    assert st["control"]["car_state"] == "RUN"

    # 2. Restart car_ctrl with a 100 ms artificial delay before each ack, then re-fetch.
    system.kill_car()
    await system.start_car(ack_delay_ms=100)
    await system.wait_s3_connected()
    st = await system.wait_status(lambda s: s["control"].get("car_state") == "RUN", timeout=3.0)
    assert st is not None, "car_state did not return to RUN after car_ctrl restart"
    # The spec gives no deadline for the new RTT to show up; allow a few heartbeat cycles.
    st = await system.wait_status(
        lambda s: isinstance(_rtt(s), Real) and _rtt(s) - rtt0 >= 100, timeout=5.0
    )
    rtt1 = _rtt(await system.status()) if st is None else _rtt(st)
    assert st is not None, f"rtt_ms did not grow by >= 100 ms: {rtt0} -> {rtt1}"
