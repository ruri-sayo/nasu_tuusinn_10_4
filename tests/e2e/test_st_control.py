"""System/E2E tests for the control plane, safety and local I/F (no browser needed).

Responsibilities:
    - Drive the real hub and car_ctrl processes from the outside: Quest/booth input via
      the hub WebSocket (a browser-less client with the same role the pages use), local
      telemetry via the car's UDP in, and observation via the car's UDP out and /status.
    - Automate the dev-machine subset of ST-0006, ST-0008(a), ST-0009, ST-0010,
      ST-0011 (hub / car_ctrl restart) and ST-0013.

Non-responsibilities:
    - Media sessions (S1/S2) and pages; see test_st_media.py.
    - Real network faults (cable pull): a frozen hub (SIGSTOP) and a crashed hub
      (SIGKILL) stand in for the loss of the hub -> car control link.
"""

from __future__ import annotations

import asyncio
import json
import math
import signal
import socket
import time
from typing import Any

import pytest
from e2elib import (
    TLM_TOPIC,
    InputPump,
    System,
    UdpRecorder,
    WsClient,
    eff_drive,
    eff_is_stopped,
    eff_state,
    get_status,
    now_ms,
    quest_input,
    s3_up,
    wait_status,
    wait_udp,
)

# Criteria taken from the requirements / ST items.
LINK_LOSS_STOP_S = 1.5  # REQ-0010 / ST-0008(a)
INPUT_LOSS_STOP_S = 0.5  # ST-0010
RECOVERY_S = 15.0  # ST-0011
DOWNSTREAM_GAP_S = 0.2  # DD-0007 I/F contract: receiver stops after 200 ms silence


def running_forward(env: dict[str, Any] | None) -> bool:
    v, _ = eff_drive(env)
    return eff_state(env) == "RUN" and v > 0.5


async def start_driving(system: System, udp: UdpRecorder) -> tuple[WsClient, InputPump]:
    """Connect as quest, hold the deadman and push the left stick fully forward."""
    await wait_status(system.base, s3_up, timeout=10)
    quest = await WsClient(system.ws_url, "quest").connect()
    pump = InputPump(quest, quest_input(deadman=True, ly=-1.0)).start()
    await wait_udp(udp, running_forward, timeout=3)
    return quest, pump


@pytest.mark.verifies("REQ-0006", spec="ST-0006")
async def test_quest_input_becomes_high_level_commands_on_udp_out(
    system: System, udp_out: UdpRecorder
) -> None:
    """Quest controller input reaches the car as drive/arm/stage commands (DD-0004 mapping)."""
    await wait_status(system.base, s3_up, timeout=10)
    quest = await WsClient(system.ws_url, "quest").connect()
    try:
        # Drive: left stick up (y < 0) = forward, left stick left (x < 0) = turn left (w > 0).
        pump = InputPump(quest, quest_input(deadman=True, lx=-0.7, ly=-0.7)).start()
        _, env = await wait_udp(
            udp_out,
            lambda e: eff_state(e) == "RUN" and eff_drive(e)[0] > 0.3 and eff_drive(e)[1] > 0.3,
            timeout=3,
        )
        assert env is not None and env["topic"] == "out/effective"
        v, w = eff_drive(env)
        assert v == pytest.approx(w, abs=0.05)
        assert math.hypot(v, w) <= 1.0 + 1e-6
        await pump.stop()

        # Arm clutch: grip pressed with a pose -> enable; relative motion from clutch start.
        pose0 = {"p": [0.0, 1.0, -0.3], "q": [0.0, 0.0, 0.0, 1.0]}
        pump = InputPump(
            quest, quest_input(deadman=True, right_grip=1.0, right_pose=pose0, trigger=0.5)
        ).start()
        _, env = await wait_udp(
            udp_out, lambda e: (e or {}).get("payload", {}).get("arm", {}).get("enable"), 3
        )
        clutch = env["payload"]["arm"]["clutch_id"]
        await pump.stop()
        pose1 = {"p": [0.1, 1.0, -0.3], "q": [0.0, 0.0, 0.0, 1.0]}
        pump = InputPump(
            quest, quest_input(deadman=True, right_grip=1.0, right_pose=pose1, trigger=0.5)
        ).start()
        _, env = await wait_udp(
            udp_out,
            lambda e: (
                abs((e or {}).get("payload", {}).get("arm", {}).get("p", [0])[0] - 0.1) < 1e-3
            ),
            timeout=3,
        )
        arm = env["payload"]["arm"]
        assert arm["enable"] is True
        assert arm["clutch_id"] == clutch
        assert arm["p"] == pytest.approx([0.1, 0.0, 0.0], abs=1e-3)
        assert arm["grip"] == pytest.approx(0.5, abs=1e-3)
        await pump.stop()

        # Stage: A -> x = +1, right stick up -> z > 0.
        pump = InputPump(quest, quest_input(deadman=True, a=True, ry=-1.0)).start()
        _, env = await wait_udp(
            udp_out,
            lambda e: (e or {}).get("payload", {}).get("stage", {}).get("x") == 1.0,
            timeout=3,
        )
        assert env["payload"]["stage"]["z"] > 0.5
        assert env["payload"]["arm"]["enable"] is False
        await pump.stop()

        # Releasing everything (grip off) -> stop values / enable=false (ST-0006).
        pump = InputPump(quest, quest_input(deadman=False)).start()
        await wait_udp(udp_out, lambda e: eff_state(e) == "RUN" and eff_is_stopped(e), 3)
        await pump.stop()
    finally:
        await quest.close()


