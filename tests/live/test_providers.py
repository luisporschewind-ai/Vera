import os

import pytest


@pytest.mark.live
def test_explicit_live_provider_smoke() -> None:
    if not all(
        os.environ.get(name)
        for name in ("VERA_LIVE_PROVIDER", "VERA_LIVE_BASE_URL", "VERA_LIVE_MODEL")
    ):
        pytest.skip("live provider is not explicitly configured")
