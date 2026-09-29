import pytest

from nasura_comm.control import ControlCore
from nasura_comm.envelope import make
from nasura_comm.mapping import Mapper

pytestmark = pytest.mark.verifies("DD-0005", spec="UT-0007")


def quest_input(v_stick=-1.0, deadman=True):
    return {
        "left": {
            "axes": [0.0, v_stick],
            "trigger": 0.0,
            "grip": 1.0 if deadman else 0.0,
            "x": False,
            "y": False,
            "thumb": False,
            "pose": None,
        },
        "right": {
            "axes": [0.0, 0.0],
            "trigger": 0.0,
            "grip": 0.0,
            "a": False,
            "b": False,
            "thumb": False,
            "pose": None,
        },
    }


def env_in(topic, payload, src="quest", seq=0):
    return make(topic, payload, src, seq, 0)


def by_topic(envs, topic):
    return [e for e in envs if e["topic"] == topic]


def is_stop(envs):
    d = by_topic(envs, "cmd/drive")[-1]["payload"]
    a = by_topic(envs, "cmd/arm")[-1]["payload"]
    s = by_topic(envs, "cmd/stage")[-1]["payload"]
    return (
        d["v"] == 0
        and d["w"] == 0
        and d["deadman"] is False
        and a["enable"] is False
        and s["x"] == 0
        and s["z"] == 0
    )


def test_no_input_gives_stop_and_heartbeat():
    core = ControlCore(Mapper())
    out = core.tick(0)
    assert by_topic(out, "sys/heartbeat")
    assert is_stop(out)


def test_input_timeout():
    core = ControlCore(Mapper())
    core.on_input(env_in("in/quest", quest_input()), 0)
    out = core.tick(200)
    assert by_topic(out, "cmd/drive")[-1]["payload"]["v"] == pytest.approx(1.0)
    out = core.tick(301)
    assert is_stop(out)


def test_periods():
    core = ControlCore(Mapper())
    out = []
    for t in range(0, 1001):
        out += core.tick(t)
    assert abs(len(by_topic(out, "sys/heartbeat")) - 10) <= 1
    for topic in ("cmd/drive", "cmd/arm", "cmd/stage"):
        assert abs(len(by_topic(out, topic)) - 30) <= 1


def test_heartbeat_payload_and_seq():
    core = ControlCore(Mapper())
    hbs = []
    for t in range(0, 301):
        hbs += by_topic(core.tick(t), "sys/heartbeat")
    assert [h["payload"]["hb"] for h in hbs] == sorted({h["payload"]["hb"] for h in hbs})
    assert hbs[1]["payload"]["t_hub"] == 100
    assert hbs[1]["seq"] > hbs[0]["seq"]
    assert all(h["src"] == "hub" for h in hbs)


def test_estop_latch():
    core = ControlCore(Mapper())
    core.on_input(env_in("in/quest", quest_input()), 0)
    out = core.on_input(env_in("in/estop", {"reason": "test"}), 1)
    assert by_topic(out, "sys/estop")
    assert core.latched is True
    core.on_input(env_in("in/quest", quest_input()), 10)
    assert is_stop(core.tick(20))


def test_release_only_from_booth():
    core = ControlCore(Mapper())
    core.on_input(env_in("in/estop", {}), 0)
    out = core.on_input(env_in("in/estop_release", {}, src="quest"), 1)
    assert not by_topic(out, "sys/estop_release")
    assert core.latched is True
    out = core.on_input(env_in("in/estop_release", {}, src="booth"), 2)
    assert by_topic(out, "sys/estop_release")
    assert core.latched is False
    core.on_input(env_in("in/quest", quest_input()), 3)
    out = core.tick(10)
    assert by_topic(out, "cmd/drive")[-1]["payload"]["v"] == pytest.approx(1.0)


def test_rtt():
    core = ControlCore(Mapper())
    core.on_car(
        make("sys/heartbeat_ack", {"hb": 1, "t_hub": 1000, "state": "RUN"}, "car_ctrl", 0, 0), 1040
    )
    assert core.rtt_ms == 40
