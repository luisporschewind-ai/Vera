"""Normalize provider usage while treating cache details as optional facts."""

from __future__ import annotations

from vera.models.base import ModelUsage


def read_field(value: object, name: str) -> object:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    direct = getattr(value, name, None)
    if direct is not None:
        return direct
    extra = getattr(value, "model_extra", None) or getattr(value, "__pydantic_extra__", None)
    if isinstance(extra, dict):
        return extra.get(name)
    return None


def nonnegative_int(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def parse_provider_usage(value: object) -> ModelUsage:
    input_count = nonnegative_int(read_field(value, "prompt_tokens"))
    output_count = nonnegative_int(read_field(value, "completion_tokens"))
    total_count = nonnegative_int(read_field(value, "total_tokens"))
    raw_hit = read_field(value, "prompt_cache_hit_tokens")
    hit = nonnegative_int(raw_hit)
    miss = nonnegative_int(read_field(value, "prompt_cache_miss_tokens"))
    if raw_hit is not None and hit is None:
        return ModelUsage(
            input_tokens=input_count,
            output_tokens=output_count,
            total_tokens=total_count,
        )
    if raw_hit is None:
        details = read_field(value, "prompt_tokens_details")
        hit = nonnegative_int(read_field(details, "cached_tokens"))
    if input_count is None or hit is None or hit > input_count:
        hit = miss = None
    elif miss is None:
        if read_field(value, "prompt_cache_miss_tokens") is not None:
            hit = miss = None
        else:
            miss = input_count - hit
    elif hit + miss != input_count:
        hit = miss = None
    return ModelUsage(
        input_tokens=input_count,
        output_tokens=output_count,
        total_tokens=total_count,
        cache_hit_input_tokens=hit,
        cache_miss_input_tokens=miss,
    )
