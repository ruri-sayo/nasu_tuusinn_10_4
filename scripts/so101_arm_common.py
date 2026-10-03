"""Shared helpers for the SO-101 streaming scripts (provisional, F-003).

Run with the LeRobot virtual environment's Python, not the nasura_comm one.

Side Effects: runs ``git`` in the hardware checkout; writes logs/.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from nasura_comm import arm_stream  # noqa: E402


def setup_logging(name: str) -> logging.Logger:
    """Log to stderr and to logs/<name>-<time>.log."""
    log_dir = REPO / "logs"
    log_dir.mkdir(exist_ok=True)
    path = log_dir / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")],
    )
    log = logging.getLogger(name)
    log.info("log file %s", path)
    return log


def head_commit(directory: Path) -> str | None:
    """Return ``git rev-parse HEAD`` of ``directory`` (None on failure)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def find_port(serial: str) -> str | None:
    """Return the serial port (COMx or /dev/tty...) whose USB serial is ``serial``."""
    from serial.tools import list_ports

    for p in list_ports.comports():
        if p.serial_number == serial:
            return str(p.device)
    return None


def preflight(log: logging.Logger, hardware_dir: Path, side: str, role: str) -> str:
    """Check the hardware checkout and the USB device; return the port or exit(2).

    Also points LeRobot at the tracked calibration files. Must run before
    importing lerobot, which reads HF_LEROBOT_CALIBRATION at import time.
    """
    import os

    commit = head_commit(hardware_dir)
    errors = arm_stream.check_hardware_dir(hardware_dir, commit, side, role)
    port = None
    if not errors:
        rule = (hardware_dir / arm_stream.UDEV_RULE).read_text(encoding="utf-8")
        serial = arm_stream.parse_udev_serials(rule)[arm_stream.device_id(side, role)]
        port = find_port(serial)
        if port is None:
            errors.append(f"{arm_stream.device_id(side, role)} (serial {serial}) is not connected")
        else:
            log.info("%s: serial %s at %s", arm_stream.device_id(side, role), serial, port)
    if errors or port is None:
        for e in errors:
            log.error("preflight: %s", e)
        sys.exit(2)
    os.environ["HF_LEROBOT_CALIBRATION"] = str(hardware_dir / arm_stream.CALIBRATION_ROOT)
    log.info("preflight OK: hardware %s, calibration %s", commit,
             arm_stream.calibration_file(hardware_dir, side, role))
    return port


def connect_with_tracked_calibration(log: logging.Logger, device: object, hold: bool) -> None:
    """Connect like LeRobot's ``connect()`` but without its interactive prompt.

    If the motors differ from the tracked calibration file, the file values
    are written (what LeRobot does when ENTER is pressed at its prompt); new
    values are never generated (REQ-0025). Writing happens with torque off.
    With ``hold`` (follower), Goal_Position is set to Present_Position before
    ``configure()`` re-enables torque, so the arm does not move on connect.
    """
    calibration = getattr(device, "calibration", None)
    if not calibration:
        log.error("no calibration loaded for %s", device)
        sys.exit(2)
    bus = device.bus  # type: ignore[attr-defined]
    bus.connect()
    bus.disable_torque()
    if not device.is_calibrated:  # type: ignore[attr-defined]
        log.warning("motor calibration differs from the tracked file; writing the file values")
        bus.write_calibration(calibration)
    if hold:
        bus.sync_write("Goal_Position", bus.sync_read("Present_Position"))
    device.configure()  # type: ignore[attr-defined]
    log.info("%s connected", device)
