import pytest

from nasura_comm.config import StatusSnapshot, build_config_json, build_status, parse_args
from nasura_comm.datachannel import channel_options

MEDIA_KEYS = {
    "width",
    "height",
    "fps",
    "max_bitrate",
    "content_hint",
    "codec",
    "audio_max_bitrate",
    "device_label",
}


@pytest.mark.verifies("DD-0009", spec="UT-0013")
def test_config_defaults():
    cfg = build_config_json(parse_args([]))
    assert MEDIA_KEYS <= set(cfg["S1"])
    assert MEDIA_KEYS <= set(cfg["S2"])
    s1, s2 = cfg["S1"], cfg["S2"]
    assert (s1["width"], s1["height"], s1["fps"], s1["max_bitrate"]) == (2880, 1440, 30, 3_600_000)
    assert (s1["content_hint"], s1["codec"], s1["audio_max_bitrate"]) == ("motion", "auto", 32_000)
    assert s1["device_label"] == "Insta360"
    assert (s2["width"], s2["height"], s2["fps"], s2["max_bitrate"]) == (640, 480, 15, 400_000)
    assert (s2["content_hint"], s2["codec"], s2["audio_max_bitrate"]) == ("detail", "auto", 32_000)
    assert cfg["up_budget_bps"] == 4_000_000


@pytest.mark.verifies("DD-0009", spec="UT-0013")
def test_config_cli_override():
    cfg = build_config_json(parse_args(["--s1-max-bitrate", "2000000", "--s1-codec", "VP8"]))
    assert cfg["S1"]["max_bitrate"] == 2_000_000
    assert cfg["S1"]["codec"] == "VP8"


@pytest.mark.verifies("DD-0009", spec="UT-0013")
def test_status_shape_empty():
    st = build_status(StatusSnapshot())
    assert set(st) >= {"roles", "sessions", "control", "stats", "dropped", "up_budget_bps"}
    assert set(st["roles"]) == {"quest", "booth", "car_media", "car_ctrl"}
    assert set(st["sessions"]) == {"S1", "S2", "S3"}
    ctrl = st["control"]
    assert set(ctrl) >= {"rtt_ms", "rtt_ewma_ms", "car_state", "latched", "last_input_age_ms"}
    assert ctrl["rtt_ms"] is None
    assert ctrl["car_state"] is None
    assert ctrl["last_input_age_ms"] is None


@pytest.mark.verifies("DD-0010", spec="UT-0013")
def test_channel_options():
    assert channel_options("ctrl") == {"ordered": False, "maxRetransmits": 0}
    rel = channel_options("rel")
    assert rel["ordered"] is True
    assert rel.get("maxRetransmits") is None
    with pytest.raises(ValueError):
        channel_options("video")
