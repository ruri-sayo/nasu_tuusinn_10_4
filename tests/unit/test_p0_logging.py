"""Implementation-aware tests for the P0-3 crash-investigation log (2026-10-05)."""

import asyncio
import json
from pathlib import Path

import pytest

from nasura_comm.log import EventLog
from nasura_comm.sysmon import SysMon, linux_cpu_temp

pytestmark = pytest.mark.impl_aware()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")


def test_linux_cpu_temp_prefers_cpu_hwmon(tmp_path: Path):
    _write(tmp_path / "hwmon/hwmon0/name", "nvme\n")
    _write(tmp_path / "hwmon/hwmon0/temp1_input", "90000\n")
    _write(tmp_path / "hwmon/hwmon1/name", "coretemp\n")
    _write(tmp_path / "hwmon/hwmon1/temp1_input", "61000\n")
    _write(tmp_path / "hwmon/hwmon1/temp2_input", "67500\n")
    _write(tmp_path / "thermal/thermal_zone0/type", "acpitz\n")
    _write(tmp_path / "thermal/thermal_zone0/temp", "40000\n")
    assert linux_cpu_temp(tmp_path) == (67.5, "coretemp")


def test_linux_cpu_temp_falls_back_to_thermal_zone(tmp_path: Path):
    _write(tmp_path / "thermal/thermal_zone0/type", "acpitz\n")
    _write(tmp_path / "thermal/thermal_zone0/temp", "45000\n")
    _write(tmp_path / "thermal/thermal_zone1/type", "x86_pkg_temp\n")
    _write(tmp_path / "thermal/thermal_zone1/temp", "52000\n")
    assert linux_cpu_temp(tmp_path) == (52.0, "x86_pkg_temp")
    assert linux_cpu_temp(tmp_path / "missing") == (None, None)


def test_sysmon_sample_shape():
    s = SysMon().sample()
    assert {"cpu_pct", "mem_pct", "temp_c"} <= set(s)
    assert s["mem_pct"] is None or 0 <= s["mem_pct"] <= 100


def test_sys_loop_logs_and_syncs(tmp_path: Path):
    log = EventLog("t", tmp_path)

    async def run() -> None:
        task = asyncio.create_task(log.sys_loop(period_s=0.01))
        await asyncio.sleep(0.1)
        task.cancel()

    asyncio.run(run())
    log.close()
    recs = [json.loads(x) for x in log.path.read_text(encoding="utf-8").splitlines()]
    assert recs and all(r["event"] == "sys" and "cpu_pct" in r for r in recs)
