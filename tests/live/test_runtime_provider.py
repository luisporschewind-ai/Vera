import os

import pytest


@pytest.mark.live
def test_runtime_provider_requires_explicit_authorization() -> None:
    if not all(
        os.environ.get(name)
        for name in (
            "VERA_LIVE_PROVIDER",
            "VERA_LIVE_BASE_URL",
            "VERA_LIVE_MODEL",
            "VERA_LIVE_API_KEY",
        )
    ):
        pytest.skip("live provider and API key are not explicitly configured")
