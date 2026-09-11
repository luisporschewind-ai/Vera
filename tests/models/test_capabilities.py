"""Model capabilities tests."""

from vera.models.capabilities import ModelCapabilities


def test_coding_capability_requires_tool_calling() -> None:
    capabilities = ModelCapabilities(tool_calling=False)
    assert capabilities.supports_request(has_tools=True) is False
    assert capabilities.supports_request(has_tools=False) is True
