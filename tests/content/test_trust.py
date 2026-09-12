from vera.content.trust import (
    ContentTrustLevel,
    coerce_trust_level,
    default_trust_level,
    lowest_trust,
    normalize_origin,
    source_kind_for_path,
)


def test_path_source_kind_distinguishes_guidance() -> None:
    assert source_kind_for_path("AGENTS.md") == "project_guidance"
    assert source_kind_for_path("docs/README.md") == "project_guidance"
    assert source_kind_for_path("src/main.swift") == "workspace_file"


def test_lowest_trust_never_promotes() -> None:
    assert lowest_trust(ContentTrustLevel.USER_INTENT, ContentTrustLevel.UNTRUSTED) is (
        ContentTrustLevel.UNTRUSTED
    )
    assert lowest_trust(ContentTrustLevel.ADVISORY, ContentTrustLevel.USER_INTENT) is (
        ContentTrustLevel.ADVISORY
    )
    assert lowest_trust() is ContentTrustLevel.UNTRUSTED


def test_coerce_trust_refuses_elevation() -> None:
    assert default_trust_level("user_goal") is ContentTrustLevel.USER_INTENT
    assert (
        coerce_trust_level("user_intent", source_kind="workspace_file")
        is ContentTrustLevel.UNTRUSTED
    )
    assert (
        coerce_trust_level("advisory", source_kind="workspace_file") is ContentTrustLevel.UNTRUSTED
    )
    assert coerce_trust_level("nope", source_kind="user_goal") is ContentTrustLevel.UNTRUSTED
    assert normalize_origin(" ./README.md ") == "README.md"
    assert normalize_origin("") == "unknown"
