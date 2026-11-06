"""The temporary folder each run works in: a hidden folder beside the scan, named
`.faceoff-<UTC time>-<12 hex digits>`.

ANTs writes its transforms and warped masks here. It is beside the scan, which must be
writable for the outputs anyway, so that it does not depend on /tmp (which is memory on many
systems and small on clusters). The folder is deleted when the run ends, whether it finished,
failed, or was stopped with Ctrl-C or SIGTERM. A hard kill (SIGKILL, for example by the
scheduler's memory limit) cannot clean up; the next run in that folder warns about what is left.
"""

from __future__ import annotations

import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

PREFIX = ".faceoff-"


class Workspace:
    """The temporary folder for one run."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        return self.root / name


@contextmanager
def workspace(parent: Path) -> Iterator[Workspace]:
    """Make a temporary folder inside `parent` and delete it afterwards, even if the run fails.
    The name has no colons, which some file systems and sync tools refuse."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = parent.resolve() / f"{PREFIX}{stamp}-{secrets.token_hex(6)}"
    root.mkdir()
    try:
        yield Workspace(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
