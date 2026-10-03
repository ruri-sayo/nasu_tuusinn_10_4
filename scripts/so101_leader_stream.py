"""Stream one SO-101 leader arm to the follower host over UDP (provisional, F-003).

Usage (LeRobot venv Python, on the operator laptop):
    python scripts/so101_leader_stream.py --side left --follower-host nasc

Responsibilities: preflight one leader, read its joints at --fps and send
one frame per reading to the follower host (one UDP port per side).
Non-responsibilities: follower control and safety (so101_follower_sink.py).
Side Effects: opens the leader's serial port (LeRobot writes motor settings
and, if the motors differ from the tracked file, the tracked calibration);
sends UDP; writes logs/.
"""

from __future__ import annotations

import argparse
import socket
import time
import uuid
from pathlib import Path

from so101_arm_common import arm_stream, connect_with_tracked_calibration, preflight, setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--side", choices=arm_stream.SIDES, required=True)
    ap.add_argument("--follower-host", required=True, help="car PC tailnet name or IP")
    ap.add_argument("--port", type=int, help="UDP port (default: 47110 left / 47111 right)")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--hardware-dir", type=Path, default=Path.home() / "hardware")
    args = ap.parse_args()
    port = args.port or arm_stream.PORTS[args.side]

    log = setup_logging(f"so101-leader-{args.side}")
    serial_port = preflight(log, args.hardware_dir, args.side, "leader")

    from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

    leader_id = arm_stream.device_id(args.side, "leader")
    leader = SO101Leader(SO101LeaderConfig(port=serial_port, id=leader_id))
    connect_with_tracked_calibration(log, leader, hold=False)

    target = (socket.gethostbyname(args.follower_host), port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    session = uuid.uuid4().hex[:12]
    log.info("streaming %s leader to %s:%d at %.0f fps (session %s)",
             args.side, *target, args.fps, session)

    period = 1.0 / args.fps
    seq = 0
    next_t = time.perf_counter()
    last_report = time.monotonic()
    errors = 0
    consecutive = 0
    max_consecutive = int(2 * args.fps)  # about 2 s of failed reads: leader is gone
    try:
        while True:
            try:
                action = leader.get_action()
            except Exception as err:  # noqa: BLE001 - keep streaming through bus glitches
                errors += 1
                consecutive += 1
                if consecutive == 1:
                    log.warning("read failed: %s", err)
                if consecutive >= max_consecutive:
                    log.error("%d reads failed in a row; stopping (follower holds)", consecutive)
                    break
            else:
                consecutive = 0
                now_ms = int(time.time() * 1000)
                frame = arm_stream.encode_frame(args.side, session, seq, now_ms, action)
                try:
                    sock.sendto(frame, target)
                except OSError as err:
                    log.warning("send failed: %s", err)
                seq += 1
            if time.monotonic() - last_report >= 10:
                last_report = time.monotonic()
                log.info("sent %d frames, %d read errors", seq, errors)
            next_t += period
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.perf_counter()
    except KeyboardInterrupt:
        log.info("stopped by user")
    finally:
        leader.disconnect()
        log.info("leader disconnected (%d frames sent)", seq)


if __name__ == "__main__":
    main()