@pytest.mark.verifies("REQ-0012", spec="ST-0010")
async def test_deadman_release_stops_drive(system: System, udp_out: UdpRecorder) -> None:
    """Releasing the deadman (left grip) makes the effective drive 0 within 0.5 s."""
    quest, pump = await start_driving(system, udp_out)
    try:
        pump.payload = quest_input(deadman=False, ly=-1.0)
        t_release = time.monotonic()
        t, _ = await wait_udp(
            udp_out, lambda e: eff_drive(e) == (0.0, 0.0), timeout=2, since=t_release
        )
        assert t - t_release <= INPUT_LOSS_STOP_S, f"drive stopped after {t - t_release:.3f}s"
    finally:
        await pump.stop()
        await quest.close()


@pytest.mark.verifies("REQ-0012", spec="ST-0010")
async def test_input_loss_stops_drive(system: System, udp_out: UdpRecorder) -> None:
    """When Quest input stops arriving (XR session ended), the drive stops within 0.5 s."""
    quest, pump = await start_driving(system, udp_out)
    try:
        await pump.stop()
        t_loss = time.monotonic()
        t, env = await wait_udp(
            udp_out, lambda e: eff_drive(e) == (0.0, 0.0), timeout=2, since=t_loss
        )
        assert t - t_loss <= INPUT_LOSS_STOP_S, f"drive stopped after {t - t_loss:.3f}s"
        # The stop comes from the hub (stop command), the link itself stays up.
        st = await get_status(system.base)
        assert st["control"]["car_state"] == "RUN"
        assert s3_up(st)
    finally:
        await quest.close()


async def _estop_latch_cycle(system: System, udp: UdpRecorder, issuer: WsClient) -> None:
    await issuer.send_env("in/estop", {"reason": "e2e"})
    t_estop = time.monotonic()
    await wait_udp(udp, lambda e: eff_state(e) == "ESTOP", timeout=2, since=t_estop)
    st = await get_status(system.base)
    assert st["control"]["latched"] is True
    assert st["control"]["car_state"] == "ESTOP"


