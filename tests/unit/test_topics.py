import pytest

from nasura_comm import topics
from nasura_comm.topics import TopicSpec

pytestmark = pytest.mark.verifies("DD-0002", spec="UT-0002")

FIXED = [
    ("sys/heartbeat", "down", "ctrl", 10),
    ("sys/heartbeat_ack", "up", "ctrl", 10),
    ("sys/estop", "down", "rel", None),
    ("sys/estop_release", "down", "rel", None),
    ("sys/state", "up", "rel", 5),
    ("cmd/drive", "down", "ctrl", 30),
    ("cmd/stage", "down", "ctrl", 30),
]


@pytest.mark.parametrize("name,direction,channel,hz", FIXED)
def test_fixed_topics(name, direction, channel, hz):
    spec = topics.lookup(name)
    assert spec is not None
    assert spec.direction == direction
    assert spec.channel == channel
    assert spec.max_rate_hz == hz
    assert spec.fixed is True


def test_fixed_table_has_seven_entries():
    assert len(FIXED) == 7
    assert len({name for name, *_ in FIXED}) == 7


def test_arm_not_registered():
    assert topics.lookup("cmd/arm") is None
    assert "cmd/arm" not in repr(topics.to_json())


def test_unknown():
    assert topics.lookup("tlm/unknown") is None


@pytest.mark.parametrize(
    "bad",
    [
        TopicSpec("sys/heartbeat", "up", "ctrl", 1.0, fixed=False),
        TopicSpec("cmd/new", "up", "ctrl", 1.0, fixed=False),
        TopicSpec("sys/x", "up", "rel", None, fixed=False),
        TopicSpec("in/x", "up", "rel", None, fixed=False),
        TopicSpec("out/x", "up", "rel", None, fixed=False),
    ],
)
def test_invalid_extension(bad):
    with pytest.raises(ValueError):
        topics.validate_extensions([bad])


def test_valid_extension():
    topics.validate_extensions([TopicSpec("tlm/battery_voltage", "up", "ctrl", 2.0, fixed=False)])


def test_to_json_contains_all():
    data = topics.to_json()
    text = repr(data)
    for name, *_ in FIXED:
        assert name in text
    for ext in topics.EXTENSIONS:
        assert ext.name in text
