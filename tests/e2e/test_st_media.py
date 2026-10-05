"""System/E2E tests with the real pages in headless Chrome (fake camera/microphone).

Responsibilities:
    - Run hub + car_ctrl + car/booth/quest pages (one headless Chrome per page) and
      observe media delivery, bitrates, monitoring and recovery through /status, the
      pages' DOM (DevTools protocol) and the car's UDP out.
    - Automate the dev-machine subset of ST-0004, ST-0007, ST-0008(b), ST-0011 and ST-0012.

Non-responsibilities:
    - WebXR rendering and Quest controller input (headless Chrome has no immersive-vr);
      control input comes from a WebSocket client with role=quest once the quest page
      has been navigated away (only one connection per role is kept by the hub).
    - Real WAN conditions, audio quality/latency and physical camera behaviour.

Constraints:
    - Tests in this module share one deployment and run in file order; each test first
      waits until the system is back in its expected state.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

import pytest
from e2elib import (
    TLM_EXTRA,
    ChromePage,
    InputPump,
    System,
    UdpRecorder,
    WsClient,
    chrome_path,
    eff_drive,
    eff_state,
    free_tcp_port,
    free_udp_port,
    get_status,
    quest_input,
    wait_status,
    wait_udp,
)

RECOVERY_S = 15.0  # ST-0011
S2_MAX_KBPS = 400.0  # REQ-0009 / ST-0004
UP_BUDGET_KBPS = 4000.0  # REQ-0007
DOWNSTREAM_GAP_S = 0.2  # DD-0007 I/F contract
PAGES = ("car", "booth", "quest")


def all_up(st: dict[str, Any]) -> bool:
    sessions = st.get("sessions", {})
    return all(sessions.get(k) == "connected" for k in ("S1", "S2", "S3"))


def media_flowing(st: dict[str, Any]) -> bool:
    stats = st.get("stats", {})
    s1 = (stats.get("S1") or {}).get("quest") or {}
    s2 = (stats.get("S2") or {}).get("car_media") or {}
    return all_up(st) and (s1.get("fps") or 0) > 0 and (s2.get("fps") or 0) > 0


class Deployment:
    """hub + car_ctrl + one headless Chrome per page, shared by this module."""

    def __init__(self, system: System, chrome: str) -> None:
        self.system = system
        self.chrome = chrome
        self.pages: dict[str, ChromePage] = {}
        self.samples: list[dict[str, Any]] | None = None

    def open_page(self, name: str) -> ChromePage:
        url = f"http://localhost:{self.system.hub_port}/{name}/"
        page = ChromePage(self.chrome, url, self.system.workdir, name)
        self.pages[name] = page
        return page

    def stop(self) -> None:
        for p in self.pages.values():
            p.stop()
        self.system.stop_all()


@pytest.fixture(scope="module")
def dep(tmp_path_factory: pytest.TempPathFactory) -> Any:
    chrome = chrome_path()
    if chrome is None:
        pytest.skip("Google Chrome not found (set CHROME to the binary path)")
    workdir = Path(tmp_path_factory.mktemp("media"))
    system = System(
        workdir=workdir,
        hub_port=free_tcp_port(),
        udp_out=free_udp_port(),
        udp_in=free_udp_port(),
        extra_topics=[TLM_EXTRA],
        # These tests follow the S1 car_media -> quest design; the booth relay
        # route (default since 2026-10-05) is checked on the real hardware.
        hub_args=["--s1-route", "direct"],
    )
    d = Deployment(system, chrome)
    try:
        system.start_hub()
        system.start_car()
        for name in PAGES:
            d.open_page(name)
        asyncio.run(wait_status(system.base, media_flowing, timeout=60))
        yield d
    finally:
        d.stop()


async def collect_stats(base: str, seconds: float) -> list[dict[str, Any]]:
    """Sample /status stats every second (pages report every 2 s)."""
    out = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        st = await get_status(base)
        out.append(st["stats"])
        await asyncio.sleep(1.0)
    return out


async def stats_samples(dep: Deployment) -> list[dict[str, Any]]:
    if dep.samples is None:
        await wait_status(dep.system.base, media_flowing, timeout=30)
        await asyncio.sleep(4.0)  # let bandwidth estimation settle
        dep.samples = await collect_stats(dep.system.base, 10.0)
    return dep.samples


def role_stats(samples: list[dict[str, Any]], session: str, role: str) -> list[dict[str, Any]]:
    return [s[session][role] for s in samples if (s.get(session) or {}).get(role)]


@pytest.mark.verifies("REQ-0004", spec="ST-0004")
async def test_pilot_video_is_shown_full_screen_on_car_page(dep: Deployment) -> None:
    """Booth camera frames arrive at the car page and fill its whole viewport."""
    samples = await stats_samples(dep)
    recv = role_stats(samples, "S2", "car_media")
    assert recv, "car_media never reported S2 stats"
    assert all(r["state"] == "connected" for r in recv)
    assert min(r["fps"] for r in recv) > 0
    assert min(r["recv_kbps"] for r in recv) > 0

    probe = """(() => {
      const vs = [...document.querySelectorAll('video')].filter(v => v.videoWidth > 0);
      return vs.map(v => { const r = v.getBoundingClientRect();
        return {w: v.videoWidth, h: v.videoHeight, t: v.currentTime, paused: v.paused,
                left: r.left, top: r.top, width: r.width, height: r.height,
                vw: innerWidth, vh: innerHeight}; });
    })()"""
    car = dep.pages["car"]
    first = await car.evaluate(probe)
    await asyncio.sleep(1.0)
    second = await car.evaluate(probe)
    assert first and second, "no playing <video> on the car page"
    v0, v1 = first[0], second[0]
    assert not v1["paused"]
    assert v1["t"] > v0["t"], "pilot video is not advancing"
    # Full screen: the element covers the whole viewport.
    assert v1["left"] <= 0 and v1["top"] <= 0
    assert v1["width"] >= v1["vw"] - 1 and v1["height"] >= v1["vh"] - 1


@pytest.mark.verifies("REQ-0009", spec="ST-0004")
async def test_pilot_video_is_sent_small_and_under_400kbps(dep: Deployment) -> None:
    """Booth S2 sender stays low-res / low-fps and at or below ~400 kbps."""
    sent = role_stats(await stats_samples(dep), "S2", "booth")
    assert len(sent) >= 5, "booth reported too few S2 stats"
    kbps = [s["send_kbps"] for s in sent]
    mean = sum(kbps) / len(kbps)
    assert mean > 0
    assert mean <= S2_MAX_KBPS, f"S2 send mean {mean:.0f} kbps, samples {kbps}"
    assert max(kbps) <= S2_MAX_KBPS * 1.1, f"S2 send samples {kbps}"
    for s in sent:
        assert s["width"] <= 640 and s["height"] <= 480, s
        assert s["fps"] <= 16, s


@pytest.mark.verifies("REQ-0007", spec="ST-0007")
async def test_car_uplink_media_stays_within_3mbps(dep: Deployment) -> None:
    """The car's upstream (S1 video+audio as sent by car_media) stays within 3.0 Mbps."""
    samples = await stats_samples(dep)
    sent = role_stats(samples, "S1", "car_media")
    recv = role_stats(samples, "S1", "quest")
    assert len(sent) >= 5 and recv, "S1 stats missing"
    assert min(r["fps"] for r in recv) > 0, "S1 is not delivering frames"
    kbps = [s["send_kbps"] for s in sent]
    assert min(kbps) > 0
    assert max(kbps) <= UP_BUDGET_KBPS, f"S1 upstream samples {kbps}"


