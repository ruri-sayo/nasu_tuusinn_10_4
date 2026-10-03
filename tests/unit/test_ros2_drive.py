"""Specification-derived tests for the ROS 2 drive adapter."""

from __future__ import annotations

import math

import pytest

from nasura_comm.envelope import encode, make
from nasura_comm.ros2_drive import DriveInputState, EffectiveDrive, decode_effective, to_joy_axes


def _data(
    *,
    state: str = "RUN",
    v: object = 0.6,
    w: object = -0.25,
    seq: int = 1,
    topic: str = "out/effective",
    src: str = "car_ctrl",
    ver: int = 1,
) -> bytes:
    env = make(
        topic,
        {"state": state, "drive": {"v": v, "w": w}, "stage": {"x": 0.0, "z": 0.0}},
        src,
        seq,
        1_790_000_000_000,
        ver,
    )
    return encode(env).encode()


@pytest.mark.verifies("DD-0017")
@pytest.mark.verifies("MD-0001")
def test_decode_effective_contract() -> None:
    assert decode_effective(_data()) == EffectiveDrive("RUN", 0.6, -0.25, 1)

    invalid = [
        b"not-json",
        _data(topic="cmd/drive"),
        _data(src="other"),
        _data(ver=2),
        _data(state="UNKNOWN"),
        _data(v=True),
        _data(v=1.01),
        _data(w=math.inf),
    ]
    assert all(decode_effective(data) is None for data in invalid)


@pytest.mark.verifies("DD-0018")
@pytest.mark.verifies("MD-0001")
def test_run_command_maps_to_joy_axes() -> None:
    assert to_joy_axes(EffectiveDrive("RUN", 0.6, -0.25, 1)) == (-0.25, 0.6)


@pytest.mark.verifies("DD-0018")
@pytest.mark.verifies("MD-0001")
@pytest.mark.parametrize("state", ["INIT", "STOP", "ESTOP"])
def test_non_run_state_maps_to_neutral(state: str) -> None:
    assert to_joy_axes(EffectiveDrive(state, 0.8, -0.7, 1)) == (0.0, 0.0)


@pytest.mark.verifies("DD-0017")
@pytest.mark.verifies("DD-0019")
@pytest.mark.verifies("MD-0001")
def test_timeout_rejects_stale_sequence_and_accepts_new_generation() -> None:
    state = DriveInputState(timeout_ms=200)
    assert state.axes(0) == (0.0, 0.0)
    assert state.accept(_data(seq=50), 10)
    assert state.axes(10) == (-0.25, 0.6)
    assert not state.accept(_data(seq=50), 50)
    assert state.axes(209) == (-0.25, 0.6)
    assert state.axes(210) == (0.0, 0.0)
    assert state.accept(_data(seq=0), 211)
    assert state.axes(211) == (-0.25, 0.6)


@pytest.mark.verifies("DD-0017")
@pytest.mark.verifies("DD-0019")
@pytest.mark.verifies("MD-0001")
def test_invalid_input_does_not_refresh_watchdog() -> None:
    state = DriveInputState(timeout_ms=200)
    assert state.accept(_data(), 0)
    assert not state.accept(b"invalid", 150)
    assert state.axes(200) == (0.0, 0.0)


@pytest.mark.verifies("DD-0020")
@pytest.mark.verifies("MD-0001")
def test_publisher_conflict_latches_neutral() -> None:
    state = DriveInputState(timeout_ms=200)
    assert state.accept(_data(), 0)
    state.latch_conflict()
    assert state.axes(1) == (0.0, 0.0)
    assert state.accept(_data(seq=2), 2)
    assert state.axes(2) == (0.0, 0.0)


@pytest.mark.verifies("DD-0022")
@pytest.mark.verifies("MD-0001")
def test_status_transition_is_reported_once() -> None:
    state = DriveInputState(timeout_ms=200)
    assert state.transition(0) == "waiting"
    assert state.transition(1) is None
    assert state.accept(_data(), 2)
    assert state.transition(2) == "active"
    assert state.transition(3) is None
    assert state.transition(202) == "timeout"
    assert state.transition(203) is None
