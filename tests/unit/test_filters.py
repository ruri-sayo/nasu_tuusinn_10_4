import pytest

from nasura_comm.filters import RateLimiter, SeqFilter


@pytest.mark.verifies("DD-0003", spec="UT-0003")
def test_seq_basic():
    f = SeqFilter()
    assert f.accept("hub", "cmd/drive", 5)
    assert not f.accept("hub", "cmd/drive", 4)
    assert not f.accept("hub", "cmd/drive", 5)
    assert f.accept("hub", "cmd/drive", 6)


@pytest.mark.verifies("DD-0003", spec="UT-0003")
def test_seq_independent():
    f = SeqFilter()
    assert f.accept("hub", "cmd/drive", 5)
    assert f.accept("hub", "cmd/stage", 1)
    assert f.accept("quest", "cmd/drive", 1)


@pytest.mark.verifies("DD-0003", spec="UT-0003")
def test_seq_reset():
    f = SeqFilter()
    assert f.accept("hub", "cmd/drive", 5000)
    assert not f.accept("hub", "cmd/drive", 4500)
    assert f.accept("hub", "cmd/drive", 3)
    assert f.accept("hub", "cmd/drive", 4)


@pytest.mark.verifies("DD-0003", spec="UT-0004")
def test_rate_10hz():
    r = RateLimiter()
    assert r.allow("sys/heartbeat", 0)
    assert not r.allow("sys/heartbeat", 50)
    assert r.allow("sys/heartbeat", 100)


@pytest.mark.verifies("DD-0003", spec="UT-0004")
def test_rate_unlimited():
    r = RateLimiter()
    assert all(r.allow("sys/estop", 0) for _ in range(20))
