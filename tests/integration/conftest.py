"""Fixtures for F-001 integration tests (50-integration-test-spec.md)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from itlib import System


@pytest.fixture
async def make_system(tmp_path: Path) -> AsyncIterator[Callable[..., Any]]:
    """Factory: start hub + car_ctrl and wait until S3 is connected."""
    systems: list[System] = []

    async def _make(extra_topics: tuple[str, ...] = (), ack_delay_ms: int | None = None) -> System:
        sys_ = System(tmp_path / f"sys{len(systems)}", extra_topics)
        sys_.tmp_path.mkdir()
        systems.append(sys_)
        await sys_.open()
        await sys_.start_hub()
        await sys_.start_car(ack_delay_ms=ack_delay_ms)
        await sys_.wait_s3_connected()
        return sys_

    try:
        yield _make
    finally:
        for s in systems:
            await s.close()


@pytest.fixture
async def system(make_system: Callable[..., Any]) -> System:
    """Default system: hub + car_ctrl running with S3 connected."""
    result: System = await make_system()
    return result
