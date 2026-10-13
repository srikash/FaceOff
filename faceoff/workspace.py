"""Per-run scratch directory, FSL style: /tmp/<UTC timestamp>_<12 hex digits>."""

from __future__ import annotations

import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path("/tmp")


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        return self.root / name


@contextmanager
def workspace(parent: Path = WORKSPACE_ROOT) -> Iterator[Workspace]:
    """Create the scratch directory and always delete it, including on error or Ctrl-C."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    root = parent / f"{stamp}_{secrets.token_hex(6)}"
    root.mkdir(parents=True)
    try:
        yield Workspace(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
