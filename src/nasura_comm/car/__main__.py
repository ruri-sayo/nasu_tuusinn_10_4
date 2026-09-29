"""Entry point: ``python -m nasura_comm.car``.

Responsibilities:
    - Parse CLI options, set up logging and run car_ctrl.

Side Effects:
    See ``nasura_comm.car.app`` (network, UDP, log files).
"""

from __future__ import annotations

import asyncio
import contextlib

from nasura_comm import log as nlog
from nasura_comm.car.app import amain, parse_args


def main(argv: list[str] | None = None) -> None:
    """Run car_ctrl until interrupted."""
    args = parse_args(argv)
    events = nlog.setup("car_ctrl", args.log_dir)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(amain(args, events))


if __name__ == "__main__":
    main()
