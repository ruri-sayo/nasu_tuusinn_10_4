"""JSON Lines event log (DD-0016).

Responsibilities:
    - Append structured events to ``logs/<node>-<start time>.jsonl``.
    - Mirror standard ``logging`` records into the same file.

Non-responsibilities:
    - Deciding what to log (callers log state transitions, not every command).

Side Effects:
    Creates the log directory and writes a file.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, TextIO


class EventLog:
    """Append-only JSON Lines writer for one node process."""

    def __init__(self, node: str, directory: str | Path = "logs") -> None:
        """Open ``<directory>/<node>-<YYYYmmdd-HHMMSS>.jsonl`` for appending."""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = path / f"{node}-{stamp}.jsonl"
        self.node = node
        self._fp: TextIO = self.path.open("a", encoding="utf-8")

    def event(self, kind: str, **fields: Any) -> None:
        """Write one event with the current epoch ms."""
        rec = {"t": int(time.time() * 1000), "node": self.node, "event": kind, **fields}
        self._fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._fp.flush()

    def close(self) -> None:
        """Close the file."""
        self._fp.close()


class _Handler(logging.Handler):
    def __init__(self, log: EventLog) -> None:
        super().__init__(logging.INFO)
        self._log = log

    def emit(self, record: logging.LogRecord) -> None:
        self._log.event("log", level=record.levelname, logger=record.name, msg=record.getMessage())


def setup(node: str, directory: str | Path = "logs", verbose: bool = False) -> EventLog:
    """Configure console logging and a JSON Lines event log for ``node``."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=f"%(asctime)s {node} %(levelname)s %(name)s: %(message)s",
    )
    ev = EventLog(node, directory)
    logging.getLogger("nasura_comm").addHandler(_Handler(ev))
    for noisy in ("aioice", "aiortc", "aiohttp.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return ev
