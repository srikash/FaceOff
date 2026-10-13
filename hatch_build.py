"""Hatch build hook: bundle the Zenodo template files into the wheel.

Downloads the four files (about 7.7 MB, checksum-verified) into faceoff/data when a wheel is
built. Running from a source checkout instead downloads them on first use. The MNI copyright
notice ships as faceoff/COPYING-MNI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class TemplateBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        sys.path.insert(0, str(root))
        from faceoff.template_files import fetch_missing  # standard library only

        fetch_missing(root / "faceoff" / "data", log=print)
