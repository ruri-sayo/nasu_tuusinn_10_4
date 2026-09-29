import pytest

from nasura_comm.envelope import make
from nasura_comm.safety import SafetyCore

_seq = iter(range(1_000_000))


def hb(now=0):
    return make("sys/heartbeat", {"hb": 1, "t_hub": now}, "hub", next(_seq), 0)


def drive(v=0.5, w=0.0, deadman=True):
    return make("cmd/drive", {"v": v, "w": w, "deadman": deadman}, "hub", next(_seq), 0)


def estop():
    return make("sys/estop", {"source": "booth", "reason": "t"}, "hub", next(_seq), 0)


def release():
    return make("sys/estop_release", {"source": "booth"}, "hub", next(_seq), 0)


def stopped(eff):
    return (
        eff["drive"]["v"] == 0
        and eff["drive"]["w"] == 0
        and eff["arm"]["enable"] is False
        and eff["stage"]["x"] == 0
        and eff["stage"]["z"] == 0
    )


def running(core, t=0):
    core.on_envelope(hb(t), t)
    assert core.state == "RUN"
    return core


# --- UT-0008 -------------------------------------------------------------


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_initial():
    core = SafetyCore()
    assert core.state == "INIT"
    assert stopped(core.effective(0))


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_run_and_command():
    core = running(SafetyCore())
    core.on_envelope(drive(0.5), 10)
    assert core.effective(20)["drive"]["v"] == pytest.approx(0.5)


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_heartbeat_timeout():
    core = running(SafetyCore(), 0)
    core.effective(499)
    assert core.state == "RUN"
    eff = core.effective(501)
    assert core.state == "STOP"
    assert stopped(eff)


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_recover_discards_old_command():
    core = running(SafetyCore(), 0)
    core.on_envelope(drive(0.5), 10)
    core.effective(600)
    assert core.state == "STOP"
    core.on_envelope(hb(610), 610)
    assert core.state == "RUN"
    assert stopped(core.effective(620))
    core.on_envelope(drive(0.3), 630)
    assert core.effective(640)["drive"]["v"] == pytest.approx(0.3)


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_link_down():
    core = running(SafetyCore())
    core.on_link_down()
    assert core.state == "STOP"


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_command_timeout_keeps_run():
    core = running(SafetyCore(), 0)
    core.on_envelope(drive(0.5), 0)
    for t in range(100, 401, 100):
        core.on_envelope(hb(t), t)
    eff = core.effective(301)
    assert core.state == "RUN"
    assert eff["drive"]["v"] == 0 and eff["drive"]["w"] == 0


@pytest.mark.verifies("DD-0006", spec="UT-0008")
def test_deadman_false_zeroes_drive():
    core = running(SafetyCore())
    core.on_envelope(drive(0.5, 0.5, deadman=False), 1)
    eff = core.effective(2)
    assert eff["drive"]["v"] == 0 and eff["drive"]["w"] == 0


# --- UT-0009 -------------------------------------------------------------


@pytest.mark.verifies("DD-0006", spec="UT-0009")
@pytest.mark.parametrize("start", ["INIT", "RUN", "STOP"])
def test_estop_from_any(start):
    core = SafetyCore()
    if start in ("RUN", "STOP"):
        running(core)
    if start == "STOP":
        core.on_link_down()
    assert core.state == start
    core.on_envelope(estop(), 1)
    assert core.state == "ESTOP"


@pytest.mark.verifies("DD-0006", spec="UT-0009")
def test_estop_ignores_everything():
    core = running(SafetyCore())
    core.on_envelope(estop(), 1)
    core.on_envelope(hb(2), 2)
    core.on_envelope(drive(0.5), 3)
    assert core.state == "ESTOP"
    assert stopped(core.effective(4))


@pytest.mark.verifies("DD-0006", spec="UT-0009")
def test_release_then_heartbeat():
    core = running(SafetyCore())
    core.on_envelope(estop(), 1)
    core.on_envelope(release(), 2)
    assert core.state == "STOP"
    core.on_envelope(hb(3), 3)
    assert core.state == "RUN"


@pytest.mark.verifies("DD-0006", spec="UT-0009")
def test_state_change_flag():
    core = SafetyCore()
    core.pop_state_changed()
    core.on_envelope(hb(0), 0)
    assert core.pop_state_changed() is True
    assert core.pop_state_changed() is False
    core.on_envelope(hb(10), 10)
    assert core.pop_state_changed() is False
    core.on_envelope(estop(), 20)
    assert core.pop_state_changed() is True
    core.on_envelope(release(), 30)
    assert core.pop_state_changed() is True
