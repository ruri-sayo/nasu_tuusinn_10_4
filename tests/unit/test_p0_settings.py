"""Implementation-aware tests for the 2026-10-05 P0 changes (rehearsal fixes).

Written alongside the implementation before the design items had IDs, so they
are ``impl_aware`` and do not count toward coverage of the specification.
"""

import pytest

from nasura_comm.config import build_config_json, parse_args

pytestmark = pytest.mark.impl_aware()


def test_yaw_offset_default_and_override():
    assert build_config_json(parse_args([]))["view"] == {"yaw_offset_deg": 0.0}
    cfg = build_config_json(parse_args(["--yaw-offset-deg", "-12.5"]))
    assert cfg["view"]["yaw_offset_deg"] == -12.5
