"""Entry point: ``python -m nasura_comm.hub``.

Responsibilities:
    - Parse CLI options, set up logging and run the hub server.

Side Effects:
    Listens on the configured TCP port and writes logs under ``--log-dir``.
"""

from __future__ import annotations

import logging

from aiohttp import web

from nasura_comm import log as nlog
from nasura_comm.config import parse_args
from nasura_comm.hub.app import create_app, self_signed_context


def main(argv: list[str] | None = None) -> None:
    """Run the hub until interrupted."""
    cfg = parse_args(argv)
    events = nlog.setup("hub", cfg.log_dir)
    ssl_ctx = self_signed_context() if cfg.tls_self_signed else None
    scheme = "https" if ssl_ctx else "http"
    logging.getLogger("nasura_comm").info("hub on %s://%s:%d/", scheme, cfg.bind, cfg.port)
    web.run_app(
        create_app(cfg, events), host=cfg.bind, port=cfg.port, ssl_context=ssl_ctx, print=None
    )


if __name__ == "__main__":
    main()
