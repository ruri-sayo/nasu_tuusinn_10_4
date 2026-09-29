"""Hub configuration and JSON views (DD-0009).

Responsibilities:
    - Hold defaults for media (S1/S2) and the hub server, overridable by CLI.
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
SESSIONS = ("S1", "S2", "S3")

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
            1920, 960, 30, 2_500_000, "motion", device_label="Insta360"
        )
    )
    s2: MediaConfig = field(default_factory=lambda: MediaConfig(640, 480, 15, 400_000, "detail"))
    up_budget_bps: int = 3_000_000


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
    ap.add_argument("--s1-max-bitrate", type=int, default=d.s1.max_bitrate)
    ap.add_argument("--s1-codec", default=d.s1.codec, choices=["auto", "H264", "VP8"])
    ap.add_argument("--s1-device-label", default=d.s1.device_label)
    ap.add_argument("--s2-max-bitrate", type=int, default=d.s2.max_bitrate)
    a = ap.parse_args(argv)
    d.port, d.bind, d.tls_self_signed = a.port, a.bind, a.tls_self_signed
    d.web_dir, d.log_dir, d.extra_topics = a.web_dir, a.log_dir, a.extra_topic
    d.s1.width, d.s1.height, d.s1.fps = a.s1_width, a.s1_height, a.s1_fps
    d.s1.max_bitrate, d.s1.codec, d.s1.device_label = (
        a.s1_max_bitrate,
        a.s1_codec,
        a.s1_device_label,
    )
    d.s2.max_bitrate = a.s2_max_bitrate
    return d


def build_config_json(cfg: HubConfig) -> dict[str, Any]:
    """Build the ``/config.json`` payload."""
    return {"S1": asdict(cfg.s1), "S2": asdict(cfg.s2), "up_budget_bps": cfg.up_budget_bps}


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
        "stats": {s: state.stats.get(s) for s in ("S1", "S2")},
        "dropped": dict(state.dropped),
        "telemetry": dict(state.telemetry),
        "up_budget_bps": state.up_budget_bps,
    }
