"""The template FaceOff registers to: a modified version of the MNI ICBM152 2020 template.

Everything FaceOff needs to know about the template is answered here: where its files are,
where the centre of its brain is, and which part of it the template-orientation outputs are
trimmed to.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache, cached_property
from pathlib import Path

import nibabel as nib
import numpy as np

from .template_files import PREFIX, ZENODO_RECORD, fetch_missing, is_complete

# Template slices (voxel indices along z, end exclusive) kept in the template-orientation
# outputs unless --no-crop is given.
TEMPLATE_CROP_Z = (70, 264)

_BUNDLED_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Template:
    """The template files in one folder, and the facts about them FaceOff uses."""

    folder: Path

    @classmethod
    def default(cls) -> Template:
        """Return the template FaceOff uses. The folder is, first match wins:

        1. FACEOFF_TEMPLATE_DIR, if set;
        2. faceoff/data, when the files came with the pip package (checked against their
           published checksums);
        3. faceoff/zenodo-23328835 in your cache folder ($XDG_CACHE_HOME, usually ~/.cache),
           where they are downloaded on first use.
        """
        return _default_template(
            os.environ.get("FACEOFF_TEMPLATE_DIR"), os.environ.get("XDG_CACHE_HOME")
        )

    @property
    def t1w(self) -> Path:
        """The template T1w image every scan is registered to."""
        return self.folder / f"{PREFIX}T1w_ref.nii.gz"

    @property
    def brain_mask(self) -> Path:
        """The brain mask; it limits the affine and --syn registration to the brain."""
        return self.folder / f"{PREFIX}brain_mask.nii.gz"

    @property
    def reface_mask(self) -> Path:
        """The region the refacing registration (SyN) is fitted over."""
        return self.folder / f"{PREFIX}reface_mask.nii.gz"

    @property
    def face_mask(self) -> Path:
        """The face and ears: 1 = remove, 0 = keep."""
        return self.folder / f"{PREFIX}face_mask.nii.gz"

    @cached_property
    def brain_centre_lps(self) -> np.ndarray:
        """The centre of the brain mask, in LPS world coordinates (mm)."""
        mask = nib.load(self.brain_mask)
        voxel = np.argwhere(np.asanyarray(mask.dataobj) > 0).mean(axis=0)
        ras = mask.affine @ np.append(voxel, 1.0)
        return (ras * np.array([-1.0, -1.0, 1.0, 1.0]))[:3]

    @cached_property
    def crop_z_mm(self) -> tuple[float, float]:
        """The world z range (mm, RAS) covered by template slices TEMPLATE_CROP_Z.

        The range runs from the lower edge of the first slice kept to the lower edge of the
        first slice dropped, so it works for any slice thickness.
        """
        image = nib.load(self.t1w)
        centre = (np.array(image.shape[:3]) - 1) / 2
        edges = []
        for index in TEMPLATE_CROP_Z:
            voxel = centre.copy()
            voxel[2] = index - 0.5
            edges.append(float(nib.affines.apply_affine(image.affine, voxel)[2]))
        return min(edges), max(edges)


@cache
def _default_template(override: str | None, cache_home: str | None) -> Template:
    """Find the template folder (see Template.default); remembered for the rest of the run."""
    if override:
        return Template(Path(override))
    if is_complete(_BUNDLED_DIR):
        return Template(_BUNDLED_DIR)
    cache_dir = Path(cache_home) if cache_home else Path.home() / ".cache"
    return Template(cache_dir / "faceoff" / f"zenodo-{ZENODO_RECORD}")


def ensure_template(log: Callable[[str], None] = lambda message: None) -> None:
    """Download any template file that is missing or damaged. Raises RuntimeError if the
    download fails."""
    fetch_missing(Template.default().folder, log=log)
