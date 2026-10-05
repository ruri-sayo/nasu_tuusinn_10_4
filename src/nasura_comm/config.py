"""Hub configuration and JSON views (DD-0009).

Responsibilities:
    - Hold defaults for media (S1/S2, S1 presets, sub camera) and the hub
      server, overridable by CLI.
    - Build ``/config.json`` and ``/status`` payloads as pure functions.

Non-responsibilities:
    - Reading configuration files (none are used; do not hand-write them).
    - Collecting status values (the hub fills ``StatusSnapshot``).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROLES = ("quest", "booth", "car_media", "car_ctrl")
SESSIONS = ("S1", "S2", "S3", "S4")
MEDIA_SESSIONS = ("S1", "S2", "S4")
S1_ROUTES = ("relay", "direct")
"""``relay`` (default): S1 goes car_media -> booth, the booth shows it and
re-sends it to the quest on S4, so the car uplink carries one copy.
``direct``: S1 goes car_media -> quest as before (no S4, booth shows nothing)."""
S1_PRESETS = ("full", "limited")
"""S1 send presets selectable from the booth: ``full`` sends the captured
resolution at ``--s1-full-max-bitrate``; ``limited`` (default) scales down by
``--s1-limited-scale`` and caps at ``--s1-max-bitrate`` (venue uplink)."""

DEFAULT_WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@dataclass
class MediaConfig:
    """Media limits for one session.

    ``max_bitrate`` / ``audio_max_bitrate`` are bps; ``codec`` is ``auto``,
    ``H264`` or ``VP8``; ``device_label`` of ``None`` means the default camera.
    """

    width: int
    height: int
    fps: int
    max_bitrate: int
    content_hint: str
    codec: str = "auto"
    audio_max_bitrate: int = 32_000
    device_label: str | None = None


@dataclass
class SubCameraConfig:
    """Sub (flat) camera selectable on S1; ``label`` is a substring of the device label."""

    label: str = "USB_Camera"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    max_bitrate: int = 8_000_000


@dataclass
class HubConfig:
    """All hub settings."""

    port: int = 8080
    bind: str = "127.0.0.1"
    tls_self_signed: bool = False
    web_dir: Path = DEFAULT_WEB_DIR
    log_dir: Path = Path("logs")
    extra_topics: list[str] = field(default_factory=list)
    s1: MediaConfig = field(
        default_factory=lambda: MediaConfig(
            2880, 1440, 30, 3_600_000, "motion", device_label="Insta360"
        )
    )
    s1_full_max_bitrate: int = 12_000_000
    s1_limited_scale: float = 1.5
    s1_preset: str = "limited"
    sub: SubCameraConfig = field(default_factory=SubCameraConfig)
    s2: MediaConfig = field(default_factory=lambda: MediaConfig(640, 480, 15, 400_000, "detail"))
    s1_route: str = "relay"
    s4: MediaConfig = field(
        default_factory=lambda: MediaConfig(2880, 1440, 30, 15_000_000, "motion")
    )
    """Booth -> quest re-send on the booth LAN (only the limits are used)."""
    up_budget_bps: int = 4_000_000
    yaw_offset_deg: float = 0.0
    """Robot front in the 360° image, degrees right of the image center
    (Insta360 mounting offset); viewers turn the sphere to put it ahead."""


def parse_args(argv: list[str] | None = None) -> HubConfig:
    """Parse hub CLI options into a ``HubConfig``."""
    d = HubConfig()
    ap = argparse.ArgumentParser(prog="python -m nasura_comm.hub")
    ap.add_argument("--port", type=int, default=d.port)
    ap.add_argument("--bind", default=d.bind)
    ap.add_argument("--tls-self-signed", action="store_true")
    ap.add_argument("--web-dir", type=Path, default=d.web_dir)
    ap.add_argument("--log-dir", type=Path, default=d.log_dir)
    ap.add_argument(
        "--extra-topic",
        action="append",
        default=[],
        help="test aid: register NAME:DIR:CHANNEL:HZ as an extension topic",
    )
    ap.add_argument("--s1-width", type=int, default=d.s1.width)
    ap.add_argument("--s1-height", type=int, default=d.s1.height)
    ap.add_argument("--s1-fps", type=int, default=d.s1.fps)
    ap.add_argument(
        "--s1-max-bitrate", type=int, default=d.s1.max_bitrate, help="limited preset (bps)"
    )
    ap.add_argument(
        "--s1-full-max-bitrate", type=int, default=d.s1_full_max_bitrate, help="full preset (bps)"
    )
    ap.add_argument(
        "--s1-limited-scale",
        type=float,
        default=d.s1_limited_scale,
        help="limited preset: divide the captured resolution by this",
    )
    ap.add_argument("--s1-preset", default=d.s1_preset, choices=list(S1_PRESETS))
    ap.add_argument("--s1-codec", default=d.s1.codec, choices=["auto", "H264", "VP8"])
    ap.add_argument("--s1-device-label", default=d.s1.device_label)
    ap.add_argument("--sub-label", default=d.sub.label)
    ap.add_argument("--sub-width", type=int, default=d.sub.width)
    ap.add_argument("--sub-height", type=int, default=d.sub.height)
    ap.add_argument("--sub-fps", type=int, default=d.sub.fps)
    ap.add_argument(
        "--sub-max-bitrate", type=int, default=d.sub.max_bitrate, help="full preset (bps)"
    )
    ap.add_argument("--s2-width", type=int, default=d.s2.width)
    ap.add_argument("--s2-height", type=int, default=d.s2.height)
    ap.add_argument("--s2-fps", type=int, default=d.s2.fps)
    ap.add_argument("--s2-max-bitrate", type=int, default=d.s2.max_bitrate)
    ap.add_argument("--s1-route", default=d.s1_route, choices=list(S1_ROUTES))
    ap.add_argument(
        "--s4-max-bitrate", type=int, default=d.s4.max_bitrate, help="booth -> quest (bps)"
    )
    ap.add_argument("--audio-max-bitrate", type=int, default=d.s1.audio_max_bitrate)
    ap.add_argument("--up-budget-bps", type=int, default=d.up_budget_bps)
    ap.add_argument(
        "--yaw-offset-deg",
        type=float,
        default=d.yaw_offset_deg,
        help="robot front in the 360° image, degrees right of the image center",
    )
    a = ap.parse_args(argv)
    d.port, d.bind, d.tls_self_signed = a.port, a.bind, a.tls_self_signed
    d.web_dir, d.log_dir, d.extra_topics = a.web_dir, a.log_dir, a.extra_topic
    d.s1.width, d.s1.height, d.s1.fps = a.s1_width, a.s1_height, a.s1_fps
    d.s1.max_bitrate, d.s1.codec, d.s1.device_label = (
        a.s1_max_bitrate,
        a.s1_codec,
        a.s1_device_label,
    )
    d.s1_full_max_bitrate, d.s1_limited_scale = a.s1_full_max_bitrate, a.s1_limited_scale
    d.s1_preset = a.s1_preset
    d.sub = SubCameraConfig(a.sub_label, a.sub_width, a.sub_height, a.sub_fps, a.sub_max_bitrate)
    d.s2.width, d.s2.height, d.s2.fps = a.s2_width, a.s2_height, a.s2_fps
    d.s2.max_bitrate = a.s2_max_bitrate
    d.s1_route, d.s4.max_bitrate = a.s1_route, a.s4_max_bitrate
    d.s1.audio_max_bitrate = d.s2.audio_max_bitrate = a.audio_max_bitrate
    d.s4.audio_max_bitrate = max(a.audio_max_bitrate, 64_000)
    d.up_budget_bps = a.up_budget_bps
    d.yaw_offset_deg = a.yaw_offset_deg
    return d


def build_config_json(cfg: HubConfig) -> dict[str, Any]:
    """Build the ``/config.json`` payload."""
    return {
        "S1": asdict(cfg.s1),
        "S1_presets": {
            "full": {"max_bitrate": cfg.s1_full_max_bitrate, "scale": 1.0},
            "limited": {"max_bitrate": cfg.s1.max_bitrate, "scale": cfg.s1_limited_scale},
        },
        "S1_preset": cfg.s1_preset,
        "sub": asdict(cfg.sub),
        "S2": asdict(cfg.s2),
        "S1_route": cfg.s1_route,
        "S4": asdict(cfg.s4),
        "up_budget_bps": cfg.up_budget_bps,
        "view": {"yaw_offset_deg": cfg.yaw_offset_deg},
    }


@dataclass
class StatusSnapshot:
    """Values collected by the hub for ``/status``; ``None`` = not yet known."""

    roles: dict[str, bool] = field(default_factory=dict)
    sessions: dict[str, str | None] = field(default_factory=dict)
    rtt_ms: int | None = None
    rtt_ewma_ms: float | None = None
    car_state: str | None = None
    latched: bool = False
    last_input_age_ms: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    up_budget_bps: int = 3_000_000


def build_status(state: StatusSnapshot) -> dict[str, Any]:
    """Build the ``/status`` payload."""
    return {
        "roles": {r: bool(state.roles.get(r, False)) for r in ROLES},
        "sessions": {s: state.sessions.get(s) for s in SESSIONS},
        "control": {
            "rtt_ms": state.rtt_ms,
            "rtt_ewma_ms": None if state.rtt_ewma_ms is None else round(state.rtt_ewma_ms, 1),
            "car_state": state.car_state,
            "latched": state.latched,
            "last_input_age_ms": state.last_input_age_ms,
        },
        "stats": {s: state.stats.get(s) for s in MEDIA_SESSIONS},
        "dropped": dict(state.dropped),
        "telemetry": dict(state.telemetry),
        "up_budget_bps": state.up_budget_bps,
    }
