import pytest
from nasura_comm.signaling import Close, Internal, Send, SignalRouter

pytestmark = pytest.mark.verifies("DD-0008", spec="UT-0012")


def sends(actions, handle=None, type_=None):
    out = [a for a in actions if isinstance(a, Send)]
    if handle is not None:
        out = [a for a in out if a.handle == handle]
    if type_ is not None:
        out = [a for a in out if a.msg.get("type") == type_]
    return out


def test_s1_restart_when_both_present():
    r = SignalRouter()
    assert not sends(r.on_hello("car_media", "cm"), type_="restart")
    acts = r.on_hello("quest", "q")
    rs = sends(acts, "cm", "restart")
    assert [a.msg["session"] for a in rs] == ["S1"]


def test_s2_and_s3():
    r = SignalRouter()
    r.on_hello("booth", "b")
    acts = r.on_hello("car_media", "cm")
    assert [a.msg["session"] for a in sends(acts, "b", "restart")] == ["S2"]
    acts = r.on_hello("car_ctrl", "cc")
    assert [a.msg["session"] for a in sends(acts, "cc", "restart")] == ["S3"]


def test_signal_forwarding():
    r = SignalRouter()
    r.on_hello("car_media", "cm")
    r.on_hello("quest", "q")
    r.on_hello("booth", "b")
    data = {"candidate": {"candidate": "x"}}
    acts = r.on_signal("quest", "S1", data)
    assert len(sends(acts)) == 1
    fwd = sends(acts, "cm", "signal")[0]
    assert fwd.msg["session"] == "S1" and fwd.msg["data"] == data
    assert r.on_signal("booth", "S1", data) == []


def test_s3_signal_to_internal_peer():
    r = SignalRouter()
    r.on_hello("car_ctrl", "cc")
    acts = r.on_signal("car_ctrl", "S3", {"sdp": {"type": "offer", "sdp": "v=0"}})
    internal = [a for a in acts if isinstance(a, Internal)]
    assert len(internal) == 1
    assert internal[0].msg["type"] == "signal"
    acts = r.on_signal("hub", "S3", {"sdp": {"type": "answer", "sdp": "v=0"}})
    assert sends(acts, "cc", "signal")


def test_rehello_closes_old():
    r = SignalRouter()
    r.on_hello("car_media", "cm")
    r.on_hello("quest", "q1")
    acts = r.on_hello("quest", "q2")
    assert any(isinstance(a, Close) and a.handle == "q1" for a in acts)
    assert sends(acts, "cm", "restart")


def test_close_old_ignored_current_notifies():
    r = SignalRouter()
    r.on_hello("car_media", "cm")
    r.on_hello("quest", "q1")
    r.on_hello("quest", "q2")
    assert r.on_close("quest", "q1") == []
    acts = r.on_close("quest", "q2")
    peer = sends(acts, "cm", "peer")
    assert peer and peer[0].msg == {"type": "peer", "session": "S1", "state": "down"}


def test_restart_req():
    r = SignalRouter()
    r.on_hello("car_media", "cm")
    assert r.on_restart_req("car_media", "S1") == []
    r.on_hello("quest", "q")
    acts = r.on_restart_req("quest", "S1")
    assert sends(acts, "cm", "restart")


def test_unknown_role_and_session():
    r = SignalRouter()
    assert r.on_hello("hacker", "h") == []
    r.on_hello("quest", "q")
    assert r.on_signal("quest", "S9", {}) == []
