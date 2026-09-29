"""Car-side local I/O (DD-0007).

Responsibilities:
    - Build the ``out/effective`` envelope for the downstream UDP interface.
    - Gate local telemetry datagrams (validate, check registry, rate limit)
      before they are forwarded to the hub.
    - Provide asyncio UDP endpoints for UDP out (127.0.0.1:47001) and
      UDP in (127.0.0.1:47002).

Non-responsibilities:
    - Deciding the effective command (``safety``).
    - Driving hardware: downstream adapters consume ``out/effective``.

Downstream interface contract:
    Receivers of ``out/effective`` must stop when 200 ms pass without a
    datagram, or when ``payload.state != "RUN"``.

Side Effects:
    ``UdpOut`` sends UDP datagrams; ``open_udp_in`` binds a UDP socket.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Callable
from typing import Any

from nasura_comm import topics
from nasura_comm.envelope import Envelope, decode, encode, make
from nasura_comm.filters import RateLimiter
from nasura_comm.safety import stop_effective

__all__ = ["TelemetryGate", "UdpOut", "build_effective", "open_udp_in", "stop_effective"]

log = logging.getLogger(__name__)

UDP_OUT_ADDR = ("127.0.0.1", 47001)
UDP_IN_ADDR = ("127.0.0.1", 47002)
UDP_OUT_PERIOD_MS = 50


def build_effective(state: str, eff: dict[str, Any], seq: int, ts: int) -> Envelope:
    """Build the ``out/effective`` envelope from a state and effective command."""
    payload = {"state": state, "drive": eff["drive"], "arm": eff["arm"], "stage": eff["stage"]}
    return make("out/effective", payload, "car_ctrl", seq, ts)


class TelemetryGate:
    """Decide whether a local datagram is forwarded to the hub.

    State:
        ``dropped`` counts discarded datagrams by reason key: ``invalid``,
        ``<topic>`` (unregistered, fixed, wrong direction or newer ver) and
        ``rate:<topic>``.
    """

    def __init__(self, registry: topics.Registry | None = None) -> None:
        """Use ``registry`` (default: the default registry)."""
        self._registry = registry or topics.DEFAULT
        self._rate = RateLimiter(self._registry)
        self.dropped: Counter[str] = Counter()

    def _drop(self, key: str) -> None:
        if key not in self.dropped:
            log.warning("dropping local datagram: %s", key)
        self.dropped[key] += 1

    def check(self, data: bytes, now_ms: int) -> tuple[str, Envelope] | None:
        """Validate one datagram at ``now_ms`` (monotonic ms).

        Returns:
            ``(channel, envelope)`` to forward, with ``src`` replaced by
            ``car_local``; or ``None`` if dropped.
        """
        env = decode(data)
        if env is None:
            self._drop("invalid")
            return None
        topic = env["topic"]
        spec = self._registry.lookup(topic)
        if spec is None or spec.fixed or spec.direction != "up" or env["ver"] > spec.ver:
            self._drop(topic)
            return None
        if not self._rate.allow(topic, now_ms):
            self._drop("rate:" + topic)
            return None
        env["src"] = "car_local"
        return spec.channel, env


class UdpOut:
    """Fire-and-forget UDP sender for ``out/effective``.

    Side Effects:
        Sends UDP datagrams to ``addr``.
    """

    def __init__(self, transport: asyncio.DatagramTransport, addr: tuple[str, int]) -> None:
        """Wrap an unconnected datagram transport."""
        self._transport = transport
        self._addr = addr

    @classmethod
    async def open(cls, addr: tuple[str, int] = UDP_OUT_ADDR) -> UdpOut:
        """Create the sending endpoint."""
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        return cls(transport, addr)

    def send(self, env: Envelope) -> None:
        """Send one envelope as one datagram."""
        self._transport.sendto(encode(env).encode(), self._addr)

    def close(self) -> None:
        """Close the socket."""
        self._transport.close()


class _InProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_data: Callable[[bytes], None]) -> None:
        self._on_data = on_data

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._on_data(data)


async def open_udp_in(
    on_data: Callable[[bytes], None], addr: tuple[str, int] = UDP_IN_ADDR
) -> asyncio.DatagramTransport:
    """Bind the telemetry input socket and call ``on_data`` per datagram.

    Side Effects:
        Binds a UDP socket on ``addr``.
    """
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _InProtocol(on_data), local_addr=addr
    )
    return transport
