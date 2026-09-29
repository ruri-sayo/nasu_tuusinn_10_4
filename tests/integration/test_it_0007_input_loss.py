"""IT-0007: loss of quest input produces a stop command."""

from __future__ import annotations

import asyncio

import pytest
from itlib import (
    QuestSender,
    System,
    drive_of,
    is_stopped_drive,
    quest_payload,
    reach_run,
    state_of,
)


@pytest.mark.verifies("AD-0005", spec="IT-0007")
@pytest.mark.verifies("AD-0007", spec="IT-0007")
async def test_input_loss_stops_drive(system: System) -> None:
    assert system.udp is not None
    sender, _ = await reach_run(system)
    await asyncio.sleep(0.5)

    # 1. quest stops sending (connection kept).
    await sender.stop()
    assert sender.last_sent is not None
    t_stop = sender.last_sent
    rec = await system.udp.wait_for(is_stopped_drive, timeout=1.0, since=t_stop)
    assert rec is not None, "no out/effective with drive 0/0 within 1 s of input stop"
    latency_ms = (rec.t - t_stop) * 1000.0
    assert latency_ms <= 350.0, f"drive 0/0 observed {latency_ms:.0f} ms after input stop"
    assert state_of(rec.env) == "RUN", f"state={state_of(rec.env)}"
    await asyncio.sleep(0.3)
    later = [r.env for r in system.udp.since(rec.t) if r.env.get("topic") == "out/effective"]
    assert all(state_of(e) == "RUN" and is_stopped_drive(e) for e in later), [
        (state_of(e), drive_of(e)) for e in later
    ]

    # 2. resume with deadman=false -> drive stays 0/0.
    loop = asyncio.get_running_loop()
    t_resume = loop.time()
    resumed = QuestSender(sender.client, quest_payload(deadman=False, left_y=-1.0))
    system.senders.append(resumed)
    resumed.start()
    await asyncio.sleep(1.0)
    during = [r.env for r in system.udp.since(t_resume) if r.env.get("topic") == "out/effective"]
    assert during, "no out/effective received"
    assert all(is_stopped_drive(e) for e in during), [drive_of(e) for e in during]
