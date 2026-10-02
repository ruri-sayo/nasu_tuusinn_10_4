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


# --- UT-0005 -------------------------------------------------------------


@pytest.mark.verifies("DD-0004", spec="UT-0005")
@pytest.mark.parametrize("left_grip", [0.0, 1.0])
def test_output_independent_of_left_grip(left_grip):
    out = Mapper().map(
        inp(
            left={"grip": left_grip, "axes": [0.0, -1.0]},
            right={"a": True, "axes": [0.0, -1.0]},
        )
    )
    assert len(out) == 2
    drive, stage = out
    assert set(drive) == {"v", "w"}
    assert drive["v"] == pytest.approx(1.0)
    assert drive["w"] == pytest.approx(0.0)
    assert set(stage) == {"x", "z"}
    assert stage["x"] == 1
    assert stage["z"] == pytest.approx(1.0)


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_left_grip_does_not_change_output():
    m = Mapper()
    base = {"axes": [0.6, -0.8]}
    right = {"b": True, "axes": [0.0, 0.5]}
    released = m.map(inp(left={**base, "grip": 0.0}, right=right))
    held = m.map(inp(left={**base, "grip": 1.0}, right=right))
    assert released == held
    assert released[0]["v"] > 0 and released[0]["w"] < 0
    assert released[1]["x"] == -1


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_deadzone_and_directions():
    m = Mapper()
    d, _ = m.map(inp(left={"axes": [0.0, -0.1]}))
    assert d["v"] == 0 and d["w"] == 0
    d, _ = m.map(inp(left={"axes": [0.0, -1.0]}))
    assert d["v"] == pytest.approx(1.0)
    d, _ = m.map(inp(left={"axes": [1.0, 0.0]}))
    assert d["w"] == pytest.approx(-1.0)


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_rescale_monotonic():
    m = Mapper()
    values = []
    for i in range(0, 101):
        mag = 0.15 + 0.85 * i / 100
        d, _ = m.map(inp(left={"axes": [0.0, -mag]}))
        values.append(d["v"])
    assert values[0] == pytest.approx(0.0, abs=1e-3)
    assert values[1] < 0.05
    assert values[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(values, values[1:], strict=False))


@pytest.mark.verifies("DD-0004", spec="UT-0005")
def test_stage_buttons():
    m = Mapper()
    _, s = m.map(inp(right={"a": True}))
    assert s["x"] == 1
    _, s = m.map(inp(right={"b": True}))
    assert s["x"] == -1
    _, s = m.map(inp(right={"a": True, "b": True}))
    assert s["x"] == 0
    _, s = m.map(inp(right={"axes": [0.0, -1.0]}))
    assert s["z"] == pytest.approx(1.0)