@pytest.mark.verifies("REQ-0019", spec="ST-0012")
async def test_booth_shows_rtt_rates_connections_and_car_state(dep: Deployment) -> None:
    """RTT, S1/S2 bitrate+fps, connection state and car state are visible at the booth."""
    st = await wait_status(dep.system.base, media_flowing, timeout=20)
    ctrl = st["control"]
    assert isinstance(ctrl["rtt_ms"], (int, float)) and ctrl["rtt_ms"] >= 0
    assert ctrl["car_state"] == "RUN"
    assert all(st["roles"][r] for r in ("quest", "booth", "car_media", "car_ctrl"))
    for session, sender, receiver in (("S1", "car_media", "quest"), ("S2", "booth", "car_media")):
        assert st["stats"][session][sender]["send_kbps"] > 0
        assert st["stats"][session][sender]["fps"] > 0
        assert st["stats"][session][receiver]["recv_kbps"] > 0
        assert st["stats"][session][receiver]["fps"] > 0

    # The booth page renders the same information.
    booth = dep.pages["booth"]
    text0 = await booth.evaluate("document.body.innerText")
    assert "RUN" in text0
    for s in ("S1", "S2", "S3"):
        assert re.search(rf"{s}\s+connected", text0), f"{s} state not shown:\n{text0}"
    assert re.search(r"\d+(\.\d+)?\s*ms", text0), "RTT not shown"
    assert len(re.findall(r"\d+\s*kbps", text0)) >= 2, "bitrates not shown"
    assert re.search(r"\d+\s*fps", text0) or "fps" in text0, "fps not shown"

    # The display refreshes (ST-0012: about once per second).
    changed = False
    for _ in range(6):
        await asyncio.sleep(0.5)
        if await booth.evaluate("document.body.innerText") != text0:
            changed = True
            break
    assert changed, "booth monitoring text did not refresh within 3 s"


