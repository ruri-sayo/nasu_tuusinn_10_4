"""Clock helpers for the I/O layer.

Responsibilities:
    - Provide monotonic and epoch time in integer milliseconds.

Non-responsibilities:
    - Used only by I/O modules; pure logic receives time as arguments.
"""

from __future__ import annotations

import time


def mono_ms() -> int:
    """Return monotonic time in ms (for timeouts)."""
    return time.monotonic_ns() // 1_000_000


def wall_ms() -> int:
    """Return UNIX epoch time in ms (for envelope ``ts``)."""
    return time.time_ns() // 1_000_000
