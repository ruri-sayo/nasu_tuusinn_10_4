import json

import pytest
from nasura_comm.local_io import TelemetryGate, build_effective, stop_effective
from nasura_comm.topics import Registry, TopicSpec

from nasura_comm import envelope


def _eff(v=0.25):
    return {
        "drive": {"v": v, "w": 0.0},
        "arm": {"enable": True, "clutch_id": 3, "p": [0.1, 0, 0], "q": [0, 0, 0, 1], "grip": 0.5},
        "stage": {"x": 1.0, "z": 0.0},
    }


@pytest.mark.verifies("DD-0007", spec="UT-0010")
def test_build_effective_shape():
    env = build_effective("RUN", _eff(), 42, 1790000000000)
    assert env["topic"] == "out/effective"
    assert env["src"] == "car_ctrl"
    assert env["seq"] == 42
    p = env["payload"]
    assert set(p) == {"state", "drive", "arm", "stage"}
    assert p["state"] == "RUN"
    assert p["drive"] == {"v": 0.25, "w": 0.0}
    assert envelope.decode(envelope.encode(env)) is not None


@pytest.mark.verifies("DD-0007", spec="UT-0010")
def test_stop_values():
    p = build_effective("STOP", stop_effective(), 0, 0)["payload"]
    assert p["drive"] == {"v": 0.0, "w": 0.0}
    assert p["arm"]["enable"] is False
    assert p["stage"] == {"x": 0.0, "z": 0.0}


def _gate():
    reg = Registry(
        [
            TopicSpec("tlm/test_value", "up", "ctrl", 5.0, fixed=False),
            TopicSpec("tlm/test_rel", "up", "rel", None, fixed=False),
            TopicSpec("tlm/down_only", "down", "ctrl", None, fixed=False),
        ]
    )
    return TelemetryGate(reg)


def _dgram(topic, src="sensor", seq=0):
    return envelope.encode(envelope.make(topic, {"value": 1}, src, seq, 0)).encode()


@pytest.mark.verifies("DD-0007", spec="UT-0011")
def test_invalid_json():
    g = _gate()
    assert g.check(b"{bad", 0) is None
    assert g.dropped["invalid"] == 1


@pytest.mark.verifies("DD-0007", spec="UT-0011")
def test_unregistered():
    g = _gate()
    assert g.check(_dgram("tlm/unknown"), 0) is None
    assert g.dropped["tlm/unknown"] == 1


@pytest.mark.verifies("DD-0007", spec="UT-0011")
@pytest.mark.parametrize("topic", ["cmd/drive", "sys/state", "tlm/down_only"])
def test_fixed_or_down(topic):
    g = _gate()
    assert g.check(_dgram(topic), 0) is None
    assert g.dropped[topic] == 1


@pytest.mark.verifies("DD-0007", spec="UT-0011")
def test_forward_registered():
    g = _gate()
    res = g.check(_dgram("tlm/test_value", src="sensor"), 0)
    assert res is not None
    channel, env = res
    assert channel == "ctrl"
    assert env["src"] == "car_local"
    assert env["topic"] == "tlm/test_value"
    channel, _ = g.check(_dgram("tlm/test_rel"), 0)
    assert channel == "rel"


@pytest.mark.verifies("DD-0007", spec="UT-0011")
def test_rate_limited():
    g = _gate()
    assert g.check(_dgram("tlm/test_value", seq=1), 0) is not None
    assert g.check(_dgram("tlm/test_value", seq=2), 100) is None
    assert g.dropped["rate:tlm/test_value"] == 1
    assert g.check(_dgram("tlm/test_value", seq=3), 200) is not None


def test_dgram_helper_is_json():
    json.loads(_dgram("tlm/x"))