@pytest.mark.verifies("REQ-0018", spec="ST-0011")
async def test_hub_restart_all_sessions_come_back(dep: Deployment) -> None:
    """Restarting the hub alone: car_ctrl and all pages reconnect and S1-S3 come back."""
    system = dep.system
    await wait_status(system.base, media_flowing, timeout=30)
    assert system.hub is not None
    system.hub.kill_hard()
    t_restart = time.monotonic()
    system.start_hub()
    await wait_status(system.base, media_flowing, timeout=RECOVERY_S)
    elapsed = time.monotonic() - t_restart
    assert elapsed <= RECOVERY_S
    assert all(p.proc.alive() for p in dep.pages.values())
    assert system.car is not None and system.car.alive()


@pytest.mark.verifies("REQ-0018", spec="ST-0011")
async def test_car_ctrl_restart_leaves_media_and_recovers(dep: Deployment) -> None:
    """Restarting car_ctrl alone: S3 comes back, media sessions are not disturbed."""
    system = dep.system
    await wait_status(system.base, media_flowing, timeout=30)
    assert system.car is not None
    system.car.kill_hard()
    await wait_status(system.base, lambda s: s["roles"]["car_ctrl"] is False, timeout=5)
    t_restart = time.monotonic()
    system.start_car()
    st = await wait_status(
        system.base,
        lambda s: media_flowing(s) and s["control"]["car_state"] == "RUN",
        timeout=RECOVERY_S,
    )
    assert time.monotonic() - t_restart <= RECOVERY_S
    assert st["roles"]["car_ctrl"] is True


FRAMES_PER_SECOND_JS = """(async () => {
  const v = [...document.querySelectorAll('video')].find(x => x.videoWidth > 0 && !x.paused);
  if (!v || !v.requestVideoFrameCallback) return 0;
  let n = 0;
  const cb = () => { n++; v.requestVideoFrameCallback(cb); };
  v.requestVideoFrameCallback(cb);
  await new Promise(r => setTimeout(r, 1000));
  return n;
})()"""


async def rendered_fps(page: ChromePage) -> int:
    """Video frames presented by the page's playing <video> during one second."""
    try:
        return int(await page.evaluate(FRAMES_PER_SECOND_JS) or 0)
    except Exception:  # noqa: BLE001 - page may be mid-navigation
        return 0


