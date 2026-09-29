"""Send test telemetry envelopes to car_ctrl's UDP in (DD-0015).

Responsibilities:
    - Emit envelopes of an arbitrary topic at an arbitrary rate for testing
      the telemetry path (ST-0013, IT-0004).

Side Effects:
    Sends UDP datagrams to the given address.

Usage:
    uv run python scripts/fake_telemetry.py tlm/test_value --hz 5 --seconds 10
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import time


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--hz", type=float, default=5.0)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--addr", default="127.0.0.1:47002")
    ap.add_argument("--src", default="fake_telemetry")
    a = ap.parse_args()
    host, port = a.addr.rsplit(":", 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.monotonic()
    seq = 0
    while (t := time.monotonic() - start) < a.seconds:
        payload = {"value": round(math.sin(t), 3)}
        env = {
            "topic": a.topic,
            "ver": 1,
            "seq": seq,
            "ts": int(time.time() * 1000),
            "src": a.src,
            "payload": payload,
        }
        sock.sendto(json.dumps(env, separators=(",", ":")).encode(), (host, int(port)))
        seq += 1
        time.sleep(1.0 / a.hz)
    print(f"sent {seq} datagrams of {a.topic}")


if __name__ == "__main__":
    main()