@pytest.mark.verifies("REQ-0011", spec="ST-0009")
async def test_estop_latches_until_booth_release(system: System, udp_out: UdpRecorder) -> None:
    """E-STOP from Quest or booth latches; only the booth release brings motion back."""
    quest, pump = await start_driving(system, udp_out)
    booth = await WsClient(system.ws_url, "booth").connect()
    try:
        for issuer in (quest, booth):
            await _estop_latch_cycle(system, udp_out, issuer)

            # Motion input keeps arriving but every effective command is stop.
            t0 = time.monotonic()
            await asyncio.sleep(1.0)
            window = udp_out.snapshot(t0)
            assert window, "UDP out went silent during ESTOP"
            assert all(eff_state(e) == "ESTOP" and eff_is_stopped(e) for _, e in window)

            # Release attempt from Quest is ignored.
            await quest.send_env("in/estop_release", {})
            t1 = time.monotonic()
            await asyncio.sleep(1.0)
            window = udp_out.snapshot(t1)
            assert all(eff_state(e) == "ESTOP" and eff_is_stopped(e) for _, e in window)
            assert (await get_status(system.base))["control"]["latched"] is True

            # Explicit release from the booth -> motion resumes with the live input.
            await booth.send_env("in/estop_release", {})
            t2 = time.monotonic()
            await wait_udp(udp_out, lambda e: eff_state(e) != "ESTOP", timeout=2, since=t2)
            await wait_udp(udp_out, running_forward, timeout=3, since=t2)
            assert (await get_status(system.base))["control"]["latched"] is False
    finally:
        await pump.stop()
        await quest.close()
        await booth.close()


@pytest.mark.verifies("REQ-0010", spec="ST-0008")
async def test_frozen_hub_stops_car_within_1500ms(system: System, udp_out: UdpRecorder) -> None:
    """Silent loss of the hub -> car link (hub frozen, TCP left open) stops the car in 1.5 s."""
    quest, pump = await start_driving(system, udp_out)
    assert system.hub is not None
    try:
        system.hub.signal(signal.SIGSTOP)
        t_loss = time.monotonic()
        try:
            t_zero, _ = await wait_udp(
                udp_out, lambda e: eff_is_stopped(e), timeout=3, since=t_loss
            )
            t_stop, _ = await wait_udp(
                udp_out,
                lambda e: eff_state(e) == "STOP" and eff_is_stopped(e),
                timeout=3,
                since=t_loss,
            )
            # Datagrams keep coming while the link is down (fixed-period output).
            await asyncio.sleep(0.5)
            gaps = _gaps(udp_out.snapshot(t_loss))
        finally:
            system.hub.signal(signal.SIGCONT)
        assert t_zero - t_loss <= LINK_LOSS_STOP_S, f"stop values after {t_zero - t_loss:.3f}s"
        assert t_stop - t_loss <= LINK_LOSS_STOP_S, f"state STOP after {t_stop - t_loss:.3f}s"
        assert max(gaps) < DOWNSTREAM_GAP_S
    finally:
        await pump.stop()
        await quest.close()


@pytest.mark.verifies("REQ-0010", spec="ST-0008")
async def test_crashed_hub_stops_car_within_1500ms(system: System, udp_out: UdpRecorder) -> None:
    """A crashed hub (process killed) stops the car's effective command within 1.5 s."""
    quest, pump = await start_driving(system, udp_out)
    assert system.hub is not None
    try:
        system.hub.kill_hard()
        t_loss = time.monotonic()
        t_stop, _ = await wait_udp(
            udp_out,
            lambda e: eff_state(e) != "RUN" and eff_is_stopped(e),
            timeout=3,
            since=t_loss,
        )
        assert t_stop - t_loss <= LINK_LOSS_STOP_S, f"stopped after {t_stop - t_loss:.3f}s"
    finally:
        await pump.stop()
        await quest.close()


@pytest.mark.verifies("REQ-0018", spec="ST-0011")
async def test_hub_restart_recovers_without_touching_car(
    system: System, udp_out: UdpRecorder
) -> None:
    """After a hub restart, car_ctrl re-establishes S3 by itself and commands flow again."""
    quest, pump = await start_driving(system, udp_out)
    car_pid = system.car.pid if system.car else None
    await pump.stop()
    await quest.close()
    assert system.hub is not None
    system.hub.kill_hard()
    await wait_udp(udp_out, lambda e: eff_state(e) != "RUN", timeout=3)

    t_restart = time.monotonic()
    system.start_hub()
    await wait_status(system.base, s3_up, timeout=RECOVERY_S)
    # The quest page reconnects on its own; this client stands in for it.
    quest = await WsClient(system.ws_url, "quest").connect()
    pump = InputPump(quest, quest_input(deadman=True, ly=-1.0)).start()
    try:
        t_ok, _ = await wait_udp(udp_out, running_forward, timeout=RECOVERY_S, since=t_restart)
        assert t_ok - t_restart <= RECOVERY_S
        assert system.car is not None and system.car.alive() and system.car.pid == car_pid
        st = await get_status(system.base)
        assert st["roles"]["car_ctrl"] is True
        assert st["control"]["car_state"] == "RUN"
    finally:
        await pump.stop()
        await quest.close()


