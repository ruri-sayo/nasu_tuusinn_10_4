import math

import pytest

from nasura_comm.mapping import Mapper


def hand(**kw):
    base = {
        "axes": [0.0, 0.0],
        "trigger": 0.0,
        "grip": 0.0,
        "thumb": False,
        "pose": None,
    }
    base.update(kw)
    return base


def inp(left=None, right=None):
    left_h = hand(x=False, y=False)
    right_h = hand(a=False, b=False)
    left_h.update(left or {})
    right_h.update(right or {})
    return {"left": left_h, "right": right_h}


def pose(p=(0.0, 0.0, 0.0), q=(0.0, 0.0, 0.0, 1.0)):
    return {"p": list(p), "q": list(q)}


def approx_list(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def q_equiv(a, b, tol=1e-6):
    return approx_list(a, b, tol) or approx_list(a, [-x for x in b], tol)


# --- UT-0005 -------------------------------------------------------------


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_deadman_released():
    drive, _arm, stage = Mapper().map(
        inp(left={"grip": 0.4, "axes": [0.0, -1.0]}, right={"a": True, "axes": [0, -1]})
    )
    assert drive["v"] == 0 and drive["w"] == 0
    assert drive["deadman"] is False
    assert stage["x"] == 0 and stage["z"] == 0


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_deadman_held():
    drive, _arm, _stage = Mapper().map(inp(left={"grip": 0.6, "axes": [0.0, -1.0]}))
    assert drive["deadman"] is True
    assert drive["v"] == pytest.approx(1.0)


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_deadzone_and_directions():
    m = Mapper()
    d, _, _ = m.map(inp(left={"grip": 1.0, "axes": [0.0, -0.1]}))
    assert d["v"] == 0 and d["w"] == 0
    d, _, _ = m.map(inp(left={"grip": 1.0, "axes": [0.0, -1.0]}))
    assert d["v"] == pytest.approx(1.0)
    d, _, _ = m.map(inp(left={"grip": 1.0, "axes": [1.0, 0.0]}))
    assert d["w"] == pytest.approx(-1.0)


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_rescale_monotonic():
    m = Mapper()
    values = []
    for i in range(0, 101):
        mag = 0.15 + 0.85 * i / 100
        d, _, _ = m.map(inp(left={"grip": 1.0, "axes": [0.0, -mag]}))
        values.append(d["v"])
    assert values[0] == pytest.approx(0.0, abs=1e-3)
    assert values[1] < 0.05
    assert values[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(values, values[1:], strict=False))


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_stage_buttons():
    m = Mapper()
    _, _, s = m.map(inp(left={"grip": 1.0}, right={"a": True}))
    assert s["x"] == 1
    _, _, s = m.map(inp(left={"grip": 1.0}, right={"b": True}))
    assert s["x"] == -1
    _, _, s = m.map(inp(left={"grip": 1.0}, right={"a": True, "b": True}))
    assert s["x"] == 0
    _, _, s = m.map(inp(left={"grip": 1.0}, right={"axes": [0.0, -1.0]}))
    assert s["z"] == pytest.approx(1.0)


# --- UT-0006 -------------------------------------------------------------


@pytest.mark.verifies("DD-0004", spec="UT-0006")
def test_clutch_rising_edge():
    m = Mapper()
    _, arm, _ = m.map(inp())
    cid0 = arm["clutch_id"]
    _, arm, _ = m.map(
        inp(right={"grip": 1.0, "pose": pose((1, 1, 1), (0, 0.3826834, 0, 0.9238795))})
    )
    assert arm["enable"] is True
    assert arm["clutch_id"] == cid0 + 1
    assert approx_list(arm["p"], [0, 0, 0])
    assert q_equiv(arm["q"], [0, 0, 0, 1])


@pytest.mark.verifies("DD-0004", spec="UT-0006")
def test_clutch_relative_motion():
    m = Mapper()
    m.map(inp(right={"grip": 1.0, "pose": pose((0.2, 1.0, -0.3))}))
    _, arm, _ = m.map(inp(right={"grip": 1.0, "pose": pose((0.3, 1.0, -0.3))}))
    assert approx_list(arm["p"], [0.1, 0, 0])
    s = math.sin(math.pi / 4)
    _, arm, _ = m.map(inp(right={"grip": 1.0, "pose": pose((0.2, 1.0, -0.3), (0, s, 0, s))}))
    assert q_equiv(arm["q"], [0, s, 0, s])


@pytest.mark.verifies("DD-0004", spec="UT-0006")
def test_clutch_release_and_regrip():
    m = Mapper()
    _, arm, _ = m.map(inp(right={"grip": 1.0, "pose": pose()}))
    cid = arm["clutch_id"]
    _, arm, _ = m.map(inp(right={"grip": 0.0, "pose": pose((1, 0, 0))}))
    assert arm["enable"] is False
    assert arm["p"] == [0, 0, 0] and arm["q"] == [0, 0, 0, 1]
    assert arm["clutch_id"] == cid
    _, arm, _ = m.map(inp(right={"grip": 1.0, "pose": pose()}))
    assert arm["clutch_id"] == cid + 1


@pytest.mark.verifies("DD-0004", spec="UT-0006")
def test_no_pose_disables():
    _, arm, _ = Mapper().map(inp(right={"grip": 1.0, "pose": None}))
    assert arm["enable"] is False


@pytest.mark.verifies("DD-0004", spec="UT-0006")
def test_grip_value():
    _, arm, _ = Mapper().map(inp(right={"grip": 1.0, "trigger": 0.7, "pose": pose()}))
    assert arm["grip"] == pytest.approx(0.7)
