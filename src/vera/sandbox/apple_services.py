"""Core-owned Apple build service capability facts."""

import platform
import re
from pathlib import Path

APPLE_IOS_BUILD_SERVICES = (
    "com.apple.CoreSimulator.CoreSimulatorService",
    "com.apple.CoreSimulator.simdiskimaged",
    "com.apple.FileCoordination",
    "com.apple.FSEvents",
    "com.apple.CoreServices.coreservicesd",
) + (("com.apple.CoreSimulator.SimLaunchHost-x86",) if platform.machine() == "x86_64" else ())


def requests_approved_ios_build(argv: tuple[str, ...]) -> bool:
    """Recognize only an unsigned, generic iPhoneOS Xcode build."""

    if not argv or Path(argv[0]).name != "xcodebuild":
        return False
    # Keep the managed output contract concrete; arbitrary build actions and
    # output overrides must not silently change the approved operation.
    forbidden_options = {"-derivedDataPath", "-resultBundlePath", "-archivePath", "-target"}
    actions = {
        "test",
        "test-without-building",
        "build-for-testing",
        "archive",
        "install",
        "clean",
        "analyze",
        "exportArchive",
    }
    output_keys = {
        "SYMROOT",
        "OBJROOT",
        "DSTROOT",
        "CONFIGURATION_BUILD_DIR",
        "BUILD_DIR",
        "BUILD_ROOT",
        "PROJECT_TEMP_DIR",
        "TARGET_TEMP_DIR",
        "CONFIGURATION_TEMP_DIR",
        "SHARED_PRECOMPS_DIR",
    }
    if any(
        arg in forbidden_options or arg in actions or arg.split("=", 1)[0] in output_keys
        for arg in argv[1:]
    ):
        return False
    for key, value in (
        ("CODE_SIGNING_ALLOWED", "NO"),
        ("CODE_SIGNING_REQUIRED", "NO"),
        ("CODE_SIGN_IDENTITY", ""),
    ):
        if [a for a in argv if a.startswith(key + "=")] != [key + "=" + value]:
            return False
    destination = _option_value(argv, "-destination")
    sdk = _option_value(argv, "-sdk")
    return (
        destination == "generic/platform=iOS"
        and argv[-1] == "build"
        and _option_value(argv, "-scheme") is not None
        and sdk is not None
        and re.fullmatch(r"iphoneos(?:[0-9]+(?:\.[0-9]+)*)?", sdk) is not None
        and "CODE_SIGNING_ALLOWED=NO" in argv
        and "CODE_SIGNING_REQUIRED=NO" in argv
        and "CODE_SIGN_IDENTITY=" in argv
    )


def _option_value(argv: tuple[str, ...], option: str) -> str | None:
    if argv.count(option) != 1:
        return None
    try:
        return argv[argv.index(option) + 1]
    except (ValueError, IndexError):
        return None