@pytest.mark.verifies("REQ-0018", spec="ST-0011")
async def test_car_ctrl_restart_recovers_without_touching_hub(
    system: System, udp_out: UdpRecorder
) -> None:
    """After car_ctrl restarts, S3 and command delivery come back; hub and quest untouched."""
    quest, pump = await start_driving(system, udp_out)
    hub_pid = system.hub.pid if system.hub else None
    try:
        assert system.car is not None
        system.car.kill_hard()
        await wait_status(system.base, lambda s: s["roles"]["car_ctrl"] is False, timeout=5)
        t_restart = time.monotonic()
        system.start_car()
        t_ok, _ = await wait_udp(udp_out, running_forward, timeout=RECOVERY_S, since=t_restart)
        assert t_ok - t_restart <= RECOVERY_S
        st = await get_status(system.base)
        assert s3_up(st) and st["control"]["car_state"] == "RUN"
        assert system.hub is not None and system.hub.alive() and system.hub.pid == hub_pid
        assert not quest.closed, "quest connection was dropped by the car restart"
    finally:
        await pump.stop()
        await quest.close()


def _gaps(records: list[tuple[float, Any]]) -> list[float]:
    ts = [t for t, _ in records]
    return [b - a for a, b in zip(ts, ts[1:], strict=False)] or [0.0]


@pytest.mark.verifies("REQ-0016", spec="ST-0013")
async def test_udp_out_is_periodic_safety_judged_output(
    system: System, udp_out: UdpRecorder
) -> None:
    """UDP out on localhost carries the safety-judged command at a fixed period, in any state."""
    quest, pump = await start_driving(system, udp_out)
    try:
        t0 = time.monotonic()
        await asyncio.sleep(3.0)
        window = udp_out.snapshot(t0)
        rate = len(window) / 3.0
        gaps = _gaps(window)
        assert 15 <= rate <= 25, f"UDP out rate {rate:.1f} Hz (expected ~20 Hz)"
        assert max(gaps) < DOWNSTREAM_GAP_S, f"max gap {max(gaps):.3f}s"
        for _, env in window:
            assert env is not None
            assert env["topic"] == "out/effective" and env["src"] == "car_ctrl"
            p = env["payload"]
            assert set(p) >= {"state", "drive", "arm", "stage"}
        seqs = [e["seq"] for _, e in window if e]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)

        # Output continues with stop values while the control link is gone.
        assert system.hub is not None
        system.hub.kill_hard()
        await asyncio.sleep(0.6)
        t1 = time.monotonic()
        await asyncio.sleep(2.0)
        window = udp_out.snapshot(t1)
        assert len(window) / 2.0 >= 15
        assert max(_gaps(window)) < DOWNSTREAM_GAP_S
        assert all(eff_state(e) != "RUN" and eff_is_stopped(e) for _, e in window)
    finally:
        await pump.stop()
        await quest.close()


