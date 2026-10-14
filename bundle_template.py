"""Build step: put the five template files into the pip package.

When the package is built, this downloads the files (about 9 MB) from Zenodo into
faceoff/data and checks their checksums, so `pip install faceoff` needs no further download.
Running from a source checkout without building downloads them on first use instead. The
MNI copyright notice ships as faceoff/COPYING-MNI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class TemplateBuildHook(BuildHookInterface):
    """Hatch (the packaging tool) runs this while it builds the pip package."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        """Download the template files into faceoff/data before the package is built."""
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        sys.path.insert(0, str(root))
        from faceoff.template_files import fetch_missing  # standard library only

        fetch_missing(root / "faceoff" / "data", log=print)
