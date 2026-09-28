"""Core-owned disposable output volume for signed Apple tools' atomic writes."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

APPLE_BUILD_STORAGE = {
    "kind": "temporary_apfs_volume_v1",
    "max_size_gib": 8,
    "derived_data": "<Core-owned-volume>/DerivedData",
    "cleanup": "after_execution",
}


class AppleVolumeError(ValueError):
    def __init__(self, root: Path, *, cleanup: bool = False) -> None:
        self.root = root
        self.cleanup = cleanup
        super().__init__(
            "apple_build_volume_cleanup_failed" if cleanup else "apple_build_volume_failed"
        )


def _hdiutil(*args: str) -> None:
    result = subprocess.run(
        ("/usr/bin/hdiutil", *args),
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
        capture_output=True,
        timeout=45,
        check=False,
    )
    if result.returncode:
        raise OSError("hdiutil failed")


@contextmanager
def apple_build_volume(forbidden_roots: tuple[Path, ...]) -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="vera-apple-build-")).resolve()
    volume = root / "volume"
    attach_started = False
    detached = False
    try:
        # The project must never gain access to the backing image or its parent.
        if any(root.is_relative_to(p.resolve()) for p in forbidden_roots):
            raise AppleVolumeError(root)
        volume.mkdir(mode=0o700)
        image = root / "build.sparseimage"
        _hdiutil(
            "create",
            "-size",
            "8g",
            "-type",
            "SPARSE",
            "-fs",
            "APFS",
            "-volname",
            "VeraBuild",
            str(image),
        )
        attach_started = True
        _hdiutil(
            "attach",
            str(image),
            "-mountpoint",
            str(volume),
            "-nobrowse",
            "-noautoopen",
            "-owners",
            "on",
        )
        if not os.path.ismount(volume) or volume.stat().st_dev == root.stat().st_dev:
            raise AppleVolumeError(root)
        yield volume
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AppleVolumeError(root) from exc
    finally:
        if attach_started:
            # Even a timed-out attach may have mounted the image. Never traverse
            # or delete its backing directory until a successful exact detach.
            try:
                _hdiutil("detach", str(volume))
                detached = not os.path.ismount(volume)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if not detached:
                raise AppleVolumeError(root, cleanup=True)
        try:
            shutil.rmtree(root)
        except OSError as exc:
            raise AppleVolumeError(root, cleanup=True) from exc
