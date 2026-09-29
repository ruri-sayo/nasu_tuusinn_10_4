"""Pytest fixtures for the F-001 system/E2E tests.

Responsibilities:
    - Expose the process/observer fixtures defined in ``e2elib`` to the test modules.

Non-responsibilities:
    - Holds no logic of its own; helpers live in ``e2elib`` (a distinct module name so it
      never clashes with other test directories' ``conftest`` modules).
"""

from e2elib import system, udp_out, workdir

__all__ = ["system", "udp_out", "workdir"]
