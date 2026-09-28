import json
import shlex
from pathlib import Path

import pytest

from vera.process.supervisor import ProcessRequest
from vera.sandbox.access import FilePermissions


def request(root: Path) -> ProcessRequest:
    return ProcessRequest(("/bin/echo", "a 'quoted' ; $HOME\nvalue"), root, {}, 2)


@pytest.mark.parametrize("interrupt", [False, True])
def test_command_scratch_alias_and_cleanup(tmp_path: Path, interrupt: bool) -> None:
    from vera.sandbox.backend import _command_directory

    temp_parent = tmp_path / "T"
    cache_parent = tmp_path / "C"
    temp_parent.mkdir()
    cache_parent.mkdir()
    try:
        with _command_directory(temp_parent, cache_parent) as (scratch, cache):
            alias = temp_parent / scratch.name
            container = scratch.parent
            assert scratch.parent.parent == temp_parent
            assert alias.is_symlink() and alias.resolve() == scratch
            assert cache == cache_parent / scratch.name
            (alias / "TemporaryItems").mkdir()
            (alias / "TemporaryItems" / "fake").write_text("fake")
            if interrupt:
                raise RuntimeError("interrupted")
    except RuntimeError:
        assert interrupt
    assert not alias.exists() and not alias.is_symlink()
    assert not container.exists()
    assert not cache.exists()


def test_missing_runtime_fails_closed(tmp_path: Path) -> None:
    from vera.sandbox.backend import SandboxError, SrtBackend

    backend = SrtBackend(runtime_root=tmp_path / "missing", base_readable=())
    permissions = FilePermissions(tmp_path, (tmp_path,), (tmp_path,))
    with (
        pytest.raises(SandboxError, match="sandbox_unavailable"),
        backend.prepare(request(tmp_path), permissions),
    ):
        pytest.fail("must not return an unconfined command")


def test_payload_preserves_arguments_and_denies_private_state(tmp_path: Path) -> None:
    from vera.sandbox.backend import build_payload, isolated_environment

    private = tmp_path / ".vera"
    permissions = FilePermissions(tmp_path, (tmp_path,), (tmp_path,), (private,))
    payload = build_payload(
        request(tmp_path), permissions, base_readable=(), scratch=tmp_path / "s"
    )
    assert payload["argv"] == list(request(tmp_path).argv)
    assert payload["allowMachLookup"] == []
    assert payload["needsNetworkRestriction"] is True
    assert str(private) in payload["readConfig"]["denyOnly"]
    assert str(private) in payload["writeConfig"]["denyWithinAllow"]
    assert "httpProxyPort" not in payload
    env = isolated_environment(
        {"API_TOKEN": "fake", "HTTP_PROXY": "fake", "BASH_ENV": "bad"}, tmp_path
    )
    assert env["HOME"] == str(tmp_path / "home")
    assert env["TMPDIR"] == str(tmp_path / "tmp")
    assert not {"API_TOKEN", "HTTP_PROXY", "BASH_ENV"} & env.keys()


def test_payload_limits_approved_apple_build_to_core_service_names(tmp_path: Path) -> None:
    from dataclasses import replace

    from vera.sandbox.apple_services import APPLE_IOS_BUILD_SERVICES
    from vera.sandbox.backend import build_payload

    permissions = FilePermissions(tmp_path, (tmp_path,), (tmp_path,))
    payload = build_payload(
        replace(request(tmp_path), apple_ios_build_services=True),
        permissions,
        base_readable=(),
        scratch=tmp_path / "s",
    )

    assert payload["allowMachLookup"] == list(APPLE_IOS_BUILD_SERVICES)
    assert all("*" not in service for service in payload["allowMachLookup"])


@pytest.mark.parametrize(
    "argv",
    [
        ("xcodebuild", "-sdk", "iphoneos", "-destination", "generic/platform=iOS"),
        ("xcodebuild", "-sdk", "iphoneos", "-destination", "platform=iOS Simulator"),
        ("simctl", "list", "runtimes"),
        (
            "xcodebuild",
            "-project",
            "Fake.xcodeproj",
            "-sdk",
            "iphoneos",
            "-destination",
            "generic/platform=iOS",
            "CODE_SIGNING_ALLOWED=NO",
            "CODE_SIGNING_REQUIRED=NO",
            "CODE_SIGN_IDENTITY=",
            "test",
        ),
    ],
)
def test_apple_build_service_recognition_requires_generic_unsigned_build(argv: tuple[str, ...]):
    from vera.sandbox.apple_services import requests_approved_ios_build

    assert requests_approved_ios_build(argv) is False


def test_backend_rejects_service_capability_for_simctl(tmp_path: Path) -> None:
    from dataclasses import replace

    from vera.sandbox.backend import SandboxError, SrtBackend

    backend = SrtBackend(
        runtime_root=tmp_path / "missing-runtime",
        base_readable=(),
        developer_dir=Path("/Applications/Xcode.app/Contents/Developer"),
    )
    request_with_capability = replace(
        ProcessRequest(("simctl", "list", "runtimes"), tmp_path, {}, 2),
        apple_ios_build_services=True,
    )
    permissions = FilePermissions(tmp_path, (tmp_path,), (tmp_path,))

    with (
        pytest.raises(SandboxError, match="sandbox_apple_build_service_unsupported"),
        backend.prepare(request_with_capability, permissions),
    ):
        pytest.fail("simctl must not receive the Apple build service capability")


def test_outside_cwd_and_glob_paths_rejected(tmp_path: Path) -> None:
    from vera.sandbox.backend import SandboxError, build_payload

    permissions = FilePermissions(tmp_path, (tmp_path,), (tmp_path,))
    with pytest.raises(SandboxError, match="sandbox_cwd_denied"):
        build_payload(
            request(tmp_path.parent), permissions, base_readable=(), scratch=tmp_path / "s"
        )
    with pytest.raises(SandboxError, match="sandbox_path_unsupported"):
        build_payload(
            request(tmp_path), permissions, base_readable=(tmp_path / "*",), scratch=tmp_path / "s"
        )


@pytest.mark.parametrize("payload", ["{}", "bad json", '{"command":"/bin/sh -c evil"}'])
def test_wrapper_must_contain_exact_sandbox_launch(payload: str) -> None:
    from vera.sandbox.backend import SandboxError, decode_wrapper

    with pytest.raises(SandboxError, match="sandbox_invalid_wrapper"):
        decode_wrapper(payload)


def test_wrapper_quoted_arguments_round_trip() -> None:
    from vera.sandbox.backend import decode_wrapper

    argv = (
        "env",
        "TMPDIR=/tmp/safe",
        "/usr/bin/sandbox-exec",
        "-p",
        '(version 1)\n(deny default (with message "test"))',
        "/bin/bash",
        "-c",
        "echo 'hello ; $x'",
    )
    assert decode_wrapper(json.dumps({"command": shlex.join(argv)})) == ("/usr/bin/env", *argv[2:])
