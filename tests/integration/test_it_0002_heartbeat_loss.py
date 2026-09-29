"""IT-0002: the car stops when the heartbeat is lost (hub SIGKILL) and recovers."""

from __future__ import annotations

import asyncio

import pytest
from itlib import System, drive_of, is_stopped_drive, reach_run, state_of


def _is_stop(env: dict) -> bool:
    return state_of(env) == "STOP" and is_stopped_drive(env)


@pytest.mark.verifies("AD-0007", spec="IT-0002")
async def test_hub_kill_stops_car_and_recovers(system: System) -> None:
    assert system.udp is not None
    loop = asyncio.get_running_loop()
    sender, _ = await reach_run(system)
    await asyncio.sleep(0.5)

    # 1. SIGKILL the hub.
    t_kill = loop.time()
    system.kill_hub()
    await sender.stop()

    # Pass: STOP with drive 0/0 within 550 ms of the kill.
    rec = await system.udp.wait_for(_is_stop, timeout=1.5, since=t_kill)
    assert rec is not None, "no out/effective with state=STOP, drive 0/0 within 1.5 s"
    latency_ms = (rec.t - t_kill) * 1000.0
    assert latency_ms <= 550.0, f"STOP observed {latency_ms:.0f} ms after hub kill"

    # Pass: stop values keep coming at 20 Hz.
    t_obs = rec.t
    await asyncio.sleep(1.5)
    after = [r for r in system.udp.since(t_obs) if r.env.get("topic") == "out/effective"]
    assert all(_is_stop(r.env) for r in after), [
        (state_of(r.env), drive_of(r.env)) for r in after if not _is_stop(r.env)
    ]
    mean_ms = (after[-1].t - after[0].t) / (len(after) - 1) * 1000.0
    assert 40.0 <= mean_ms <= 60.0, f"mean interval {mean_ms:.1f} ms"

    # Pass: after the hub restarts (same port), S3 reconnects automatically within 15 s.
    await system.start_hub()
    await system.wait_s3_connected(timeout=15.0)

    # Pass: resuming input returns the car to RUN.
    t_resume = loop.time()
    await system.start_driving()
    rec = await system.udp.wait_for(
        lambda e: state_of(e) == "RUN" and abs(drive_of(e)[0] - 1.0) < 0.05,
        timeout=5.0,
        since=t_resume,
    )
    assert rec is not None, "car did not return to RUN after input resumed"
