import json

import pytest

from nasura_comm import envelope

pytestmark = pytest.mark.verifies("DD-0001", spec="UT-0001")


def _valid() -> dict:
    return envelope.make("cmd/drive", {"v": 0.5}, "hub", 7, 1790000000000)


def test_roundtrip():
    env = _valid()
    text = envelope.encode(env)
    back = envelope.decode(text)
    assert back is not None
    assert dict(back) == {
        "topic": "cmd/drive",
        "ver": 1,
        "seq": 7,
        "ts": 1790000000000,
        "src": "hub",
        "payload": {"v": 0.5},
    }


def test_encode_is_compact():
    assert " " not in envelope.encode(_valid())


def test_invalid_json():
    assert envelope.decode("{not json") is None
    assert envelope.decode("[]") is None
    assert envelope.decode("") is None


@pytest.mark.parametrize("key", ["topic", "ver", "seq", "ts", "src", "payload"])
def test_missing_key(key):
    env = dict(_valid())
    del env[key]
    assert envelope.decode(json.dumps(env)) is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("seq", "1"),
        ("seq", -1),
        ("ver", 0),
        ("ver", "1"),
        ("ts", "x"),
        ("src", 3),
        ("payload", [1, 2]),
        ("payload", "x"),
        ("topic", 5),
    ],
)
def test_wrong_type(key, value):
    env = dict(_valid())
    env[key] = value
    assert envelope.decode(json.dumps(env)) is None


@pytest.mark.parametrize("topic", ["Cmd/drive", "cmd", "cmd//x", "cmd/" + "a" * 61])
def test_bad_topic(topic):
    assert len("cmd/" + "a" * 61) == 65
    env = dict(_valid())
    env["topic"] = topic
    assert envelope.decode(json.dumps(env)) is None


def test_max_topic_length_accepted():
    env = dict(_valid())
    env["topic"] = "cmd/" + "a" * 60
    assert envelope.decode(json.dumps(env)) is not None


def test_oversize():
    env = envelope.make("tlm/big", {"s": "x" * (16 * 1024)}, "car_local", 0, 0)
    assert envelope.decode(envelope.encode(env)) is None


def test_bytes_input():
    assert envelope.decode(envelope.encode(_valid()).encode()) is not None
