"""Explicit user setup for the shared Core sandbox backend."""

import os
from pathlib import Path
from typing import Annotated

import typer

from vera.sandbox.backend import SRT_VERSION
from vera.sandbox.settings import SandboxSettings, settings_path

sandbox_app = typer.Typer(help="inspect and approve sandbox base permissions")


@sandbox_app.command("setup")
def setup(
    runtime_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    node: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    read_root: Annotated[
        list[Path] | None, typer.Option(help="Additional exact read-only toolchain path")
    ] = None,
    list_directory: Annotated[
        list[Path] | None,
        typer.Option(
            exists=True,
            file_okay=False,
            help="List only this directory node; no child file contents",
        ),
    ] = None,
    git_executable: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            help="Explicit native Git executable; exact read-only grant",
        ),
    ] = None,
    developer_dir: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            help="Selected Apple Developer directory; requires an approved read root",
        ),
    ] = None,
) -> None:
    """Display the complete base scope before saving it to private user settings."""
    import json

    metadata = json.loads((runtime_root / "package.json").read_text(encoding="utf-8"))
    if (
        metadata.get("name") != "@anthropic-ai/sandbox-runtime"
        or metadata.get("version") != SRT_VERSION
    ):
        raise typer.BadParameter(f"requires @anthropic-ai/sandbox-runtime@{SRT_VERSION}")
    base = tuple(
        Path(value)
        for value in (
            "/System",
            "/usr/lib",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            "/dev/null",
            "/dev/urandom",
            "/dev/random",
            "/private/var/select/sh",
        )
    ) + tuple(path.resolve() for path in (read_root or []))
    selected_git = git_executable.resolve() if git_executable is not None else None
    if selected_git is not None:
        if not os.access(selected_git, os.X_OK):
            raise typer.BadParameter("Git executable must be executable")
        base = (*base, selected_git)
    for path in base:
        if path == Path("/") or path == Path.home() or path in Path.home().parents:
            raise typer.BadParameter("filesystem root and whole user home are not base permissions")
    config = SandboxSettings(
        runtime_root=runtime_root.resolve(),
        node=node.resolve(),
        base_readable=base,
        directory_listable=tuple(path.resolve() for path in (list_directory or [])),
        git_executable=selected_git,
        developer_dir=developer_dir.resolve() if developer_dir is not None else None,
    )
    if config.developer_dir is not None and not any(
        config.developer_dir.is_relative_to(root.resolve()) for root in base
    ):
        raise typer.BadParameter("Developer directory requires an explicit --read-root grant")
    typer.echo("项目命令及后代：默认禁网；只读基础运行路径如下。工作区和单独批准的文件另计。")
    typer.echo("系统路径别名 /tmp、/var、/etc：仅链接元数据，不开放目标内容。")
    typer.echo("每次执行使用独立 HOME、系统临时和缓存子目录；清理失败会明确报告。")
    typer.echo("directory_listable 仅允许读取指定目录中的名称，不递归开放子目录或文件内容。")
    typer.echo(config.model_dump_json(indent=2))
    typer.echo("此后端目前仅有 Intel macOS 的基础边界试验记录；工具链和 arm64 尚未验收。")
    if not typer.confirm("批准这些基础运行权限并保存到用户配置？", default=False):
        raise typer.Abort()
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(config.model_dump_json(indent=2) + "\n")
    typer.echo(f"已保存：{path}")


@sandbox_app.command("show")
def show() -> None:
    path = settings_path()
    if not path.exists():
        typer.echo("尚未配置沙盒 runtime；项目命令保持禁用（sandbox_setup_required）。")
        return
    config = SandboxSettings.model_validate_json(path.read_text(encoding="utf-8"))
    typer.echo(config.model_dump_json(indent=2))
