"""Host load sampler for crash investigation logs (P0-3, 2026-10-05).

Responsibilities:
    - Sample CPU usage (since the previous sample), memory usage and, where the
      OS exposes it without extra software, the CPU temperature.
    - Linux: ``/proc/stat``, ``/proc/meminfo``, ``/sys/class/hwmon`` and
      ``/sys/class/thermal``. Windows: ``GetSystemTimes`` and
      ``GlobalMemoryStatusEx`` (no temperature: Windows offers none to a
      normal user process without a vendor driver).

Non-responsibilities:
    - Writing logs (callers pass the sample to ``EventLog``).
    - Raising on unsupported platforms or missing files: values become ``None``.

Side Effects:
    Reads system files / calls system APIs only.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any

CPU_SENSORS = ("coretemp", "k10temp", "zenpower", "cpu_thermal")
"""hwmon driver names that report the CPU package/die temperature."""


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None


def _linux_cpu_times() -> tuple[int, int] | None:
    """Return ``(idle, total)`` jiffies from ``/proc/stat``."""
    text = _read(Path("/proc/stat"))
    if not text:
        return None
    f = [int(x) for x in text.splitlines()[0].split()[1:9]]
    return f[3] + f[4], sum(f)


def _linux_mem_pct() -> float | None:
    text = _read(Path("/proc/meminfo"))
    if not text:
        return None
    kv = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        kv[k] = int(v.split()[0]) if v.split() else 0
    total, avail = kv.get("MemTotal"), kv.get("MemAvailable")
    if not total or avail is None:
        return None
    return round(100.0 * (total - avail) / total, 1)


def linux_cpu_temp(root: Path = Path("/sys/class")) -> tuple[float | None, str | None]:
    """Return ``(degrees C, source)``: CPU hwmon max, else thermal zones."""
    temps: list[float] = []
    for hw in sorted((root / "hwmon").glob("hwmon*")):
        name = _read(hw / "name")
        if name not in CPU_SENSORS:
            continue
        for f in hw.glob("temp*_input"):
            v = _read(f)
            if v and v.lstrip("-").isdigit():
                temps.append(int(v) / 1000)
        if temps:
            return round(max(temps), 1), name
    zones: dict[str, float] = {}
    for z in sorted((root / "thermal").glob("thermal_zone*")):
        v, kind = _read(z / "temp"), _read(z / "type") or z.name
        if v and v.lstrip("-").isdigit():
            zones[kind] = int(v) / 1000
    if not zones:
        return None, None
    kind = "x86_pkg_temp" if "x86_pkg_temp" in zones else max(zones, key=lambda k: zones[k])
    return round(zones[kind], 1), kind


class _FileTime(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]

    def value(self) -> int:
        return int((self.hi << 32) | self.lo)


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_uint32),
        ("dwMemoryLoad", ctypes.c_uint32),
        ("rest", ctypes.c_uint64 * 7),
    ]


def _windows_cpu_times() -> tuple[int, int] | None:
    idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
    if not k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    # Kernel time includes idle time.
    return idle.value(), kernel.value() + user.value()


def _windows_mem_pct() -> float | None:
    st = _MemStatus()
    st.dwLength = ctypes.sizeof(_MemStatus)
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
    if not k32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    return float(st.dwMemoryLoad)


class SysMon:
    """Stateful sampler: CPU usage is the average since the previous ``sample``."""

    def __init__(self) -> None:
        """Take the first CPU reading."""
        self._win = sys.platform == "win32"
        self._prev = self._cpu_times()

    def _cpu_times(self) -> tuple[int, int] | None:
        try:
            return _windows_cpu_times() if self._win else _linux_cpu_times()
        except (OSError, ValueError, AttributeError, IndexError):
            return None

    def sample(self) -> dict[str, Any]:
        """Return ``cpu_pct``, ``mem_pct``, ``temp_c``, ``temp_src`` and ``load1``."""
        out: dict[str, Any] = {"cpu_pct": None, "mem_pct": None, "temp_c": None}
        now = self._cpu_times()
        if now and self._prev and now[1] > self._prev[1]:
            idle, total = now[0] - self._prev[0], now[1] - self._prev[1]
            out["cpu_pct"] = round(100.0 * (1 - idle / total), 1)
        self._prev = now
        try:
            out["mem_pct"] = _windows_mem_pct() if self._win else _linux_mem_pct()
        except (OSError, ValueError, AttributeError):
            pass
        if not self._win:
            out["temp_c"], out["temp_src"] = linux_cpu_temp()
            loadavg = getattr(os, "getloadavg", None)
            out["load1"] = round(loadavg()[0], 2) if loadavg else None
        return out
