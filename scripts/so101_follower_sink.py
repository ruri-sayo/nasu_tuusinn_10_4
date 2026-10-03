"""Drive one SO-101 follower arm from streamed leader frames (provisional, F-003).

Usage (LeRobot venv Python, on the car PC):
    python scripts/so101_follower_sink.py --side left --allow-from <laptop> \
        --confirm-safe-workspace

Responsibilities: preflight one follower, receive frames for its side only,
apply the newest fresh frame at --fps with LeRobot's max_relative_target
clipping, and hold position (send no goal) while frames are stale.
Non-responsibilities: reading the leader (so101_leader_stream.py), video.
Side Effects: opens the follower's serial port and drives its servos; listens
on UDP; writes logs/. On exit the follower torque is disabled
(disable_torque_on_disconnect, REQ-0028): the arm goes limp.

Safety: software stop is auxiliary. The attendant must be able to cut the
follower power at any time (AD-0018).
"""

from __future__ import annotations

import argparse
import select
import signal
import socket
import sys
import time
from pathlib import Path

from so101_arm_common import arm_stream, connect_with_tracked_calibration, preflight, setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--side", choices=arm_stream.SIDES, required=True)
    ap.add_argument("--allow-from", required=True, help="leader laptop tailnet name or IP")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, help="UDP port (default: 47110 left / 47111 right)")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--timeout-ms", type=int, default=500, help="hold position after this silence")
    ap.add_argument(
        "--max-relative-target", type=float, default=arm_stream.MAX_RELATIVE_TARGET_LIMIT
    )
    ap.add_argument("--hardware-dir", type=Path, default=Path.home() / "hardware")
    ap.add_argument("--confirm-safe-workspace", action="store_true",
                    help="confirm: attendant at the power switch, clear workspace, no load")
    args = ap.parse_args()
    port = args.port or arm_stream.PORTS[args.side]

    log = setup_logging(f"so101-follower-{args.side}")
    if not args.confirm_safe_workspace:
        log.error("refusing to start without --confirm-safe-workspace (AD-0018)")
        sys.exit(2)
    err = arm_stream.check_max_relative_target(args.max_relative_target)
    if err:
        log.error(err)
        sys.exit(2)
    allowed_ip = socket.gethostbyname(args.allow_from)
    serial_port = preflight(log, args.hardware_dir, args.side, "follower")

    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    follower = SO101Follower(SO101FollowerConfig(
        port=serial_port,
        id=arm_stream.device_id(args.side, "follower"),
        disable_torque_on_disconnect=True,
        max_relative_target=args.max_relative_target,
    ))
    connect_with_tracked_calibration(log, follower, hold=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, port))
    sock.setblocking(False)
    log.info("%s follower listening on %s:%d (allow %s, max_relative_target %.1f, timeout %d ms)",
             args.side, args.bind, port, allowed_ip, args.max_relative_target, args.timeout_ms)

    stop = {"reason": ""}

    def request_stop(signum: int, _frame: object) -> None:
        stop["reason"] = signal.Signals(signum).name

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    gate = arm_stream.FrameGate(args.side, args.timeout_ms)
    period = 1.0 / args.fps
    was_fresh = False
    rejected = applied = 0
    last_report = time.monotonic()
    reported: set[tuple[str, str]] = set()

    def reject(src: str, reason: str) -> None:
        # Log each (source, reason) once so a silent mismatch is visible.
        nonlocal rejected
        rejected += 1
        if (src, reason) not in reported:
            reported.add((src, reason))
            log.warning("rejecting frames from %s: %s", src, reason)

    log.info("waiting for leader frames (follower holds its position until then)")
    try:
        while not stop["reason"]:
            deadline = time.perf_counter() + period
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                ready, _, _ = select.select([sock], [], [], remaining)
                if not ready:
                    break
                try:
                    data, (src, _) = sock.recvfrom(65535)
                except BlockingIOError:
                    continue
                if src != allowed_ip:
                    reject(src, f"source is not --allow-from ({allowed_ip})")
                    continue
                frame = arm_stream.decode_frame(data)
                if frame is None:
                    reject(src, "invalid frame")
                elif frame.side != args.side:
                    reject(src, f"frame for side {frame.side!r} on the {args.side} port")
                elif not gate.offer(frame, int(time.monotonic() * 1000)):
                    rejected += 1  # duplicate or out of order: normal on UDP
            now = int(time.monotonic() * 1000)
            fresh = gate.fresh(now)
            if fresh != was_fresh:
                msg = "stream fresh: following leader" if fresh else "stream stale: holding"
                log.warning(msg)
                was_fresh = fresh
            if fresh and gate.latest is not None:
                follower.send_action(gate.latest.action())
                applied += 1
            if time.monotonic() - last_report >= 10:
                last_report = time.monotonic()
                log.info("applied %d, rejected %d", applied, rejected)
    except Exception:
        log.exception("follower loop failed")
        stop["reason"] = "error"
    finally:
        follower.disconnect()
        log.info("follower disconnected, torque disabled (reason: %s)", stop["reason"] or "unknown")
    sys.exit(0 if stop["reason"] in ("SIGINT", "SIGTERM") else 1)


if __name__ == "__main__":
    main()
