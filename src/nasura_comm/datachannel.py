"""S3 DataChannel helpers (DD-0010).

Responsibilities:
    - Define the options of the ``ctrl`` and ``rel`` channels.
    - Provide a small wrapper that sends envelopes on the channel declared in
      the topic registry.

Non-responsibilities:
    - Connection lifecycle and reconnection (``hub`` / ``car`` entry points).
"""

from __future__ import annotations

import logging
from typing import Any

from nasura_comm import topics
from nasura_comm.envelope import Envelope, encode

log = logging.getLogger(__name__)

CHANNELS = ("ctrl", "rel")


def channel_options(name: str) -> dict[str, Any]:
    """Return aiortc ``createDataChannel`` keyword options for ``name``.

    ``ctrl`` is unordered with no retransmission (latest value only);
    ``rel`` is ordered and reliable.

    Raises:
        ValueError: For unknown channel names.
    """
    if name == "ctrl":
        return {"ordered": False, "maxRetransmits": 0}
    if name == "rel":
        return {"ordered": True}
    raise ValueError(f"unknown channel: {name}")


class ChannelPair:
    """The two S3 channels of one peer connection.

    Side Effects:
        ``send`` writes to the WebRTC DataChannel (network).
    """

    def __init__(self, registry: topics.Registry | None = None) -> None:
        """Start with no open channels."""
        self._registry = registry or topics.DEFAULT
        self.channels: dict[str, Any] = {}

    def attach(self, channel: Any) -> None:
        """Register an aiortc ``RTCDataChannel`` by its label."""
        if channel.label in CHANNELS:
            self.channels[channel.label] = channel

    def is_open(self) -> bool:
        """Return True if both channels are open."""
        return all(
            name in self.channels and self.channels[name].readyState == "open" for name in CHANNELS
        )

    def send(self, env: Envelope, channel: str | None = None) -> bool:
        """Send ``env`` on ``channel`` or the channel registered for its topic.

        Returns:
            False if the channel is not open (the message is dropped).
        """
        if channel is None:
            spec = self._registry.lookup(env["topic"])
            channel = spec.channel if spec is not None else "rel"
        ch = self.channels.get(channel)
        if ch is None or ch.readyState != "open":
            return False
        ch.send(encode(env))
        return True
