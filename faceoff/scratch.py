"""The temporary folder each run works in, named like FSL's: /tmp/<UTC time>_<12 hex digits>.

ANTs writes its transforms and warped masks here. The folder is deleted when the run ends,
whether it finished, failed, or was stopped with Ctrl-C.
"""

from __future__ import annotations

import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path("/tmp")


class Workspace:
    """The temporary folder for one run."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        """Return the path of a file called `name` inside the temporary folder."""
        return self.root / name


@contextmanager
def workspace(parent: Path = WORKSPACE_ROOT) -> Iterator[Workspace]:
    """Make a temporary folder for one run and delete it afterwards, even if the run fails."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    root = parent / f"{stamp}_{secrets.token_hex(6)}"
    root.mkdir(parents=True)
    try:
        yield Workspace(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