async def reload_page(page: ChromePage) -> float:
    """Reload a page and wait until the new document is running; returns t_reload."""
    await page.evaluate("window.__e2e_marker = 1")
    await page.cdp("Page.reload", {"ignoreCache": True})
    t_reload = time.monotonic()
    deadline = t_reload + 10
    while time.monotonic() < deadline:
        try:
            if await page.evaluate("window.__e2e_marker === undefined"):
                return t_reload
        except Exception:  # noqa: BLE001 - page may be mid-navigation
            pass
        await asyncio.sleep(0.1)
    raise AssertionError(f"{page.name} page did not reload")


async def wait_frames(page: ChromePage, deadline: float) -> None:
    while time.monotonic() < deadline:
        if await rendered_fps(page) > 0:
            return
    raise AssertionError(f"{page.name} page shows no fresh video frames")


@pytest.mark.verifies("REQ-0018", spec="ST-0011")
async def test_page_reloads_recover_sessions(dep: Deployment) -> None:
    """Reloading the car page, then the quest page: S1/S2 re-establish on their own."""
    system = dep.system
    car, quest = dep.pages["car"], dep.pages["quest"]

    await wait_status(system.base, media_flowing, timeout=30)
    t_reload = await reload_page(car)
    deadline = t_reload + RECOVERY_S
    await wait_frames(car, deadline)  # S2 (booth -> new car document)
    await wait_frames(quest, deadline)  # S1 (new car document -> quest)
    await wait_status(system.base, media_flowing, timeout=max(0.1, deadline - time.monotonic()))
    assert time.monotonic() - t_reload <= RECOVERY_S

    t_reload = await reload_page(quest)
    deadline = t_reload + RECOVERY_S
    await wait_frames(quest, deadline)  # S1 into the new quest document
    await wait_status(system.base, media_flowing, timeout=max(0.1, deadline - time.monotonic()))
    assert time.monotonic() - t_reload <= RECOVERY_S
    assert all(p.proc.alive() for p in dep.pages.values())


@pytest.mark.verifies("REQ-0015", spec="ST-0008")
async def test_media_teardown_does_not_disturb_control(dep: Deployment) -> None:
    """Reloading the car page (S1/S2 torn down and renegotiated) while driving: RUN throughout.

    The quest page is navigated away first so that a WebSocket client can take the quest
    role and generate controller input (headless Chrome cannot run WebXR). S2 therefore
    is the media session that is torn down and rebuilt while commands flow.
    """
    system = dep.system
    car = dep.pages["car"]
    await wait_status(system.base, media_flowing, timeout=30)
    await dep.pages["quest"].cdp("Page.navigate", {"url": "about:blank"})
    await wait_status(system.base, lambda s: s["roles"]["quest"] is False, timeout=10)

    udp = UdpRecorder(system.udp_out)
    quest = await WsClient(system.ws_url, "quest").connect()
    pump = InputPump(quest, quest_input(ly=-1.0)).start()
    try:
        await wait_udp(udp, lambda e: eff_state(e) == "RUN" and eff_drive(e)[0] > 0.5, 3)
        await wait_frames(car, time.monotonic() + 10)

        t0 = await reload_page(car)
        await wait_frames(car, t0 + RECOVERY_S)  # S2 rebuilt into the new car document
        await asyncio.sleep(1.0)
        window = udp.snapshot(t0 - 0.5)
        st = await get_status(system.base)

        assert len(window) > 20
        bad = [e for _, e in window if not (eff_state(e) == "RUN" and eff_drive(e)[0] > 0.5)]
        assert not bad, f"control disturbed during media teardown: {bad[:3]}"
        ts = [t for t, _ in window]
        max_gap = max(b - a for a, b in zip(ts, ts[1:], strict=False))
        assert max_gap < DOWNSTREAM_GAP_S, f"UDP out gap {max_gap:.3f}s"
        assert st["control"]["car_state"] == "RUN" and st["sessions"]["S3"] == "connected"
        assert st["control"]["rtt_ms"] is not None
    finally:
        await pump.stop()
        await quest.close()
        udp.close()