def _send_udp_in(system: System, data: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(data, ("127.0.0.1", system.udp_in))


def _tlm_env(topic: str, seq: int, payload: dict[str, Any]) -> bytes:
    env = {"topic": topic, "ver": 1, "seq": seq, "ts": now_ms(), "src": "car_local"}
    env["payload"] = payload
    return json.dumps(env).encode()


@pytest.mark.verifies("REQ-0014", spec="ST-0013")
async def test_local_telemetry_reaches_operator_side(system: System, udp_out: UdpRecorder) -> None:
    """A registered telemetry envelope thrown into UDP in reaches /status, quest and booth."""
    await wait_status(system.base, s3_up, timeout=10)
    quest = await WsClient(system.ws_url, "quest").connect()
    booth = await WsClient(system.ws_url, "booth").connect()
    try:
        for i in range(1, 6):
            _send_udp_in(system, _tlm_env(TLM_TOPIC, i, {"value": 12.5 + i}))
            await asyncio.sleep(0.2)
        st = await wait_status(
            system.base,
            lambda s: s.get("telemetry", {}).get(TLM_TOPIC) == {"value": 17.5},
            timeout=3,
        )
        assert st["telemetry"][TLM_TOPIC] == {"value": 17.5}
        for client in (quest, booth):
            deadline = time.monotonic() + 3
            while not client.envs(TLM_TOPIC) and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            got = client.envs(TLM_TOPIC)
            assert got, f"{client.role} did not receive {TLM_TOPIC}"
            assert got[-1]["payload"] == {"value": 17.5}
    finally:
        await quest.close()
        await booth.close()


@pytest.mark.verifies("REQ-0013", spec="ST-0013")
async def test_registered_topic_passes_unregistered_is_ignored(
    system: System, udp_out: UdpRecorder
) -> None:
    """A topic added by one registry entry flows; unknown topics are dropped without harm."""
    quest, pump = await start_driving(system, udp_out)
    booth = await WsClient(system.ws_url, "booth").connect()
    try:
        # The extension topic (added by one registry entry, here via --extra-topic on both
        # hub and car) is advertised to the browsers.
        names = [t["name"] for t in booth.welcome["topics"]["topics"]]  # type: ignore[index]
        assert TLM_TOPIC in names

        t0 = time.monotonic()
        for i in range(1, 4):
            _send_udp_in(system, _tlm_env("tlm/unknown", i, {"value": i}))
            _send_udp_in(system, b"{not json")
            await asyncio.sleep(0.1)
        _send_udp_in(system, _tlm_env(TLM_TOPIC, 100, {"value": 42}))

        # The registered topic still flows after the junk.
        await wait_status(
            system.base, lambda s: s.get("telemetry", {}).get(TLM_TOPIC) == {"value": 42}, 3
        )
        # ST-0013: the unregistered topic is counted as dropped and never forwarded.
        st = await wait_status(
            system.base, lambda s: s.get("dropped", {}).get("tlm/unknown", 0) >= 3, timeout=5
        )
        assert "tlm/unknown" not in st.get("telemetry", {})
        assert not quest.envs("tlm/unknown") and not booth.envs("tlm/unknown")

        # Control was not disturbed while junk arrived.
        window = udp_out.snapshot(t0)
        assert window and all(running_forward(e) for _, e in window)
        assert max(_gaps(window)) < DOWNSTREAM_GAP_S
        assert s3_up(st) and st["control"]["car_state"] == "RUN"
    finally:
        await pump.stop()
        await quest.close()
        await booth.close()


@pytest.mark.verifies("REQ-0013", spec="ST-0013")
async def test_unregistered_topic_from_browser_is_ignored(
    system: System, udp_out: UdpRecorder
) -> None:
    """An unregistered topic sent by a page is ignored by the hub without side effects.

    The car-side drop count must stay visible in /status: the hub adds the car's counts
    to its /status ``dropped`` (DD-0002 "合算"), so the total can only grow.
    """
    quest, pump = await start_driving(system, udp_out)
    booth = await WsClient(system.ws_url, "booth").connect()
    try:
        for i in range(1, 4):
            _send_udp_in(system, _tlm_env("tlm/unknown", i, {"value": i}))
            await asyncio.sleep(0.1)
        await wait_status(
            system.base, lambda s: s.get("dropped", {}).get("tlm/unknown", 0) >= 3, timeout=5
        )

        t0 = time.monotonic()
        await booth.send_env("tlm/unknown", {"value": 1})
        await quest.send_env("tlm/unknown", {"value": 1})
        await asyncio.sleep(2.5)  # > one sys/state period, so /status is refreshed

        assert not booth.closed and not quest.closed
        assert not quest.envs("tlm/unknown") and not booth.envs("tlm/unknown")
        window = udp_out.snapshot(t0)
        assert window and all(running_forward(e) for _, e in window)
        st = await get_status(system.base)
        assert "tlm/unknown" not in st.get("telemetry", {})
        dropped = st.get("dropped", {}).get("tlm/unknown", 0)
        assert dropped >= 3, f"car-side drop count lost from /status: dropped={st['dropped']}"
    finally:
        await pump.stop()
        await quest.close()
        await booth.close()
