"""Versioned, non-secret candidates for user-owned model selection."""

from __future__ import annotations

from dataclasses import dataclass

from vera.config import ProviderConfig

CATALOG_VERSION = 1


@dataclass(frozen=True)
class CatalogEntry:
    profile_id: str
    provider_id: str
    display_name: str
    model_id: str
    base_url: str | None
    api_key_env: str
    output_token_parameter: str = "max_tokens"
    stream_usage_mode: str = "provider_default"

    def provider_config(self, *, base_url: str | None = None) -> ProviderConfig | None:
        endpoint = base_url or self.base_url
        if endpoint is None:
            return None
        return ProviderConfig.model_validate(
            {
                "base_url": endpoint,
                "model": self.model_id,
                "api_key_env": self.api_key_env,
                "output_token_parameter": self.output_token_parameter,
                "stream_usage_mode": self.stream_usage_mode,
            }
        )


MODEL_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "deepseek-flash",
        "deepseek",
        "DeepSeek Flash",
        "deepseek-flash",
        "https://api.deepseek.com",
        "DEEPSEEK_API_KEY",
    ),
    CatalogEntry("glm-4.6", "glm", "GLM 4.6", "glm-4.6", None, "GLM_API_KEY"),
    CatalogEntry(
        "openai-gpt-4.1-mini",
        "openai",
        "GPT-4.1 mini",
        "gpt-4.1-mini",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        "max_completion_tokens",
        "include_usage",
    ),
    CatalogEntry(
        "openai-gpt-4.1",
        "openai",
        "GPT-4.1",
        "gpt-4.1",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        "max_completion_tokens",
        "include_usage",
    ),
)

CATALOG_BY_ID = {item.profile_id: item for item in MODEL_CATALOG}

GLM_ENDPOINTS = {
    "china": "https://open.bigmodel.cn/api/paas/v4/",
    "international": "https://api.z.ai/api/paas/v4/",
}
