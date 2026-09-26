"""CLI projection of the Core model configuration service."""

from __future__ import annotations

import sys

import typer

from vera.config import ConfigurationError, ProviderConfig, load_user_providers
from vera.provider_catalog import CATALOG_BY_ID, GLM_ENDPOINTS
from vera.provider_configuration import ProviderConfigurationService
from vera.provider_credentials import set_provider_key

models_app = typer.Typer(help="configure user-owned model profiles")
key_app = typer.Typer(help="manage private provider keys")
models_app.add_typer(key_app, name="key")


def _service() -> ProviderConfigurationService:
    return ProviderConfigurationService()


def _fail(exc: Exception) -> None:
    if isinstance(exc, ConfigurationError):
        typer.echo(str(exc), err=True)
    else:
        typer.echo("invalid model configuration", err=True)
    raise typer.Exit(5) from exc


def _require_tty() -> None:
    if not sys.stdin.isatty():
        _fail(ConfigurationError("key_input_requires_tty", "model setup requires a terminal"))


@models_app.command("list")
def list_models() -> None:
    try:
        summaries = _service().list_profiles_with_keys(load_user_providers())
    except Exception as exc:
        _fail(exc)
    for item in summaries:
        flags = ["enabled" if item.enabled else "disabled"]
        if item.default:
            flags.append("default")
        typer.echo(
            f"{item.profile_id}\t{item.display_name}\t{','.join(flags)}"
            f"\t{item.key_status}\t{item.reason or 'ready'}"
        )


@models_app.command("enable")
def enable(profile_id: str) -> None:
    try:
        _service().enable(profile_id)
    except Exception as exc:
        _fail(exc)
    typer.echo(f"enabled {profile_id}")


@models_app.command("disable")
def disable(profile_id: str) -> None:
    try:
        _service().disable(profile_id)
    except Exception as exc:
        _fail(exc)
    typer.echo(f"disabled {profile_id}")


@models_app.command("move")
def move(profile_id: str, before: str = typer.Option(..., "--before")) -> None:
    try:
        _service().move_before(profile_id, before)
    except Exception as exc:
        _fail(exc)
    typer.echo(f"moved {profile_id}")


@models_app.command("default")
def select_default(profile_id: str) -> None:
    try:
        _service().set_default(profile_id)
    except Exception as exc:
        _fail(exc)
    typer.echo(f"default {profile_id}")


@key_app.command("set")
def key_set(profile_id: str) -> None:
    _require_tty()
    try:
        profile = next(
            item
            for item in _service().list_profiles_with_keys(load_user_providers())
            if item.profile_id == profile_id
        )
    except StopIteration:
        _fail(ConfigurationError("unknown_model_profile", "model profile is unknown"))
    try:
        value = typer.prompt("API Key", hide_input=True, confirmation_prompt=True)
        set_provider_key(profile.api_key_env, value)
    except Exception as exc:
        _fail(exc)
    typer.echo("Key: configured")


@models_app.command("setup")
def setup() -> None:
    _require_tty()
    service = _service()
    typer.echo("模型目录：")
    for item in service.list_profiles():
        typer.echo(f"  {item.profile_id}: {item.display_name}")
    profile_id = typer.prompt("Profile ID（输入 custom 新建）").strip()
    if profile_id == "custom":
        profile_id = typer.prompt("新 Profile ID").strip()
        endpoint = typer.prompt("HTTPS endpoint").strip()
        model = typer.prompt("Model ID").strip()
        key_env = typer.prompt("Key 环境变量名").strip()
        token_param = typer.prompt("输出 token 参数", default="max_tokens").strip()
        usage_mode = typer.prompt("流式用量模式", default="provider_default").strip()
        try:
            profile = ProviderConfig.model_validate(
                {
                    "base_url": endpoint,
                    "model": model,
                    "api_key_env": key_env,
                    "output_token_parameter": token_param,
                    "stream_usage_mode": usage_mode,
                }
            )
        except Exception as exc:
            _fail(exc)
        typer.echo(
            f"Profile {profile_id}: {profile.model} @ {profile.base_url};"
            f" Key ref {profile.api_key_env}"
        )
        if not typer.confirm("保存该 Profile？"):
            raise typer.Exit(2)
        try:
            service.add_custom(profile, profile_id)
        except Exception as exc:
            _fail(exc)
    elif profile_id in CATALOG_BY_ID:
        entry = CATALOG_BY_ID[profile_id]
        if entry.provider_id == "glm":
            region = typer.prompt("GLM 账号区域（china/international）").strip()
            endpoint = GLM_ENDPOINTS.get(region)
            if endpoint is None:
                _fail(ConfigurationError("invalid_glm_region", "select china or international"))
            glm_profile = entry.provider_config(base_url=endpoint)
            assert glm_profile is not None
            typer.echo(
                f"Profile {profile_id}: {glm_profile.model} @ {glm_profile.base_url};"
                f" Key ref {glm_profile.api_key_env}"
            )
            if not typer.confirm("保存该 endpoint？"):
                raise typer.Exit(2)
            service.configure_catalog(profile_id, glm_profile)
        else:
            typer.echo(
                f"Profile {profile_id}: {entry.model_id} @ {entry.base_url};"
                f" Key ref {entry.api_key_env}"
            )
            if not typer.confirm("启用该 Profile？"):
                raise typer.Exit(2)
    else:
        _fail(ConfigurationError("unknown_model_profile", "model profile is unknown"))
    try:
        service.enable(profile_id)
        if typer.confirm("设为默认模型？", default=False):
            service.set_default(profile_id)
        if typer.confirm("现在设置 API Key？", default=True):
            key_set(profile_id)
    except Exception as exc:
        _fail(exc)
    typer.echo(f"configured {profile_id}")
