"""Implementation-aware tests for the 2026-10-05 P0 changes (rehearsal fixes).

Written alongside the implementation before the design items had IDs, so they
are ``impl_aware`` and do not count toward coverage of the specification.
"""

import pytest

from nasura_comm.config import build_config_json, parse_args
from nasura_comm.hub.app import Hub

pytestmark = pytest.mark.impl_aware()


def test_yaw_offset_default_and_override():
    assert build_config_json(parse_args([]))["view"] == {"yaw_offset_deg": 0.0}
    cfg = build_config_json(parse_args(["--yaw-offset-deg", "-12.5"]))
    assert cfg["view"]["yaw_offset_deg"] == -12.5


def test_s1_presets_default_limited_within_budget():
    cfg = build_config_json(parse_args([]))
    assert cfg["S1_preset"] == "limited"
    lim, full = cfg["S1_presets"]["limited"], cfg["S1_presets"]["full"]
    assert lim == {"max_bitrate": cfg["S1"]["max_bitrate"], "scale": 1.5}
    assert full == {"max_bitrate": 12_000_000, "scale": 1.0}
    audio = cfg["S1"]["audio_max_bitrate"]
    assert lim["max_bitrate"] + audio <= cfg["up_budget_bps"] - 300_000


def test_s1_preset_and_media_cli():
    cfg = build_config_json(
        parse_args(
            [
                "--s1-max-bitrate=2000000",
                "--s1-full-max-bitrate=9000000",
                "--s1-limited-scale=2",
                "--s1-preset=full",
                "--sub-label=Cam",
                "--sub-max-bitrate=5000000",
                "--s2-width=320",
                "--s2-height=240",
                "--s2-fps=10",
                "--audio-max-bitrate=24000",
                "--up-budget-bps=3000000",
            ]
        )
    )
    assert cfg["S1_presets"]["limited"] == {"max_bitrate": 2_000_000, "scale": 2.0}
    assert cfg["S1_presets"]["full"]["max_bitrate"] == 9_000_000
    assert cfg["S1_preset"] == "full"
    assert cfg["sub"]["label"] == "Cam" and cfg["sub"]["max_bitrate"] == 5_000_000
    assert (cfg["S2"]["width"], cfg["S2"]["height"], cfg["S2"]["fps"]) == (320, 240, 10)
    assert cfg["S1"]["audio_max_bitrate"] == cfg["S2"]["audio_max_bitrate"] == 24_000
    assert cfg["up_budget_bps"] == 3_000_000


def test_hub_selects_camera_and_preset():
    hub = Hub(parse_args([]))
    assert (hub.camera, hub.preset) == ("main", "limited")
    hub._select_camera({"preset": "full"})
    assert (hub.camera, hub.preset) == ("main", "full")
    hub._select_camera({"source": "sub"})
    assert (hub.camera, hub.preset) == ("sub", "full")
    assert hub._camera_msg()["env"]["payload"] == {"source": "sub", "preset": "full"}
    for bad in ({}, {"preset": "max"}, {"source": "x", "preset": "limited"}):
        hub._select_camera(bad)
    assert (hub.camera, hub.preset) == ("sub", "full")
    assert hub.dropped["in/camera"] == 3


def test_relay_route_sessions():
    from nasura_comm.signaling import SESSIONS_RELAY, Send, SignalRouter

    r = SignalRouter(SESSIONS_RELAY)
    r.on_hello("car_media", "c")
    acts = r.on_hello("booth", "b")
    restarts = sorted(
        (a.handle, a.msg["session"])
        for a in acts
        if isinstance(a, Send) and a.msg["type"] == "restart"
    )
    assert restarts == [("b", "S2"), ("c", "S1")]
    acts = r.on_hello("quest", "q")
    assert [(a.handle, a.msg["session"]) for a in acts] == [("b", "S4")]
    assert r.on_signal("quest", "S1", {}) == []  # the quest is not on S1 any more
    fwd = r.on_signal("quest", "S4", {"x": 1})
    assert fwd[0].handle == "b"
    peer = r.on_close("booth", "b")
    assert sorted((a.handle, a.msg["session"]) for a in peer) == [
        ("c", "S1"),
        ("c", "S2"),
        ("q", "S4"),
    ]


def test_route_default_relay_and_direct_option():
    assert build_config_json(parse_args([]))["S1_route"] == "relay"
    hub = Hub(parse_args(["--s1-route", "direct"]))
    assert "S4" not in hub.router.sessions
    assert Hub(parse_args([])).router.sessions["S1"] == ("car_media", "booth")


def _env(topic, payload, src):
    return {"topic": topic, "ver": 1, "seq": 0, "ts": 0, "src": src, "payload": payload}


def test_admin_login_gates_settings_and_input_source(monkeypatch):
    monkeypatch.delenv("NASURA_ADMIN_PASSWORD", raising=False)
    hub = Hub(parse_args([]))
    assert hub.cfg.admin_password == "Admin"
    assert "Admin" not in str(build_config_json(hub.cfg))
    seen = []
    hub.core.on_input = lambda env, *_: seen.append(env["src"]) or []
    stick = {"left": {"axes": [0, -1]}, "right": {}}

    hub._handle_input("booth", _env("in/quest", stick, "booth"))
    hub._handle_input("quest", _env("in/quest", stick, "quest"))
    assert seen == ["quest"]  # default: the Quest controllers drive

    # Not logged in: switching is refused.
    hub._handle_input("booth", _env("in/pilot", {"mode": "gamepad"}, "booth"))
    hub._handle_input("booth", _env("in/camera", {"preset": "full"}, "booth"))
    assert (hub.pilot, hub.preset) == ("quest", "limited")

    hub._handle_input("booth", _env("in/admin", {"password": "x"}, "booth"))
    assert not hub.admin
    hub._admin_fail_at -= 2000  # let the retry block expire
    hub._handle_input("booth", _env("in/admin", {"password": "Admin"}, "booth"))
    assert hub.admin
    hub._handle_input("booth", _env("in/pilot", {"mode": "gamepad"}, "booth"))
    hub._handle_input("booth", _env("in/camera", {"preset": "full"}, "booth"))
    assert (hub.pilot, hub.preset) == ("gamepad", "full")

    seen.clear()
    hub._handle_input("quest", _env("in/quest", stick, "quest"))
    hub._handle_input("booth", _env("in/quest", stick, "booth"))
    assert seen == ["booth"]  # gamepad mode: only the booth page drives
    hub._handle_input("quest", _env("in/pilot", {"mode": "quest"}, "quest"))
    assert hub.pilot == "gamepad"  # the quest may not switch

    hub._handle_input("booth", _env("in/admin", {"logout": True}, "booth"))
    hub._handle_input("booth", _env("in/pilot", {"mode": "quest"}, "booth"))
    assert hub.pilot == "gamepad"


def test_admin_wrong_password_blocks_retry():
    hub = Hub(parse_args(["--admin-password", "pw"]))
    hub._login({"password": "nope"})
    hub._login({"password": "pw"})  # within the retry block
    assert not hub.admin
