"""Print ``out/effective`` datagrams from car_ctrl (ST-0006, ST-0008).

Responsibilities:
    - Listen on the UDP out address and print one line per datagram with a
      local timestamp, state and the command values; flag gaps > 200 ms.

Side Effects:
    Binds a UDP socket (default 127.0.0.1:47001).
"""

from __future__ import annotations

import argparse
import json
import socket
import time


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="127.0.0.1:47001")
    a = ap.parse_args()
    host, port = a.addr.rsplit(":", 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, int(port)))
    last = None
    while True:
        data, _ = sock.recvfrom(65536)
        now = time.monotonic()
        gap = "" if last is None or now - last <= 0.2 else f"  GAP {int((now - last) * 1000)} ms"
        last = now
        p = json.loads(data)["payload"]
        d, st = p["drive"], p["stage"]
        print(
            f"{time.strftime('%H:%M:%S')}.{int(now * 1000) % 1000:03d} {p['state']:5s} "
            f"v={d['v']:+.2f} w={d['w']:+.2f} "
            f"stage=({st['x']:+.0f},{st['z']:+.2f}){gap}",
            flush=True,
        )


if __name__ == "__main__":
    main()
