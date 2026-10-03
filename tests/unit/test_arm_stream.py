import json
import math
from pathlib import Path

import pytest

from nasura_comm import arm_stream as a

pytestmark = pytest.mark.impl_aware()

RULE = """SUBSYSTEM=="tty", ENV{ID_SERIAL_SHORT}=="5B79049673", SYMLINK+="left_leader"
SUBSYSTEM=="tty", ENV{ID_SERIAL_SHORT}=="5B79050494", SYMLINK+="left_follower"

SUBSYSTEM=="tty", ENV{ID_SERIAL_SHORT}=="5B79050171", SYMLINK+="right_leader"
SUBSYSTEM=="tty", ENV{ID_SERIAL_SHORT}=="5B79050711", SYMLINK+="right_follower"
"""

ACTION = {f"{j}.pos": float(i) for i, j in enumerate(a.JOINTS)}


def frame(side: str = "left", sid: str = "s1", seq: int = 0) -> a.Frame:
    f = a.decode_frame(a.encode_frame(side, sid, seq, 1000, ACTION))
    assert f is not None
    return f


def make_hw(tmp_path: Path) -> Path:
    (tmp_path / a.UDEV_RULE).parent.mkdir(parents=True)
    (tmp_path / a.UDEV_RULE).write_text(RULE, encoding="utf-8")
    for side in a.SIDES:
        for role in ("leader", "follower"):
            p = a.calibration_file(tmp_path, side, role)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
    return tmp_path


def test_parse_udev_serials() -> None:
    assert a.parse_udev_serials(RULE) == {
        "left_leader": "5B79049673",
        "left_follower": "5B79050494",
        "right_leader": "5B79050171",
        "right_follower": "5B79050711",
    }


def test_calibration_file_paths() -> None:
    hw = Path("hw")
    root = hw / "so101/calibration"
    left = a.calibration_file(hw, "left", "leader")
    right = a.calibration_file(hw, "right", "follower")
    assert left == root / "teleoperators/so_leader/left_leader.json"
    assert right == root / "robots/so_follower/right_follower.json"


def test_device_id_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        a.device_id("center", "leader")


def test_check_hardware_dir_ok(tmp_path: Path) -> None:
    hw = make_hw(tmp_path)
    assert a.check_hardware_dir(hw, a.HARDWARE_COMMIT, "right", "follower") == []


def test_check_hardware_dir_reports_commit_and_missing_calibration(tmp_path: Path) -> None:
    hw = make_hw(tmp_path)
    a.calibration_file(hw, "left", "leader").unlink()
    errors = a.check_hardware_dir(hw, "deadbeef", "left", "leader")
    assert len(errors) == 2
    assert "deadbeef" in errors[0] and "calibration missing" in errors[1]


@pytest.mark.parametrize("value", [0, -1, 5.01, math.nan, math.inf, "5", True, None])
def test_max_relative_target_rejects(value: object) -> None:
    assert a.check_max_relative_target(value) is not None


@pytest.mark.parametrize("value", [0.5, 5, 5.0])
def test_max_relative_target_accepts(value: float) -> None:
    assert a.check_max_relative_target(value) is None


def test_roundtrip() -> None:
    f = frame("right", "abc", 7)
    assert (f.side, f.session, f.seq, f.ts_ms) == ("right", "abc", 7, 1000)
    assert f.action() == ACTION


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update(v=2),
        lambda m: m.update(side="center"),
        lambda m: m.update(sid=""),
        lambda m: m.update(seq=-1),
        lambda m: m.update(seq=True),
        lambda m: m.update(ts="x"),
        lambda m: m["pos"].pop("gripper"),
        lambda m: m["pos"].update(extra=1.0),
        lambda m: m["pos"].update(gripper="1"),
    ],
)
def test_decode_rejects(mutate) -> None:  # type: ignore[no-untyped-def]
    msg = json.loads(a.encode_frame("left", "s", 0, 0, ACTION))
    mutate(msg)
    assert a.decode_frame(json.dumps(msg).encode()) is None


def test_decode_rejects_garbage_and_nan() -> None:
    assert a.decode_frame(b"\xff\x00") is None
    assert a.decode_frame(b"[]") is None
    msg = json.loads(a.encode_frame("left", "s", 0, 0, ACTION))
    msg["pos"]["gripper"] = float("nan")
    assert a.decode_frame(json.dumps(msg).encode()) is None


def test_gate_rejects_other_side() -> None:
    g = a.FrameGate("left", 500)
    assert not g.offer(frame("right"), 0)
    assert g.latest is None and not g.fresh(0)


def test_gate_orders_within_session_and_resets_on_new_session() -> None:
    g = a.FrameGate("left", 500)
    assert g.offer(frame(seq=5), 0)
    assert not g.offer(frame(seq=5), 1)
    assert not g.offer(frame(seq=3), 2)
    assert g.offer(frame(seq=6), 3)
    assert g.offer(frame(sid="s2", seq=0), 4)  # sender restarted
    assert g.latest is not None and g.latest.session == "s2"


def test_gate_freshness() -> None:
    g = a.FrameGate("left", 500)
    assert not g.fresh(0)
    g.offer(frame(), 1000)
    assert g.fresh(1500)
    assert not g.fresh(1501)
