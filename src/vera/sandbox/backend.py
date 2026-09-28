"""Fixed-version SRT adapter. Only the trusted Core constructs permissions."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from vera.process.supervisor import ProcessRequest
from vera.sandbox.access import FilePermissions, ResourceIdentity
from vera.sandbox.apple_services import APPLE_IOS_BUILD_SERVICES, requests_approved_ios_build
from vera.sandbox.apple_volume import AppleVolumeError, apple_build_volume

SRT_VERSION = "0.0.77"


class SandboxError(ValueError):
    """Stable, content-free failure code suitable for a tool result."""


class SandboxCleanupError(SandboxError):
    """Execution may have finished; never report this as a launch failure."""

    def __init__(self, root: Path, reason: str = "cleanup_failed") -> None:
        self.reason = reason
        super().__init__(f"sandbox_cleanup_failed: {root}; {reason}; execution may have occurred")


@contextmanager
def _command_directory(parent: Path, cache_parent: Path) -> Iterator[tuple[Path, Path]]:
    # Foundation insists on T/<suffix>. Point that path at a nested private
    # directory: macOS can protect T/<suffix>/TemporaryItems against removal,
    # while the same contents under the nested directory remain removable.
    container = Path(tempfile.mkdtemp(prefix="vera-scratch-", dir=parent)).resolve()
    root = container
    link: Path | None = None
    cache: Path | None = None
    link_created = False
    cache_created = False
    try:
        root = Path(tempfile.mkdtemp(prefix="vera-command-", dir=container)).resolve()
        link = parent / root.name
        cache = cache_parent / root.name
        link.symlink_to(root, target_is_directory=True)
        link_created = True
        cache.mkdir(mode=0o700)
        cache_created = True
        yield root, cache
    finally:
        active_error = sys.exc_info()[1]
        failures: list[Path] = []
        if cache_created and cache is not None:
            try:
                shutil.rmtree(cache)
            except FileNotFoundError:
                pass
            except OSError:
                if cache.exists():
                    failures.append(cache)
        if link_created and link is not None:
            try:
                link.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                if link.exists() or link.is_symlink():
                    failures.append(link)
        try:
            shutil.rmtree(container)
        except FileNotFoundError:
            pass
        except OSError:
            if container.exists():
                failures.append(container)
        if failures:
            reason = getattr(active_error, "reason", "cleanup_failed")
            raise SandboxCleanupError(failures[0], reason)


def isolated_environment(
    source: Mapping[str, str],
    scratch: Path,
    *,
    git_executable: Path | None = None,
    writable_roots: tuple[Path, ...] = (),
) -> dict[str, str]:
    # Do not inherit PATH, loader hooks, shell startup, proxy or provider variables.
    result = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"),
        "XDG_CACHE_HOME": str(scratch / "cache"),
        "XDG_CONFIG_HOME": str(scratch / "home" / ".config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "LC_ALL": "C",
        "CFFIXED_USER_HOME": str(scratch / "home"),
        "xcrun_db": str(scratch / "cache" / "xcrun"),
        "CLANG_MODULE_CACHE_PATH": str(scratch / "cache" / "clang"),
        "SWIFTPM_MODULECACHE_OVERRIDE": str(scratch / "cache" / "swift"),
        "DIRHELPER_USER_DIR_SUFFIX": scratch.name,
    }
    if git_executable is not None:
        # Git discovery itself spawns Git. Select the same approved binary for
        # descendants; this PATH entry does not grant access to sibling files.
        result["PATH"] = f"{git_executable.parent}:{result['PATH']}"
    # Exact Git identity is an explicit native-Git input, not ambient credentials.
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        if name in source:
            result[name] = source[name]
    for name, value in {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
    }.items():
        if source.get(name) == value:
            result[name] = value
    for name in ("COVERAGE_FILE", "CLANG_MODULE_CACHE_PATH", "SWIFTPM_MODULECACHE_OVERRIDE"):
        raw_value = source.get(name)
        if raw_value and Path(raw_value).is_absolute():
            path = Path(raw_value).resolve()
            if any(path.is_relative_to(root.resolve()) for root in writable_roots):
                result[name] = str(path)
    return result


def _path(path: Path) -> str:
    value = str(path.resolve())
    # SRT treats these as patterns. Never let a literal grant become a glob.
    if any(char in value for char in "*?[]{}\x00\n\r"):
        raise SandboxError("sandbox_path_unsupported")
    return value


def build_payload(
    request: ProcessRequest,
    permissions: FilePermissions,
    *,
    base_readable: tuple[Path, ...],
    scratch: Path,
) -> dict[str, Any]:
    permissions.validate()
    cwd = request.cwd.resolve()
    if not any(
        cwd == root.resolve() or root.resolve() in cwd.parents for root in permissions.writable
    ):
        raise SandboxError("sandbox_cwd_denied")
    if not request.argv or any("\x00" in part for part in request.argv):
        raise SandboxError("sandbox_invalid_argv")
    roots = (*base_readable, *permissions.readable, *permissions.writable)
    if any(path.resolve() != path for path in (*permissions.readable, *permissions.writable)):
        raise SandboxError("resource_changed")
    if any(root.resolve() == Path("/") for root in roots):
        raise SandboxError("sandbox_root_forbidden")
    private = [_path(path) for path in permissions.private_roots]
    for root in roots:
        if any(
            root.resolve() == path.resolve() or path.resolve() in root.resolve().parents
            for path in permissions.private_roots
        ):
            raise SandboxError("sandbox_private_resource")
    return {
        "argv": list(request.argv),
        "allowMachLookup": (
            list(APPLE_IOS_BUILD_SERVICES) if request.apple_ios_build_services else []
        ),
        "darwinUserDirSuffix": scratch.name,
        "needsNetworkRestriction": True,
        "readConfig": {
            "denyOnly": [
                "/",
                *private,
                "/**/.env",
                "/**/.npmrc",
                "/**/.pypirc",
                "/**/credentials",
                "/**/*.pem",
                "/**/*.key",
                "/**/*.p12",
            ],
            "allowWithinDeny": [_path(path) for path in (*roots, scratch)],
        },
        "writeConfig": {
            "allowOnly": [_path(path) for path in (*permissions.writable, scratch)],
            "denyWithinAllow": private,
        },
    }


def decode_wrapper(payload: str) -> tuple[str, ...]:
    try:
        value = json.loads(payload)
        command = value["command"]
        argv = shlex.split(command)
        index = argv.index("/usr/bin/sandbox-exec")
        if argv[0] != "env" or index < 1 or len(argv) != index + 6:
            raise ValueError
        # No env options, PATH overrides or injected loader configuration.
        for assignment in argv[1:index]:
            if not re.fullmatch(r"(?:TMPDIR|SANDBOX_RUNTIME)=[^\x00]*", assignment):
                raise ValueError
        if argv[index + 1] != "-p" or argv[index + 3 : index + 5] != ["/bin/bash", "-c"]:
            raise ValueError
        profile = argv[index + 2]
        if "(version 1)" not in profile or "(deny default" not in profile:
            raise ValueError
        # SRT's proxy helper emits a shared /tmp/claude. Keep our private TMPDIR.
        return (
            "/usr/bin/env",
            *(item for item in argv[1:index] if not item.startswith("TMPDIR=")),
            *argv[index:],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SandboxError("sandbox_invalid_wrapper") from exc


class SrtBackend:
    """No discovery through the project, automatic install, or unconfined fallback.

    runtime_root and base_readable must come from approved user-level settings.
    The runtime is trusted executable code and must be outside command write roots.
    """

    def __init__(
        self,
        *,
        runtime_root: Path,
        base_readable: tuple[Path, ...],
        node: Path = Path("/usr/local/bin/node"),
        git_executable: Path | None = None,
        developer_dir: Path | None = None,
        directory_listable: tuple[Path, ...] = (),
    ) -> None:
        self.runtime_root = runtime_root.resolve()
        self.base_readable = base_readable
        self.directory_listable = directory_listable
        self.node = node.resolve()
        self.git_executable = git_executable.resolve() if git_executable is not None else None
        self.developer_dir = developer_dir.resolve() if developer_dir is not None else None

    def toolchain_environment(self, permissions: FilePermissions) -> dict[str, str]:
        developer = self.developer_dir
        if developer is None:
            return {}
        if not any(developer.is_relative_to(root.resolve()) for root in self.base_readable):
            raise SandboxError("sandbox_toolchain_not_approved")
        if any(
            developer.is_relative_to(root.resolve()) or root.resolve().is_relative_to(developer)
            for root in permissions.writable
        ):
            raise SandboxError("sandbox_runtime_writable")
        if not developer.is_dir() or developer.resolve() != developer:
            raise SandboxError("sandbox_toolchain_unavailable")
        return {"DEVELOPER_DIR": str(developer)}

    def select_git(self, request: ProcessRequest, permissions: FilePermissions) -> ProcessRequest:
        """Resolve direct Git invocations using explicit, user-approved settings.

        No shell text, project config or ambient PATH may select this executable.
        The selected file must be an exact base read grant and outside write roots.
        """
        git = self.git_executable
        if git is None:
            return request
        if ":" in str(git.parent):
            raise SandboxError("sandbox_git_invalid_path")
        if git not in self.base_readable:
            raise SandboxError("sandbox_git_not_approved")
        if any(
            git == root.resolve() or root.resolve() in git.parents for root in permissions.writable
        ):
            raise SandboxError("sandbox_runtime_writable")
        if git.resolve() != git or not git.is_file() or not os.access(git, os.X_OK):
            raise SandboxError("sandbox_git_unavailable")
        if not request.argv or request.argv[0] not in {"git", "/usr/bin/git"}:
            return request
        return replace(request, argv=(str(git), *request.argv[1:]))

    @contextmanager
    def prepare(
        self, request: ProcessRequest, permissions: FilePermissions
    ) -> Iterator[ProcessRequest]:
        if not request.apple_ios_build_services:
            with self._prepare(request, permissions) as wrapped:
                yield wrapped
            return
        if sys.platform != "darwin":
            raise SandboxError("sandbox_unsupported")
        expected = self.developer_dir / "usr/bin/xcodebuild" if self.developer_dir else None
        if (
            not requests_approved_ios_build(request.argv)
            or expected is None
            or Path(request.argv[0]).resolve() != expected.resolve()
        ):
            raise SandboxError("sandbox_apple_build_service_unsupported")
        try:
            with apple_build_volume(
                (*self.base_readable, *permissions.readable, *permissions.writable)
            ) as volume:
                effective = (
                    *request.argv[:-1],
                    "-derivedDataPath",
                    str(volume / "DerivedData"),
                    "build",
                )
                managed = replace(request, argv=effective, effective_argv=effective)
                grants = replace(
                    permissions,
                    readable=(*permissions.readable, volume),
                    writable=(*permissions.writable, volume),
                    identities=(*permissions.identities, ResourceIdentity.capture(volume)),
                )
                with self._prepare(managed, grants) as wrapped:
                    yield wrapped
        except AppleVolumeError as exc:
            if exc.cleanup:
                raise SandboxCleanupError(exc.root, "apple_build_volume_cleanup_failed") from exc
            raise SandboxError("sandbox_apple_build_volume_failed") from exc

    @contextmanager
    def _prepare(
        self, request: ProcessRequest, permissions: FilePermissions
    ) -> Iterator[ProcessRequest]:
        request = self.select_git(request, permissions)
        if request.apple_ios_build_services:
            expected_xcodebuild = (
                self.developer_dir / "usr/bin/xcodebuild"
                if self.developer_dir is not None
                else None
            )
            if (
                expected_xcodebuild is None
                or Path(request.argv[0]).resolve() != expected_xcodebuild.resolve()
            ):
                raise SandboxError("sandbox_apple_build_service_unsupported")
        package = self.runtime_root / "package.json"
        try:
            metadata = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SandboxError("sandbox_unavailable") from exc
        if (
            metadata.get("name") != "@anthropic-ai/sandbox-runtime"
            or metadata.get("version") != SRT_VERSION
        ):
            raise SandboxError("sandbox_version_mismatch")
        if sys.platform != "darwin":
            raise SandboxError("sandbox_unsupported")
        bridge = Path(__file__).with_name("srt_bridge.mjs").resolve()
        for executable in (self.runtime_root, self.node, bridge):
            if any(
                executable == root.resolve() or root.resolve() in executable.parents
                for root in permissions.writable
            ):
                raise SandboxError("sandbox_runtime_writable")
        # Foundation's temporary-directory API uses confstr rather than TMPDIR.
        # Its per-process suffix must name the very same owned directory.
        temp_value = os.confstr(65537)
        cache_value = os.confstr(65538)
        if not temp_value or not cache_value:
            raise SandboxError("sandbox_temp_unavailable")
        temp_parent = Path(temp_value).resolve()
        with _command_directory(temp_parent, Path(cache_value).resolve()) as (scratch, cache):
            permissions = replace(
                permissions,
                readable=(*permissions.readable, cache),
                writable=(*permissions.writable, cache),
                identities=(*permissions.identities, ResourceIdentity.capture(cache)),
            )
            for name in ("home", "tmp", "cache"):
                (scratch / name).mkdir(mode=0o700)
            payload = build_payload(
                request, permissions, base_readable=self.base_readable, scratch=scratch
            )
            env = isolated_environment(
                request.env,
                scratch,
                git_executable=self.git_executable,
                writable_roots=permissions.writable,
            )
            env.update(self.toolchain_environment(permissions))
            if self.developer_dir is not None:
                # ibtool otherwise starts detached pooled servers outside the
                # supervised process group. Use its direct execution mode.
                env["IBToolNeverDeque"] = "YES"
            try:
                wrapped = subprocess.run(
                    [str(self.node), str(bridge), str(self.runtime_root)],
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    timeout=10,
                    cwd=request.cwd,
                    env=env,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SandboxError("sandbox_unavailable") from exc
            if wrapped.returncode != 0 or len(wrapped.stdout) > 1_000_000:
                raise SandboxError("sandbox_initialization_failed")
            argv = decode_wrapper(wrapped.stdout)
            index = argv.index("/usr/bin/sandbox-exec") + 2
            # System aliases are symlink nodes, so SRT's DIRECTORY metadata
            # allowance does not cover them. This never grants target contents.
            rule = (
                "\n(allow file-read-metadata (require-all (vnode-type SYMLINK)"
                ' (require-any (literal "/tmp") (literal "/var") (literal "/etc"))))'
            )
            # Foundation returns T/<suffix>, which is our exact symlink node.
            # SRT's grant for scratch covers the resolved target, not the link.
            temp_alias = temp_parent / scratch.name
            rule += (
                "\n(allow file-read* (require-all"
                f" (literal {json.dumps(str(temp_alias))}) (vnode-type SYMLINK)))"
            )
            # SRT resolves read grants to their targets; macOS also reads this
            # standard shell-selector link itself. Grant only the approved link
            # inode, never a parent directory or an unapproved target.
            selector = Path("/private/var/select/sh")
            if selector in self.base_readable and selector.is_symlink():
                rule += (
                    '\n(allow file-read* (require-all (literal "/private/var/select/sh")'
                    " (vnode-type SYMLINK)))"
                )
            for directory in self.directory_listable:
                if (
                    not directory.is_absolute()
                    or not directory.is_dir()
                    or directory.resolve() != directory
                    or any(directory.is_relative_to(p.resolve()) for p in permissions.private_roots)
                ):
                    raise SandboxError("sandbox_invalid_directory_listing")
                # SRT readConfig only supports recursive grants. Directory-node
                # listing needs this literal rule; child contents stay denied.
                rule += (
                    "\n(allow file-read-data (require-all (vnode-type DIRECTORY) (literal "
                    + json.dumps(str(directory))
                    + ")))"
                )
            argv = (*argv[:index], argv[index] + rule, *argv[index + 1 :])
            permissions.validate()
            self.select_git(request, permissions)
            self.toolchain_environment(permissions)
            try:
                yield replace(request, argv=argv, env=env)
            finally:
                # macOS may reject host deletion of system-created
                # TemporaryItems. Remove only these Core-owned roots under the
                # same SRT profile while the narrow grants are still active.
                cleanup_command = (
                    "export DIRHELPER_USER_DIR_SUFFIX="
                    + shlex.quote(scratch.name)
                    + "; exec /bin/rm -rf "
                    + shlex.quote(str(cache))
                    + " "
                    + shlex.quote(str(scratch))
                )
                cleanup_argv = (*argv[:-1], cleanup_command)
                try:
                    cleaned = subprocess.run(
                        cleanup_argv,
                        cwd=request.cwd,
                        env=env,
                        capture_output=True,
                        timeout=15,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise SandboxCleanupError(scratch, "cleanup_runner_failed") from exc
                if cleaned.returncode != 0:
                    reason = (
                        "cleanup_denied"
                        if b"Operation not permitted" in cleaned.stderr
                        else "cleanup_process_failed"
                    )
                    raise SandboxCleanupError(scratch, reason)
