"""Sequence and rate filters (DD-0003).

Responsibilities:
    - Drop stale or duplicate messages on the unordered ``ctrl`` channel.
    - Limit per-topic rates according to the topic registry.

Non-responsibilities:
    - Reading clocks: callers pass ``now_ms`` (monotonic milliseconds).
"""

from __future__ import annotations

from nasura_comm import topics

SEQ_RESET_GAP = 1000
"""A sequence number this far below the last one is taken as a sender restart."""


class SeqFilter:
    """Keep the highest seq seen per (src, topic) and reject older ones."""

    def __init__(self) -> None:
        """Create an empty filter."""
        self._last: dict[tuple[str, str], int] = {}

    def accept(self, src: str, topic: str, seq: int) -> bool:
        """Return True if ``seq`` is newer than the last accepted one.

        ``seq < last - 1000`` is treated as a sender restart and accepted.
        """
        key = (src, topic)
        last = self._last.get(key)
        if last is None or seq > last or seq < last - SEQ_RESET_GAP:
            self._last[key] = seq
            return True
        return False


JITTER_TOLERANCE = 0.2
"""Fraction of the interval a message may arrive early (sender clock jitter)."""


class RateLimiter:
    """Enforce ``max_rate_hz`` per topic.

    Uses a virtual schedule (GCRA): each allowed message advances the next
    due time by ``1000 / hz`` ms, and a message may arrive up to 20 % of the
    interval early. A sender at exactly the declared rate is not thinned by
    jitter, while the long-run rate stays at ``max_rate_hz``.
    """

    def __init__(self, registry: topics.Registry | None = None) -> None:
        """Use ``registry`` (default: the default registry) for rates."""
        self._registry = registry or topics.DEFAULT
        self._due: dict[str, float] = {}

    def allow(self, topic: str, now_ms: int) -> bool:
        """Return True if ``topic`` may pass at ``now_ms`` (monotonic ms).

        Unregistered topics and topics without ``max_rate_hz`` always pass.
        """
        spec = self._registry.lookup(topic)
        if spec is None or spec.max_rate_hz is None:
            return True
        interval = 1000.0 / spec.max_rate_hz
        due = self._due.get(topic)
        if due is not None and now_ms < due - interval * JITTER_TOLERANCE:
            return False
        self._due[topic] = max(due if due is not None else now_ms, now_ms) + interval
        return True
