"""Provider-reported cache details are optional facts, not estimates."""

from types import SimpleNamespace

import pytest

from vera.models.provider_usage import parse_provider_usage


def test_deepseek_top_level_cache_counts_are_preserved() -> None:
    usage = parse_provider_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 8,
            "total_tokens": 108,
            "prompt_cache_hit_tokens": 60,
            "prompt_cache_miss_tokens": 40,
        }
    )
    assert (usage.cache_hit_input_tokens, usage.cache_miss_input_tokens) == (60, 40)
    assert usage.input_tokens == 100


def test_openai_cached_tokens_derive_uncached_from_valid_total() -> None:
    details = SimpleNamespace(model_extra={"cached_tokens": 60})
    raw = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=8,
        total_tokens=108,
        prompt_tokens_details=details,
    )
    usage = parse_provider_usage(raw)
    assert (usage.cache_hit_input_tokens, usage.cache_miss_input_tokens) == (60, 40)


@pytest.mark.parametrize(
    "details",
    [
        {"prompt_cache_hit_tokens": True},
        {"prompt_cache_hit_tokens": -1},
        {"prompt_cache_hit_tokens": 101},
        {"prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 50},
        {"prompt_cache_miss_tokens": 40},
    ],
)
def test_invalid_or_incomplete_cache_detail_is_unknown(details: dict[str, object]) -> None:
    usage = parse_provider_usage(
        {"prompt_tokens": 100, "completion_tokens": 8, "total_tokens": 108, **details}
    )
    assert usage.input_tokens == 100
    assert usage.cache_hit_input_tokens is None
    assert usage.cache_miss_input_tokens is None


def test_total_only_provider_keeps_cache_unknown() -> None:
    usage = parse_provider_usage(
        {"prompt_tokens": 100, "completion_tokens": 8, "total_tokens": 108}
    )
    assert usage.input_tokens == 100
    assert usage.cache_hit_input_tokens is None
    assert usage.cache_miss_input_tokens is None


def test_invalid_explicit_hit_cannot_fall_back_to_other_provider_shape() -> None:
    usage = parse_provider_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 8,
            "total_tokens": 108,
            "prompt_cache_hit_tokens": True,
            "prompt_tokens_details": {"cached_tokens": 60},
        }
    )
    assert usage.cache_hit_input_tokens is None
    assert usage.cache_miss_input_tokens is None
